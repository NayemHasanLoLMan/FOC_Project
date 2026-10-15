"""
OCR engine abstraction layer.

Supports two backends:
  - "easyocr"  : Free, local OCR using EasyOCR + PyMuPDF (for POC/development)
  - "azure"    : Azure AI Document Intelligence (for production)

Both backends return the same OCRResult dataclass so the parser
does not need to know which backend was used.
"""

import os
import re
import hashlib
import json
from statistics import median
from dataclasses import asdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Unified OCR result model
# ---------------------------------------------------------------------------

@dataclass
class OCRWord:
    """Single recognized word with bounding-box and confidence."""
    text: str
    confidence: float = 1.0
    x0: float = 0.0
    y0: float = 0.0
    x1: float = 0.0
    y1: float = 0.0
    page: int = 0


@dataclass
class OCRTableCell:
    """A single cell detected in a table."""
    row_index: int
    column_index: int
    content: str
    page: int = 0
    bbox: list[float] | None = None
    confidence: float | None = None
    original_content: str | None = None


@dataclass
class OCRTable:
    """A table detected in the document."""
    cells: list[OCRTableCell] = field(default_factory=list)
    row_count: int = 0
    column_count: int = 0
    page: int = 0
    bbox: list[float] | None = None


@dataclass
class OCRResult:
    """
    Unified OCR result returned by any backend.

    Attributes:
        content:  Full extracted text (all pages concatenated).
        words:    Individual words with coordinates and confidence.
        tables:   Detected tables with cell contents.
        pages:    Per-page text content.
        backend:  Which OCR backend produced this result.
    """
    content: str = ""
    words: list[OCRWord] = field(default_factory=list)
    tables: list[OCRTable] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    backend: str = ""
    total_pages: int = 0
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# EasyOCR backend
# ---------------------------------------------------------------------------

def _pdf_to_images(pdf_path: Path, dpi: int = 180, max_pages: int | None = None):
    """Convert pages of a PDF to PIL images using PyMuPDF."""
    import pymupdf as fitz  # PyMuPDF
    from PIL import Image
    import io

    doc = fitz.open(str(pdf_path))
    num_pages = len(doc)
    if max_pages is not None:
        num_pages = min(num_pages, max_pages)

    for page_num in range(num_pages):
        page = doc[page_num]
        digital_text = page.get_text().strip()
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_bytes))
        yield page_num, img, digital_text
    doc.close()


