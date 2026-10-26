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
from dataclasses import asdict, dataclass, field, replace
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


def _grid_tables(img, words, page, *, min_vertical=0):
    """Recover ruled packing-list cells using existing OpenCV and OCR boxes."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(np.array(img.convert('RGB')), cv2.COLOR_RGB2GRAY)
    ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    h, w = gray.shape
    def positions(vertical, relaxed=False):
        kernel = (1, max(25, h // 12, min_vertical)) if vertical else (max(25, w // 3), 1)
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


def _recover_shipped_tables(result, pdf_path):
    """Recover compact packing grids with separate shipped-quantity/unit columns."""
    from .parser import _table_fields
    recovered=[]
    for page, content in enumerate(result.pages):
        if not re.search(r'PACKING\s*LIST', content, re.I):continue
        if any(t.page==page and _table_fields(t)[0] for t in result.tables):continue
        words=[w for w in result.words if w.page==page and w.y1>w.y0]
        shipped=[w for w in words if re.fullmatch(r'SHIPPED(?:\s+QTY)?',w.text.strip(),re.I)]
        if len(shipped)!=1:continue
        anchor=shipped[0]
        height=median(w.y1-w.y0 for w in words)
        headers=[w for w in words if abs(w.y0-anchor.y0)<height*2]
        if not any(re.fullmatch('DESCRIPTION',w.text.strip(),re.I) for w in headers):continue
        if not any(re.fullmatch(r'\(?UNIT\)?',w.text.strip(),re.I) for w in headers):continue
        endings=[w.y0 for w in words if w.y0>anchor.y1+height and
                 re.match(r'^(?:TOTAL\s*:|SHORT\s+SHIPMENT\b)',w.text.strip(),re.I)]
        if not endings:continue
        top=max(0,int(min(w.y0 for w in headers)-height*2))
        bottom=int(min(endings))
        transform=result.page_transforms[page] if page<len(result.page_transforms) else None
        image=_cached_page_image(pdf_path,page,result.dpi,transform)
        local=[replace(w,y0=w.y0-top,y1=w.y1-top) for w in words
               if top<=(w.y0+w.y1)/2<bottom]
        candidates=_grid_tables(image.crop((0,top,image.width,bottom)),local,page,
                                min_vertical=round(height*3))
        for table in candidates:
            for row in range(table.row_count):
                cells=[c for c in table.cells if c.row_index==row and c.bbox]
                desc=[c for c in cells if re.fullmatch('DESCRIPTION',c.content.strip(),re.I)]
                qty=[c for c in cells if re.fullmatch(r'SHIPPED\s+QTY\.?',c.content.strip(),re.I)]
                units=[c for c in cells if re.fullmatch(r'\(?UNIT\)?',c.content.strip(),re.I)]
                if not (len(desc)==len(qty)==len(units)==1):continue
                desc,qty,unit=desc[0],qty[0],units[0]
                if not (desc.column_index+1==qty.column_index and qty.column_index+1==unit.column_index):continue
                output=[replace(desc,row_index=0,column_index=0,content='DESCRIPTION',
                                bbox=[desc.bbox[0],desc.bbox[1]+top,desc.bbox[2],desc.bbox[3]+top]),
                        OCRTableCell(0,1,'QTY (SHIPPED) / UNIT',page,
                                     [qty.bbox[0],qty.bbox[1]+top,unit.bbox[2],unit.bbox[3]+top],
                                     original_content=qty.content+' / '+unit.content)]
                for body_row in range(row+1,table.row_count):
                    description=next((c for c in table.cells if c.row_index==body_row and
                                      c.column_index==desc.column_index and c.bbox),None)
                    if description is None:continue
                    left,yt,right,yb=description.bbox
                    if re.match(r'^(?:TOTAL\b|SHORT\s+SHIPMENT\b)',description.content,re.I):break
                    selected=[w for w in local if qty.bbox[0]<=(w.x0+w.x1)/2<unit.bbox[2]
                              and yt<=(w.y0+w.y1)/2<yb]
                    value='\n'.join(_cluster_into_lines(selected,max(3,height*.45)))
                    index=len(output)//2
                    output.extend([replace(description,row_index=index,column_index=0,
                                           bbox=[left,yt+top,right,yb+top]),
                                   OCRTableCell(index,1,value,page,
                                                [qty.bbox[0],yt+top,unit.bbox[2],yb+top],
                                                min((w.confidence for w in selected),default=None))])
                if len(output)<=2:continue
                box=[desc.bbox[0],desc.bbox[1]+top,unit.bbox[2],table.bbox[3]+top]
                recovered.append(OCRTable(output,len(output)//2,2,page,box))
                emit('ocr_table_recovery',page=page+1,method='ruled_shipped_quantity_and_unit',
                     rows=len(output)//2-1,bbox=box)
                break
    if recovered:
        # Superseded geometry must not enter the unstructured fallback a second time.
        retained=[t for t in result.tables if not any(t.page==r.page and t.bbox and
                  t.bbox[0]<r.bbox[2] and r.bbox[0]<t.bbox[2] and
                  t.bbox[1]<r.bbox[3] and r.bbox[1]<t.bbox[3] for r in recovered)]
        result.tables=sorted(retained+recovered,key=lambda t:(t.page,(t.bbox or [0,0])[1]))
    return bool(recovered)


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


def _column_regions(image, box, quantity_cells, words, page, group_braces=False, extra_points=()):
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
    points+=list(extra_points)
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


def _packing_column_regions(image, box, table, columns, header, words, group_braces=False):
    """Include declarations above quantity rows, preserving physical shared cells."""
    quantities=[c for c in table.cells if c.row_index>header and c.column_index==columns['quantity']
                and c.content.strip() and c.bbox and not any(
                    re.match(r'^(?:SUB[ -]?)?TOTAL\b',d.content.strip(),re.I)
                    for d in table.cells if d.row_index==c.row_index)]
    left,top,right,bottom=box
    totals=[c.bbox[1] for c in table.cells if c.row_index>header and c.bbox and
            re.match(r'^(?:SUB[ -]?)?TOTAL\b',c.content.strip(),re.I)]
    bottom=min([bottom]+totals)
    box=[left,top,right,bottom]
    declarations=[(w.y0+w.y1)/2 for w in words if w.page==table.page and re.search(r'\d',w.text)
                  and left<=(w.x0+w.x1)/2<right and top<=(w.y0+w.y1)/2<bottom]
    descriptions={c.row_index:c.content for c in table.cells if c.column_index==columns['description']}
    if quantities and declarations and min(declarations)<min(c.bbox[1] for c in quantities) and all(
            re.match(r'^\s*COL(?:OU?R)?[. :]',descriptions.get(c.row_index,''),re.I) for c in quantities):
        quantities=[]  # A declared heading weight/package covers its colour continuations.
    return _column_regions(image,box,quantities,words,table.page,group_braces,extra_points=declarations)


def _shipment_cover(text):
    return bool(re.search(r'\bSHIPPER\b',text,re.I) and re.search(r'\bCONSIGNEE\b|\bPACKAGES\b',text,re.I))


def _packing_footer(ocr,page,field):
    """Read a labelled local total only on the compact shipped-quantity packing form."""
    from .parser import NUM, _number
    text=ocr.pages[page]
    if not (re.search(r'PACKING\s+LIST',text,re.I) and re.search(r'\bSHIPPED\b',text,re.I)):
        return None
    if field=='package_count' and not re.search(r'\bPKGS?\b|\bPACKAGES?\b',text,re.I):return None
    pattern=(rf'^\s*TOTAL\s+GROSS\s+WEIGHT[^\d\n]*({NUM})\s*KGS?\b[^\n]*$'
             if field=='gross_weight_kg' else r'^\s*TOTAL\s*:\s*([1-9]\d{0,3})\s*$')
    matches=list(re.finditer(pattern,text,re.I|re.M))
    if len(matches)!=1:return None
    value=_number(matches[0][1])
    return {'page':page+1,'text':matches[0][0].strip(),'value':value,'method':'labelled local packing total'} if 0<value<float('inf') else None


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
            changed=False
            if result.table_version!=5:
                result=_refresh_paddle_tables(result,pdf_path)
                changed=True
            changed=_recover_shipped_tables(result,pdf_path) or changed
            if changed:
                temporary=cache.with_suffix('.tmp')
                temporary.write_text(json.dumps(asdict(result),ensure_ascii=False),encoding='utf-8')
                temporary.replace(cache)
            emit('ocr_cache', cached=True, pages=len(result.pages), table_version=result.table_version)
            return result
    emit('ocr_cache', cached=False)
    result=analyze_with_paddle(pdf_path,max_pages=max_pages,page_cache_dir=cache.with_suffix('') if cache else None)
    _recover_shipped_tables(result,pdf_path)
    if cache:
        cache.parent.mkdir(parents=True,exist_ok=True)
        temporary=cache.with_suffix('.tmp')
        temporary.write_text(json.dumps(asdict(result),ensure_ascii=False),encoding='utf-8')
        temporary.replace(cache)
    return result
