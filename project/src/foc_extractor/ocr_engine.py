"""
OCR engine abstraction layer.

Local PaddleOCR with page geometry and source-keyed caching.

OCRResult carries page text, coordinates, tables and coverage to the parser.
"""

from .processing_evidence import emit
import os
import re
import hashlib
import json
from statistics import median
from dataclasses import asdict, dataclass, field
from pathlib import Path


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
    Local OCR evidence consumed by the parser and invoice audit.

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
    dpi: int = 300
    page_transforms: list[dict] = field(default_factory=list)
    table_version: int = 0


# ---------------------------------------------------------------------------
# Page rendering and table geometry
# ---------------------------------------------------------------------------

def _pdf_to_images(pdf_path: Path, dpi: int = 300, max_pages: int | None = None):
    """Render source pages at the local OCR resolution."""
    import pymupdf
    from PIL import Image
    with pymupdf.open(pdf_path) as document:
        count=min(len(document),max_pages) if max_pages is not None else len(document)
        for page in range(count):
            pix=document[page].get_pixmap(dpi=dpi)
            yield page,Image.frombytes('RGB',[pix.width,pix.height],pix.samples)


def _grid_tables(img, words, page):
    """Recover ruled packing-list cells using existing OpenCV and OCR boxes."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(np.array(img.convert('RGB')), cv2.COLOR_RGB2GRAY)
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = gray.shape
    def positions(vertical, relaxed=False):
        kernel = (1, max(25, h // 12)) if vertical else (max(25, w // 3), 1)
        tolerant = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (5,1) if vertical else (1,max(3,round(w*.004)) if relaxed else 3)))
        supported=tolerant
        # Printed row gutters interrupt inner vertical rules on these packing lists.
        if vertical:
            tolerant = cv2.morphologyEx(tolerant, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(8,h//40))))
        mask = cv2.morphologyEx(tolerant, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, kernel))
        contours = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
        vals = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)
            if vertical and ch > h*.08:
                # Text can join a rule after closing; require ink along most of its height.
                support=np.count_nonzero(supported[y:y+ch,x:x+cw],axis=0)/ch
                offsets=np.flatnonzero(support >= .65)
                vals.extend(x+int(offset) for offset in offsets)
                # Slightly leaning rules span several pixel columns on high-resolution scans.
                if not len(offsets) and support.max()>=.5 and cw<=max(12,w*.01) and ch>h*.15:
                    vals.append(x+cw/2)
            elif not vertical and cw > w*(.4 if relaxed else .55):
                vals.append(y+ch/2)
        if vertical:
            lines=cv2.HoughLinesP(ink,1,np.pi/1800,80,minLineLength=h//5,maxLineGap=h//100)
            for x0,y0,x1,y1 in lines.reshape(-1,4) if lines is not None else []:
                if abs(x1-x0)<=abs(y1-y0)*.02 and abs(y1-y0)>h*.2:
                    vals.append((x0+x1)/2)
        groups = []
        merge_tol=max(6,(w if vertical else h)*.006)
        for v in sorted(vals):
            if not groups or v - groups[-1][-1] > merge_tol:
                groups.append([v])
            else:
                groups[-1].append(v)
        return [sum(g) / len(g) for g in groups]
    xs, ys = positions(True), positions(False)
    if len(xs)>=4 and len(ys)<3:
        # Retry small scan slopes before giving up on physical table boundaries.
        ys=positions(False,relaxed=True)
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
    return [OCRTable(cells, len(ys)-1, len(xs)-1, page,[xs[0],ys[0],xs[-1],ys[-1]])]


def _cached_page_image(pdf_path, page, dpi=300, transform=None):
    """Align a PDF render with existing OCR boxes without running OCR again."""
    import pymupdf
    from PIL import Image
    with pymupdf.open(pdf_path) as doc:
        pix=doc[page].get_pixmap(dpi=dpi)
        original=Image.frombytes('RGB',[pix.width,pix.height],pix.samples)
    if transform is not None:
        oriented=original.rotate(transform['rotation'],expand=True)
        return oriented.rotate(transform['skew'],expand=False,fillcolor='white')
    return original


def _column_regions(image, box, quantity_cells, words, page, group_braces=False):
    """Locate physical cells in a ruled column, using goods quantities as anchors."""
    import cv2
    import numpy as np
    left,top,right,bottom=map(round,box)
    if not (0<=left<right<=image.width and 0<=top<bottom<=image.height) or right-left<20 or bottom-top<10:
        raise ValueError('Column is too small or outside the page')
    strip=np.asarray(image.convert('L'))[top:bottom,left+5:right-5]
    ink=cv2.threshold(strip,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)[1]
    tolerant=cv2.dilate(ink,cv2.getStructuringElement(cv2.MORPH_RECT,(1,5)))
    rules=cv2.morphologyEx(tolerant,cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_RECT,(max(15,strip.shape[1]//2),1)))
    groups=[]
    for y in np.flatnonzero(np.count_nonzero(rules,axis=1)>=strip.shape[1]*.7):
        if not groups or y-groups[-1][-1]>5:groups.append([int(y)])
        else:groups[-1].append(int(y))
    cuts=[top]+[top+round(sum(g)/len(g)) for g in groups if 5<sum(g)/len(g)<bottom-top-5]+[bottom]
    points=[(w.y0+w.y1)/2 for w in words if w.page==page and any(
        c.bbox[0]<=(w.x0+w.x1)/2<c.bbox[2] and c.bbox[1]<=(w.y0+w.y1)/2<c.bbox[3]
        for c in quantity_cells)] if words else [(c.bbox[1]+c.bbox[3])/2 for c in quantity_cells]
    if not points or any(not top<=y<bottom for y in points):
        raise ValueError('Goods rows cannot be assigned to physical column cells')
    regions=[[left,y0,right,y1] for y0,y1 in zip(cuts,cuts[1:]) if any(y0<=y<y1 for y in points)]
    if group_braces:
        # shortcut: Only continuous blue braces group ruled rows; extend for other source annotation styles.
        rgb=np.asarray(image.convert('RGB'))[top:bottom,left:right].astype(int)
        blue=((rgb[:,:,2]>rgb[:,:,0]+25)&(rgb[:,:,2]>rgb[:,:,1]+15)).astype('uint8')
        blue=cv2.morphologyEx(blue,cv2.MORPH_CLOSE,np.ones((11,1),dtype='uint8'))
        _,_,stats,_=cv2.connectedComponentsWithStats(blue)
        if len(regions)>1 and any(x<(right-left)*.2 and h>4*w
                and top+y<=min(points) and top+y+h>=max(points) for x,y,w,h,area in stats[1:]):
            regions=[[left,regions[0][1],right,regions[-1][3]]]
    return regions


def _skew_angle(img):
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
    return angle if abs(angle)>.08 else 0


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


# ---------------------------------------------------------------------------
# PaddleOCR backend
# ---------------------------------------------------------------------------

def _reread_paddle_quantities(img, tables, reader):
    import numpy as np
    from .parser import _table_fields, _quantity_text, QTY_UNIT, NUM
    from .local_vision import _accepted_quantity
    for table in tables:
        columns,header=_table_fields(table)
        if 'quantity' not in columns:continue
        for cell in table.cells:
            if cell.row_index<=header or cell.column_index!=columns['quantity'] or not cell.bbox:continue
            text=_quantity_text(cell.content).strip()
            main=re.sub(r'\([^)]*\)|\[[^]]*\]','',text)
            if not text or re.fullmatch(NUM,text) or (QTY_UNIT.search(main) and not QTY_UNIT.sub('',main).strip(' \t\n\r+&,;:.()[]')):continue
            left,top,right,bottom=cell.bbox
            crop=img.crop((int(left)+3,int(top)+3,int(right)-3,int(bottom)-3))
            if min(crop.size)<5:continue
            crop=crop.resize((crop.width*2,crop.height*2))
            raw=next(iter(reader.predict(np.array(crop)[:,:,::-1])))
            candidate=' '.join(raw['rec_texts']).strip()
            if _accepted_quantity(cell.content,candidate):
                cell.original_content=cell.content
                cell.content=candidate
                cell.confidence=min((float(s) for s in raw['rec_scores']),default=None)


def _paddle_readers():
    os.environ.setdefault('PADDLE_PDX_CACHE_HOME',str(Path(__file__).resolve().parents[2]/'.cache/paddlex'))
    os.environ.setdefault('PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK','True')
    from paddleocr import PaddleOCR, DocImgOrientationClassification
    global _PADDLE_READERS
    if '_PADDLE_READERS' not in globals():
        options=dict(device='cpu',cpu_threads=min(4,os.cpu_count() or 1),enable_mkldnn=True)
        reader=PaddleOCR(**options,text_detection_model_name='PP-OCRv5_mobile_det',
            text_recognition_model_name='en_PP-OCRv5_mobile_rec',text_recognition_batch_size=1,
            text_det_limit_side_len=3000,text_det_limit_type='max',
            use_doc_orientation_classify=False,use_doc_unwarping=False,use_textline_orientation=False)
        orientation=DocImgOrientationClassification(**options)
        _PADDLE_READERS=(reader,orientation)
    return _PADDLE_READERS


def _refresh_paddle_tables(result, pdf_path):
    """Rebuild derived geometry without repeating page OCR after a layout fix."""
    if len(result.page_transforms)!=len(result.pages):raise ValueError('Missing cached page transforms')
    tables=[]
    for page in range(len(result.pages)):
        words=[w for w in result.words if w.page==page]
        img=_cached_page_image(pdf_path,page,dpi=result.dpi,transform=result.page_transforms[page])
        rebuilt=_grid_tables(img,words,page)
        _reread_paddle_quantities(img,rebuilt,_paddle_readers()[0])
        tables.extend(rebuilt)
    result.tables=tables
    result.table_version=5
    return result


def analyze_with_paddle(pdf_path: Path, max_pages=None, page_cache_dir=None) -> OCRResult:
    """Local lightweight OCR; reuse the same table recovery and invoice parser."""
    import numpy as np
    import pymupdf
    with pymupdf.open(pdf_path) as doc:
        total_pages=len(doc)
    result=OCRResult(backend='paddle',total_pages=total_pages,dpi=300,table_version=5)
    for page,img in _pdf_to_images(pdf_path,dpi=300,max_pages=max_pages):
        checkpoint=page_cache_dir/f'{page}.json' if page_cache_dir else None
        saved=None
        if checkpoint and checkpoint.exists():
            try:
                raw=json.loads(checkpoint.read_text(encoding='utf-8'))
                saved=(raw['content'],[OCRWord(**w) for w in raw['words']],
                       [OCRTable(**{**t,'cells':[OCRTableCell(**c) for c in t['cells']]}) for t in raw['tables']],raw['transform'])
                if not isinstance(saved[0],str) or not {'rotation','skew'}<=saved[3].keys():
                    raise ValueError('Invalid page checkpoint')
                if raw.get('table_version')!=5:
                    content,words,_,transform=saved
                    img=_cached_page_image(pdf_path,page,dpi=300,transform=transform)
                    tables=_grid_tables(img,words,page)
                    _reread_paddle_quantities(img,tables,_paddle_readers()[0])
                    saved=(content,words,tables,transform)
            except (OSError,ValueError,KeyError,TypeError,AttributeError):saved=None
        if saved is not None:
            content,words,tables,transform=saved
        else:
            reader,orientation=_paddle_readers()
            prediction=next(iter(orientation.predict(np.array(img)[:,:,::-1])))
            angle=int(prediction['label_names'][0])
            if angle not in (0,90,180,270):raise ValueError('Unexpected page orientation')
            img=img.rotate(angle,expand=True)
            skew=_skew_angle(img)
            img=img.rotate(skew,expand=False,fillcolor='white')
            transform={'rotation':angle,'skew':skew}
            raw=next(iter(reader.predict(np.array(img)[:,:,::-1])))
            texts,scores,boxes=raw['rec_texts'],raw['rec_scores'],raw['rec_boxes']
            if not len(texts)==len(scores)==len(boxes):raise ValueError('Inconsistent OCR text and boxes')
            words=[OCRWord(t.strip(),float(s),*[float(v) for v in b],page)
                   for t,s,b in zip(texts,scores,boxes) if t.strip()]
            tables=_grid_tables(img,words,page)
            _reread_paddle_quantities(img,tables,reader)
            content='\n'.join(_cluster_into_lines(words,max(3,median(w.y1-w.y0 for w in words)*.45) if words else 8))
            if checkpoint:
                checkpoint.parent.mkdir(parents=True,exist_ok=True)
                temporary=checkpoint.with_suffix('.tmp')
                temporary.write_text(json.dumps({'content':content,'words':[asdict(w) for w in words],
                    'tables':[asdict(t) for t in tables],'transform':transform,'table_version':5}),encoding='utf-8')
                temporary.replace(checkpoint)
            print(f'  OCR {pdf_path.name}: page {page+1}, rotation {angle}, {len(words)} boxes',flush=True)
        result.pages.append(content)
        result.words.extend(words)
        result.tables.extend(tables)
        result.page_transforms.append(transform)
        emit('ocr_page', page=page+1, cached=saved is not None, transform=transform,
             words=len(words), tables=len(tables), dpi=300)
    result.content='\n\n--- PAGE BREAK ---\n\n'.join(result.pages)
    if len(result.pages)<total_pages:result.warnings.append('Page limit excluded source pages.')
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_pdf(pdf_path: Path, max_pages: int | None = None, cache_dir: Path | None = None) -> OCRResult:
    """Read local PaddleOCR evidence, reusing source-keyed caches when available."""
    if max_pages is not None and max_pages < 1:
        raise ValueError('max_pages must be a positive integer')
    cache=None
    if cache_dir:
        settings=f'paddle-mobile-v1:3.7.0:3.2.0:{max_pages}:300'.encode()
        digest=hashlib.sha256(pdf_path.read_bytes()+settings).hexdigest()
        cache=Path(cache_dir)/f'{digest}.json'
        try:
            raw=json.loads(cache.read_text(encoding='utf-8'))
            raw['words']=[OCRWord(**v) for v in raw['words']]
            raw['tables']=[OCRTable(**{**t,'cells':[OCRTableCell(**c) for c in t['cells']]}) for t in raw['tables']]
            result=OCRResult(**raw)
        except (OSError,ValueError,KeyError,TypeError):result=None
        if result is not None:
            if result.table_version!=5:
                result=_refresh_paddle_tables(result,pdf_path)
                temporary=cache.with_suffix('.tmp')
                temporary.write_text(json.dumps(asdict(result),ensure_ascii=False),encoding='utf-8')
                temporary.replace(cache)
            emit('ocr_cache', cached=True, pages=len(result.pages), table_version=result.table_version)
            return result
    emit('ocr_cache', cached=False)
    result=analyze_with_paddle(pdf_path,max_pages=max_pages,page_cache_dir=cache.with_suffix('') if cache else None)
    if cache:
        cache.parent.mkdir(parents=True,exist_ok=True)
        temporary=cache.with_suffix('.tmp')
        temporary.write_text(json.dumps(asdict(result),ensure_ascii=False),encoding='utf-8')
        temporary.replace(cache)
    return result