def _grid_tables(img, words, page, reader=None):
    """Recover ruled packing-list cells using existing OpenCV and OCR boxes."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(np.array(img.convert('RGB')), cv2.COLOR_RGB2GRAY)
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = gray.shape
    def positions(vertical):
        kernel = (1, max(25, h // 6)) if vertical else (max(25, w // 3), 1)
        tolerant = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (5,1) if vertical else (1,3)))
        supported=tolerant
        # Printed row gutters interrupt inner vertical rules on these packing lists.
        if vertical:
            tolerant = cv2.morphologyEx(tolerant, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8,h//40))))
        mask = cv2.morphologyEx(tolerant, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kernel))
        contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
        vals = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if vertical and ch > h*.20:
                # Text can join a rule after closing; require ink along most of its height.
                offsets=np.flatnonzero(np.count_nonzero(supported[y:y+ch,x:x+cw],axis=0)/ch >= .65)
                vals.extend(x+int(offset) for offset in offsets)
            elif not vertical and cw > w*.55:
                vals.append(y+ch/2)
        groups = []
        for v in sorted(vals):
            if not groups or v - groups[-1][-1] > 12:
                groups.append([v])
            else:
                groups[-1].append(v)
        return [sum(g) / len(g) for g in groups]
    xs, ys = positions(True), positions(False)
    if len(xs) < 4 or len(ys) < 3:
        return []
    cells = []
    for r, (top, bottom) in enumerate(zip(ys, ys[1:])):
        for c, (left, right) in enumerate(zip(xs, xs[1:])):
            selected = [v for v in words if left <= (v.x0+v.x1)/2 < right and top <= (v.y0+v.y1)/2 < bottom]
            if selected:
                tol = max(3, median(v.y1-v.y0 for v in selected) * .45)
                cells.append(OCRTableCell(r, c, '\n'.join(_cluster_into_lines(selected, tol)), page,
                                          [left,top,right,bottom],min(v.confidence for v in selected)))
    # Numeric columns are often tiny beside long descriptions. Read their
    # cropped cells at higher magnification instead of guessing I/1 or S/5.
    from .parser import _table_fields
    columns,header=_table_fields(OCRTable(cells,len(ys)-1,len(xs)-1,page))
    numeric_cols={columns[k] for k in ('quantity','weight','packages') if k in columns}
    if reader and numeric_cols:
        by_cell={(c.row_index,c.column_index):c for c in cells}
        occupied_rows={c.row_index for c in cells if c.row_index>header}
        for r in sorted(occupied_rows):
            for c in sorted(numeric_cols):
                existing=by_cell.get((r,c))
                if existing and existing.confidence is not None and existing.confidence >= .9:
                    continue
                crop=img.crop((int(xs[c])+3,int(ys[r])+3,int(xs[c+1])-3,int(ys[r+1])-3))
                if crop.width<5 or crop.height<5:continue
                crop=crop.resize((crop.width*2,crop.height*2))
                recognized=reader.readtext(np.array(crop),detail=1,paragraph=False,min_size=3,text_threshold=.5,low_text=.3)
                if recognized:
                    local=[OCRWord(t,float(conf),min(p[0] for p in box),min(p[1] for p in box),max(p[0] for p in box),max(p[1] for p in box),page) for box,t,conf in recognized]
                    value='\n'.join(_cluster_into_lines(local,max(3,median(w.y1-w.y0 for w in local)*.45)))
                    confidence=min(w.confidence for w in local)
                    if existing:
                        existing.original_content=existing.content
                        if confidence > (existing.confidence or 0):
                            existing.content=value
                            existing.confidence=confidence
                    else:cells.append(OCRTableCell(r,c,value,page,[xs[c],ys[r],xs[c+1],ys[r+1]],confidence))
    return [OCRTable(cells, len(ys)-1, len(xs)-1, page,[xs[0],ys[0],xs[-1],ys[-1]])]


def _cached_page_image(pdf_path, page, words, dpi=180):
    """Align a PDF render with existing OCR boxes without running OCR again."""
    import pymupdf
    import numpy as np
    from PIL import Image
    with pymupdf.open(pdf_path) as doc:
        pix=doc[page].get_pixmap(dpi=dpi)
        original=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
    candidates=[]
    for angle in (0,90,180,270):
        img=original.rotate(angle,expand=True)
        if any(w.x1>img.width+5 or w.y1>img.height+5 for w in words):continue
        img=_deskew(img)
        ink=np.array(img.convert('L'))<160
        densities=[]
        for word in words:
            crop=ink[max(0,int(word.y0)):int(word.y1),max(0,int(word.x0)):int(word.x1)]
            if crop.size and word.confidence>=.7:densities.append(float(crop.mean()))
        candidates.append((sum(densities)/len(densities) if densities else 0,angle,img))
    if not candidates:raise ValueError('Cached OCR coordinates do not fit the PDF page')
    return max(candidates,key=lambda candidate:candidate[0])[2]


def _upgrade_cached_tables(result, pdf_path):
    from .parser import _table_fields
    for page in range(len(result.pages)):
        words=[w for w in result.words if w.page==page]
        if not words or not any(w.x1 for w in words) or 'SHIPPER' in result.pages[page].upper():continue
        old=[t for t in result.tables if t.page==page]
        image=_cached_page_image(pdf_path,page,words)
        rebuilt=_grid_tables(image,words,page)
        if not rebuilt:continue
        if not any(_table_fields(t)[0] for t in old):
            result.tables=[t for t in result.tables if t.page!=page]+rebuilt
        elif len(old)==len(rebuilt)==1 and (old[0].row_count,old[0].column_count)==(rebuilt[0].row_count,rebuilt[0].column_count):
            by_position={(c.row_index,c.column_index):c for c in rebuilt[0].cells}
            old[0].bbox=rebuilt[0].bbox
            for cell in old[0].cells:
                candidate=by_position.get((cell.row_index,cell.column_index))
                if candidate:
                    cell.bbox=candidate.bbox
                    cell.original_content=candidate.content
                    if candidate.content==cell.content:cell.confidence=candidate.confidence
    result.tables.sort(key=lambda table:table.page)
    return result


def _deskew(img):
    import cv2
    import numpy as np
    import math
    gray=cv2.cvtColor(np.array(img.convert('RGB')),cv2.COLOR_RGB2GRAY)
    lines=cv2.HoughLinesP(cv2.Canny(gray,50,150),1,np.pi/1800,100,minLineLength=min(img.size)//3,maxLineGap=25)
    angles=[]
    for x1,y1,x2,y2 in lines.reshape(-1,4) if lines is not None else []:
        angle=math.degrees(math.atan2(y2-y1,x2-x1))
        if abs(angle)<5:angles.append(angle)
    angle=median(angles) if angles else 0
    return img.rotate(angle,expand=False,fillcolor='white') if abs(angle)>.08 else img


def _cluster_into_lines(words: list[OCRWord], line_tol: float = 12.0) -> list[str]:
    """Group words into horizontal text lines based on y-coordinate clustering."""
    if not words:
        return []

    # Sort primarily by y0
    sorted_words = sorted(words, key=lambda w: (w.y0, w.x0))
    line_groups: list[list[OCRWord]] = []

    for w in sorted_words:
        placed = False
        for grp in line_groups:
            # Check vertical overlap or close y-center
            avg_y = sum(gw.y0 for gw in grp) / len(grp)
            if abs(w.y0 - avg_y) <= line_tol:
                grp.append(w)
                placed = True
                break
        if not placed:
            line_groups.append([w])

    # Sort each group horizontally left-to-right, then assemble lines
    lines = []
    line_groups.sort(key=lambda g: sum(gw.y0 for gw in g) / len(g))
    for grp in line_groups:
        grp_sorted = sorted(grp, key=lambda w: w.x0)
        lines.append(" ".join(gw.text for gw in grp_sorted if gw.text))
    return lines


def analyze_with_easyocr(
    pdf_path: Path,
    languages: list[str] | None = None,
    dpi: int = 180,
    max_pages: int | None = None,
    page_cache_dir: Path | None = None,
) -> OCRResult:
    """
    Run EasyOCR on a PDF file with auto-rotation and reading-order line clustering.
    """
    import easyocr
    import numpy as np
    import torch
    import pymupdf

    torch.set_num_threads(min(4, os.cpu_count() or 1))

    if languages is None:
        languages = ['en']

    key = tuple(sorted(languages))
    global _EASYOCR_READERS
    if "_EASYOCR_READERS" not in globals():
        _EASYOCR_READERS = {}
    if key not in _EASYOCR_READERS:
        _EASYOCR_READERS[key] = easyocr.Reader(languages, gpu=False, verbose=False)
    reader = _EASYOCR_READERS[key]

    pages_data = _pdf_to_images(pdf_path, dpi=dpi, max_pages=max_pages)

    all_words: list[OCRWord] = []
    page_texts: list[str] = []
    tables: list[OCRTable] = []
    with pymupdf.open(pdf_path) as doc:
        total_pages = len(doc)

    for page_num, img, digital_text in pages_data:
        checkpoint = page_cache_dir / f'{page_num}.json' if page_cache_dir else None
        if checkpoint and checkpoint.exists():
            saved=json.loads(checkpoint.read_text(encoding='utf-8'))
            all_words.extend(OCRWord(**v) for v in saved['words'])
            tables.extend(OCRTable(**{**t,'cells':[OCRTableCell(**c) for c in t['cells']]}) for t in saved['tables'])
            page_texts.append(saved['content'])
            continue
        # If the page already has clean digital text, use it
        if len(digital_text) > 100:
            lines = [l.strip() for l in digital_text.splitlines() if l.strip()]
            page_text = "\n".join(lines)
            page_texts.append(page_text)
            for word_str in page_text.split():
                all_words.append(OCRWord(text=word_str, confidence=1.0, page=page_num))
            continue

        # Score all right-angle orientations on a small preview. Result count
        # alone favours sideways garbage on dense tables.
        preview = img.copy()
        preview.thumbnail((1100, 1100))
        candidates = []
        for angle in (0, 90, 180, 270):
            recognized = reader.readtext(np.array(preview.rotate(angle, expand=True)), detail=1, paragraph=False)
            score = sum(len(re.sub(r'\W', '', t)) * float(c)**2 for _, t, c in recognized)
            candidates.append((score, angle))
            readable = ' '.join(t for _, t, c in recognized if c > .65).upper()
            if re.search(r'PACKING LIST|SHIPPER|PARTICULARS|QUANTITY', readable) and score > 150:
                break
        angle = max(candidates)[1]
        img = _deskew(img.rotate(angle, expand=True))
        results = reader.readtext(np.array(img), detail=1, paragraph=False, canvas_size=3000)

        page_words: list[OCRWord] = []
        for bbox, text, confidence in results:
            clean_text = text.strip()
            if not clean_text:
                continue
            x0 = min(p[0] for p in bbox)
            y0 = min(p[1] for p in bbox)
            x1 = max(p[0] for p in bbox)
            y1 = max(p[1] for p in bbox)

            word = OCRWord(
                text=clean_text,
                confidence=float(confidence),
                x0=float(x0), y0=float(y0), x1=float(x1), y1=float(y1),
                page=page_num,
            )
            page_words.append(word)
            all_words.append(word)

        page_tables=_grid_tables(img, page_words, page_num, reader)
        tables.extend(page_tables)
        lines = _cluster_into_lines(page_words, line_tol=max(3, median(w.y1-w.y0 for w in page_words) * .45) if page_words else 8)
        page_text = "\n".join(lines)
        page_texts.append(page_text)
        if checkpoint:
            checkpoint.parent.mkdir(parents=True,exist_ok=True)
            temp=checkpoint.with_suffix('.tmp')
            temp.write_text(json.dumps({'content':page_text,'words':[asdict(w) for w in page_words],
                                       'tables':[asdict(t) for t in page_tables]}),encoding='utf-8')
            temp.replace(checkpoint)
        print(f'  OCR {pdf_path.name}: page {page_num + 1}, rotation {angle}, {len(page_words)} boxes', flush=True)

    full_text = "\n\n--- PAGE BREAK ---\n\n".join(page_texts)

    return OCRResult(
        content=full_text,
        words=all_words,
        tables=tables,
        pages=page_texts,
        backend="easyocr",
        total_pages=total_pages,
        warnings=['Page limit excluded source pages.'] if len(page_texts) < total_pages else [],
    )


# ---------------------------------------------------------------------------
# Azure Document Intelligence backend
# ---------------------------------------------------------------------------

def analyze_with_azure(pdf_path: Path, model_id: str | None = None) -> OCRResult:
    """
    Run Azure AI Document Intelligence on a PDF file.

    Requires environment variables:
      - AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT
      - AZURE_DOCUMENT_INTELLIGENCE_KEY

    Args:
        pdf_path: Path to the PDF file.
        model_id: Azure model ID (default: from env or 'prebuilt-layout').

    Returns:
        OCRResult with full text, tables, and per-word data.
    """
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential

    endpoint = os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"]
    key = os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]
    model = model_id or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID", "prebuilt-layout")

    client = DocumentIntelligenceClient(
        endpoint=endpoint,
        credential=AzureKeyCredential(key),
    )

    with pdf_path.open("rb") as f:
        poller = client.begin_analyze_document(
            model, body=f, content_type="application/pdf"
        )
    azure_result = poller.result()

    # Convert Azure result to unified OCRResult
    content = getattr(azure_result, "content", "") or ""

    # Extract words
    words: list[OCRWord] = []
    for page in getattr(azure_result, "pages", []) or []:
        for word in getattr(page, "words", []) or []:
            polygon = getattr(word, "polygon", None) or []
            x_coords = [polygon[i] for i in range(0, len(polygon), 2)] if polygon else [0]
            y_coords = [polygon[i] for i in range(1, len(polygon), 2)] if polygon else [0]
            words.append(OCRWord(
                text=word.content,
                confidence=getattr(word, "confidence", 1.0),
                x0=min(x_coords),
                y0=min(y_coords),
                x1=max(x_coords),
                y1=max(y_coords),
                page=getattr(page, "page_number", 1) - 1,
            ))

    # Extract tables
    tables: list[OCRTable] = []
    for azure_table in getattr(azure_result, "tables", []) or []:
        cells: list[OCRTableCell] = []
        for cell in azure_table.cells:
            cells.append(OCRTableCell(
                row_index=cell.row_index,
                column_index=cell.column_index,
                content=cell.content.strip(),
                page=getattr(cell, "bounding_regions", [{}])[0].get("page_number", 1) - 1
                if getattr(cell, "bounding_regions", None) else 0,
            ))
        tables.append(OCRTable(
            cells=cells,
            row_count=getattr(azure_table, "row_count", 0),
            column_count=getattr(azure_table, "column_count", 0),
        ))

    # Per-page text (split on page breaks if available)
    pages = content.split("\n\n") if content else []

    return OCRResult(
        content=content,
        words=words,
        tables=tables,
        pages=pages,
        backend="azure",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_pdf(
    pdf_path: Path,
    backend: str = "auto",
    model_id: str | None = None,
    max_pages: int | None = None,
    cache_dir: Path | None = None,
) -> OCRResult:
    """
    Analyze a PDF file using the specified OCR backend.

    Args:
        pdf_path:   Path to the PDF file.
        backend:    "easyocr", "azure", or "auto".
                    "auto" uses Azure if credentials are set, else EasyOCR.
        model_id:   Azure model ID (only used with azure backend).
        max_pages:  Maximum local OCR pages (None, the default, processes all).

    Returns:
        OCRResult with extracted text, words, and tables.
    """
    if backend == "auto":
        has_azure = (
            os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
            and os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")
        )
        backend = "azure" if has_azure else "easyocr"

    if backend not in ('azure', 'easyocr'):
        raise ValueError(f"Unknown OCR backend: {backend!r}. Use 'easyocr', 'azure', or 'auto'.")
    cache = None
    if cache_dir:
        effective_model=(model_id or os.getenv('AZURE_DOCUMENT_INTELLIGENCE_MODEL_ID','prebuilt-layout')) if backend=='azure' else model_id
        settings = f'grid-v4:{backend}:{effective_model}:{max_pages}:180'.encode()
        digest = hashlib.sha256(pdf_path.read_bytes() + settings).hexdigest()
        cache = Path(cache_dir) / f'{digest}.json'
        legacy=Path(cache_dir)/f"{hashlib.sha256(pdf_path.read_bytes()+f'grid-v3:{backend}:{model_id}:{max_pages}:180'.encode()).hexdigest()}.json"
        source=cache if cache.exists() else legacy if backend=='easyocr' else cache
        if source.exists():
            try:raw = json.loads(source.read_text(encoding='utf-8'))
            except (ValueError,OSError):raw=None
        else:raw=None
        if raw is not None:
            raw['words'] = [OCRWord(**v) for v in raw['words']]
            raw['tables'] = [OCRTable(**{**t, 'cells':[OCRTableCell(**c) for c in t['cells']]}) for t in raw['tables']]
            result=OCRResult(**raw)
            if source==legacy:
                result=_upgrade_cached_tables(result,pdf_path)
                temporary=cache.with_suffix('.tmp')
                temporary.write_text(json.dumps(asdict(result),ensure_ascii=False),encoding='utf-8')
                temporary.replace(cache)
            return result
    result = analyze_with_azure(pdf_path, model_id) if backend == 'azure' else analyze_with_easyocr(
        pdf_path, max_pages=max_pages, page_cache_dir=cache.with_suffix('') if cache else None)
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        temporary = cache.with_suffix('.tmp')
        temporary.write_text(json.dumps(asdict(result), ensure_ascii=False), encoding='utf-8')
        temporary.replace(cache)
    return result
