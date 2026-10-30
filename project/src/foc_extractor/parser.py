"""
Parser module: Extracts structured FOCData from OCR text.

Works with the unified OCRResult from ocr_engine.py.
Handles all template types: BD (EGMCL/PGCL), India (TGPL), Jordan (EJU1).

Extraction strategy:
  1. Header fields â€” source blocks & regex with OCR tolerance
  2. Line items    â€” recovered tables or regex-based line item parsing
  3. Validation    â€” cross-checks package counts, carton numbers, and totals
"""

from .processing_evidence import emit
import re
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .models import FOCData, LineItem

# Numbers have no nested captures; quantity and unit are named explicitly.
NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+,\d+|\d+(?:[.,]\d+)?)"
UNITS = r"YARDS?|YDS?|YS?|PIECES?|PCS?|SETS?|GROSS|GRS|CONES?|ROLLS?|MTRS?|METERS?|PACKS?|G"
PACKAGE_UNIT = r'PACK(?:AGE)?(?:\(?S\)?)?|PKGS?|PKS?|CTNS?|CARTONS?|ROLLS?|BAGS?|BOX(?:ES)?'
QTY_UNIT = re.compile(rf"(?<![\w.,+\-])(?P<qty>{NUM})\s*(?P<unit>{UNITS})\b", re.I)


def _normalize_unit(unit):
    u = unit.upper().strip()
    return {'Y':'YDS','YS':'YDS','YD':'YDS','YARD':'YDS','YARDS':'YDS','PC':'PCS','PIECE':'PCS',
            'PIECES':'PCS','SET':'SETS','GRS':'GROSS','CONE':'CONES',
            'ROLL':'ROLLS','MTR':'MTRS','METER':'MTRS','METERS':'MTRS','PACK':'PACKS'}.get(u, u)


def _number(s):
    if ',' in s and '.' in s and s.rfind(',') > s.rfind('.'):
        return float(s.replace('.', '').replace(',', '.'))
    if ',' in s and '.' not in s and not re.fullmatch(r'\d{1,3}(?:,\d{3})+', s):
        return float(s.replace(',', '.'))
    return float(s.replace(',', ''))


def _quantity_text(text):
    text=re.sub(rf'(?<=\d)\s*·\s*(?=(?:{UNITS})\b)', ' ',text,flags=re.I)
    text=re.sub(r'\b[Iil](?=\s*(?:PCS?\b|YDS\b|SETS?\b))','1',text,flags=re.I)
    text=re.sub(r'(?<=\d)\s*(?:VD[S:]?|Y[O0][S5])\b',' YDS',text,flags=re.I)
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    quantities=[(line,QTY_UNIT.fullmatch(line)) for line in lines if QTY_UNIT.fullmatch(line)]
    if len(quantities)==1 and len(lines)>1:
        value,match=quantities[0]
        if all(line==value or (re.fullmatch(UNITS,line,re.I) and _normalize_unit(line)==_normalize_unit(match['unit'])) for line in lines):
            return value
    expression=re.fullmatch(rf'\s*({NUM})\s*({UNITS})\s*[x×*]\s*([1-9]\d*)\s*(=?)\s*({NUM})\s*({UNITS})\s*(=?)\s*',text,re.I)
    if expression and len(expression[4]+expression[7])==1:
        left,right=(Decimal(str(_number(expression[n]))) for n in (1,5))
        if (left.is_finite() and right.is_finite() and left>0 and right>0
                and _normalize_unit(expression[2])==_normalize_unit(expression[6])
                and left*Decimal(expression[3])==right):
            return expression[5]+' '+_normalize_unit(expression[6])
    return text


def _extract_invoice_number(text):
    text=re.sub(r'[\\⁄／]','/',text)
    candidates=[f'S/{n}/{y}' for n,y in re.findall(r'\b[S58]\s*/\s*(\d{3,5})\s*/\s*(\d{2})\b',text,re.I)]
    return Counter(candidates).most_common(1)[0][0] if candidates else None


def _date_candidates(text, month_first=False):
    from datetime import date, datetime
    text=re.sub(r'\b0CT\b','OCT',text,flags=re.I)
    months = {m:i+1 for i,m in enumerate('JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split())}
    values=set()
    for value in re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text):
        try:values.add(date.fromisoformat(value).isoformat())
        except ValueError:pass
    patterns = [r'ON/ABT\.?\s*([A-Z]{3})[A-Z]*[.\s-]*(\d{1,2})[,\s-]+(\d{4})',
                r'\b(\d{1,2})[-\s]+([A-Z]{3})[A-Z]*[,.\s-]+(\d{4}|\d{2})\b']
    for idx,pattern in enumerate(patterns):
        for m in re.finditer(pattern,text.upper()):
            a,b,y=m.groups(); month,day=(months.get(a),b) if idx==0 else (months.get(b),a)
            try:values.add(date(int(y) if len(y)==4 else datetime.strptime(y,'%y').year,month,int(day)).isoformat())
            except (ValueError,TypeError):continue
    for a,b,y in re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',text):
        a,b,y=int(a),int(b),int(y)
        # Packing-list forms use month/day/year; explicit export dates stay strict.
        for month,day in (((a,b),) if month_first else ((a,b),(b,a))):
            try:values.add(date(y,month,day).isoformat())
            except ValueError:pass
    return values


def _parse_date(text):
    values=_date_candidates(text)
    return next(iter(values)) if len(values)==1 else None


EXPORT_DATE_LABEL=r'(?:DATE\s+OF\s+EXPORT(?:ATION)?|EXPORT\s+DATE|ON\s*/\s*ABT\.?)'


def _extract_export_date(text):
    labelled=re.findall(EXPORT_DATE_LABEL+r'\s*[:.-]?\s*((?:\d|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)[A-Z]*\b)[^\n]*)',text,re.I)
    values={_parse_date('ON/ABT '+value) for value in labelled}
    return next(iter(values)) if len(values)==1 else None


def _extract_packing_date(pages):
    for page in pages:
        if not re.search(r'\bPACKING\s+LIST\b',page,re.I):continue
        values=re.findall(r'\b(?:PACKING\s+)?DATE[ \t]*:[ \t]*([^\n]*)',page,re.I)
        if not values:continue
        candidates=[_date_candidates('ON/ABT '+value,month_first=True) for value in values]
        dates=set.intersection(*candidates)
        # Later enclosures may have their own dates; use the first dated packing page.
        return next(iter(dates)) if len(dates)==1 else None
    return None


def _extract_carton_range(text):
    ranges=[]
    # Correct O only inside a labelled carton number, never in style codes.
    text=re.sub(r'(C\s*[/I1]?\s*NO[.:]?[^\n]*)',lambda m:re.sub(r'(?<=[0-9])O\b','0',m[0]),text.upper())
    for m in re.finditer(r'C\s*[/I1]?\s*NO[.:]?\s*([A-Z]\s*\d{1,3})(?:(?:[ \t]*[-â€“][ \t]*|[ \t]+(?=[A-Z]\d))([A-Z]?\s*\d{1,3}))?',text):
        first=re.sub(r'\s','',m[1]); last=re.sub(r'\s','',m[2] or '')
        if last:
            if last[0].isdigit():last=first[0]+last
            if first[0]!=last[0] or int(first[1:])>int(last[1:]):continue
        ranges.append(first+('-'+last if last else ''))
    return ', '.join(dict.fromkeys(ranges)) or None


def _carton_count(value):
    cartons=set()
    for part in (value or '').split(', '):
        m=re.fullmatch(r'([A-Z])(\d+)(?:-([A-Z])(\d+))?',part)
        if m:
            end=int(m[4] or m[2])
            if end-int(m[2])>999:return None
            cartons.update((m[1],n) for n in range(int(m[2]),end+1))
    return len(cartons) or None


def _extract_shipping_marks(text):
    text=re.sub(r'\bF\s*\.\s*O\s*\.\s*C\s*\.?', 'FOC',text,flags=re.I)
    match=re.search(r'\b([A-Z]{2,8})([ \t-]+\d{1,2})?[ \t-]*(FOC|FABRIC|GMT)\b',text.upper())
    if not match:return None
    return match[1]+((' '+match[2].strip(' -')) if match[2] else '')+'-'+match[3]


def _extract_package_count(text):
    pattern=r'\b(\d{1,4})[ \t]*(?:'+PACKAGE_UNIT+r')(?![A-Z])'
    totals=re.findall(r'\bTOTAL\s*:?\s*'+pattern,text.upper())
    values=list(dict.fromkeys(totals)) if totals else re.findall(pattern,text.upper())
    return int(values[0]) if len(values)==1 else None


def _extract_gross_weight(text):
    patterns=[rf'(?:\bG\.?\s*W\.?|GROSS\s+WEIGHT)\s*:?\s*({NUM})\s*KGS?\b']
    if 'SHIPPER' in text.upper() and 'PACKAGES' in text.upper():
        patterns.append(rf'\b(?:APP|EST)\s*\.?\s*:?\s*({NUM})\s*KGS?\b')
    values={_number(v) for p in patterns for v in re.findall(p,text.upper())}
    return next(iter(values)) if len(values)==1 else None


def _shipment_summary(ocr):
    from .ocr_engine import _shipment_cover
    pages=ocr.pages or [ocr.content]
    covers=[p for p in pages if _shipment_cover(p)]
    return '\n'.join(covers) if covers else (pages[0] if not re.search(r'PACKING\s+LIST',pages[0],re.I) else '')


def _extract_net_weight(text):
    values={_number(v) for v in re.findall(
        rf'(?:\bN\.?\s*W\.?|NET\s+WEIGHT)\s*:?\s*({NUM})\s*KGS?\b', text.upper())}
    return next(iter(values)) if len(values)==1 and next(iter(values)) > 0 else None


def _extract_total_value(text):
    values={_number(v) for v in re.findall(rf'TOTAL\s+VALUE\s*:?\s*(?:USD\s*|\$\s*)?({NUM})',text.upper())}
    return next(iter(values)) if len(values)==1 else None


def _repair_goods_text(text):
    # Percent-sign glyph errors are repaired only beside an explicit fiber name.
    text=re.sub(r'\b[1I][0O]{2}(?:Z[0O]?|T|%[0O])\s+(?=(?:COTTON|COTON|OTTON)\b)',
                '100% ',text,flags=re.I)
    text=re.sub(r'(?<=100% )(?:(?:COTON)|OTTON)\b','COTTON',text,flags=re.I)
    return re.sub(r'\bKIPS(?=\s+100%\s+COTTON)','KIDS',text,flags=re.I)


def _fabric_sample_note(text):
    """Recover the broad category from FAB notes without inventing their subtype."""
    return bool(re.search(r'\bFA[BRP]\s+[A-Z]{5,12}\b',text.upper()))


def _fabric_sample_category(text):
    if re.search(r'\bFAB(?:RIC)?\s+SWATCH(?:ES)?\b',text,re.I):return 'FABRIC SWATCHES'
    if re.search(r'\bFAB(?:RIC)?\s+SAMPLES?\b',text,re.I):return 'FABRIC SAMPLES'
    return 'FABRIC SAMPLES' if _fabric_sample_note(text) else None


def _clean_material_description(raw_desc):
    """Normalize source text without converting garments to fabric or losing blends."""
    s=re.sub(r'\s+',' ',_repair_goods_text(raw_desc)).strip().upper()
    s=re.sub(r'(\d)\s*%\s*',r'\1% ',s)
    s=re.sub(r'\bFABRICS? SWATCH(?:ES)?\b','FABRIC SWATCHES',s)
    s=re.sub(r'\bWOVEN FABRIC\b','WOVEN FABRICS',s)
    s=re.sub(r'\bKNIT FABRIC\b','KNIT FABRICS',s)
    s=re.sub(r'^\d+[).]\s+','',s)
    s=re.sub(r'\bMOOULD\b','MOULD',s)
    s=re.sub(r'\bMEATAL SNAP\b','METAL SNAP',s)
    s=re.sub(r'\b(SHANK|RIVET|SNAP)DIE\b',r'\1 DIE',s)
    garment=re.match(r"^(WOVEN|KNIT(?:TED)?)\s+((?:MEN|WOMEN)'?S?|LADIES|KIDS?)\s+(PANTS?|SHIRTS?|DRESS(?:ES)?|BLOUSES?|JACKETS?)\s*[-:]\s*(.+)",s)
    if garment:
        composition=_material_heading(garment[4],garment[1])
        if composition:
            return f'{garment[2]} {composition.removesuffix(" FABRICS")} {garment[3]}'
    if re.match(r'^SHANK\s*&\s*RIVET\s*-?\s*\d+(?:\.\d+)?G\s+EACH ITEM\b',s):return 'SHANK & RIVET'
    if re.search(r'\bDIE\s+MOULD\b',s):
        kinds=set(re.findall(r'\bSNAP|\bSHANK|\bRIVET',s))
        if len(kinds)==1:return f'DIE MOULD ({next(iter(kinds))})'
    if re.search(r'\bFABRIC SWATCHES CARD\b',s):return 'FABRIC SWATCHES CARD'
    if re.search(r'\bSWATCH(?:ES)?\b',s) and (re.search(r'\bFABRICS?\b',s) or (
            re.search(r'\bCOLOU?R STANDARD\b',s) and re.search(
                r'\b(?:POPLIN|COTTON|LINEN|NYLON|POLYESTER|DENIM|TROUSERS?|SHORTS?|SHIRTS?|BLOUSES?)\b',s))):
        return 'FABRIC SWATCHES'
    if re.search(r'\bBULK TRIMS? CARD\b',s):return 'BULK TRIM CARD'
    if re.search(r'\bTRIMS? CARD\b',s):return 'TRIM CARD'
    if re.search(r'\bSIZE STICKER\b',s):return 'SIZE STICKER'
    if re.search(r'\bEC\s+SAMPLE\s+LACE\b',s):return 'EC SAMPLE LACE'
    if re.search(r'\bFELT PATCH\b',s):return 'FELT PATCH'
    if re.match(r'^BULK FABRIC BLANKET\b',s):return 'BULK FABRIC BLANKET'
    if re.match(r'^TAPER CARD\b',s):return 'TAPER CARD'
    if re.fullmatch(r'(?:CSI\s+)?FAB\s+[A-Z]{5,12}(?:\s+\d+ COLOU?RS?.*)?',s):return 'FABRIC SAMPLES'
    # Composition starts after supplier/style metadata. Keep the complete blend.
    comp=re.search(r'\b\d{1,3}\s*%',s)
    if comp:
        material=s[comp.start():]
        # Some garment cells put their category before the composition.
        prefix=s[:comp.start()]
        category=re.search(r'\b(MENS?|WOMENS?|LADIES|LADY|KIDS?|GIRLS?|BOYS?)\s+(WOVEN|KNIT(?:TED)?)\b',prefix)
        garments=set(re.findall(r'\b(?:SHIRTS?|PANTS?|SHORTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?)\b',prefix))
        if category and len(garments)==1 and not re.search(r'\bFABRICS?\b',s):
            composition=_material_heading(material)
            if composition:
                return f'{composition} {category[1]} {category[2]} {next(iter(garments))}'
        end=re.search(r'\b(?:WOVEN|KNIT(?:TED)?)\s+(?:FABRICS?|SHIRTS?|PANTS?|SHORTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?)\b',material)
        percentages=[int(v) for v in re.findall(r'(\d{1,3})\s*%',material)]
        if end and sum(percentages)==100:
            prefix=s[:comp.start()]
            garment=re.search(r"(?<![A-Z])((?:MEN|WOMEN)'?S?|LADIES|LADY|KIDS?)\s*$",prefix)
            return ((garment[1]+' ') if garment else '')+material[:end.end()]
    style=re.fullmatch(r'STYLE\s*[:#]\s*[A-Z0-9-]+\s+(.+\b(?:DRESS|SHIRT|PANTS|BLOUSE|JACKET))',s)
    return style[1] if style else s


def _material_headings(text, fabric_type=''):
    text=re.sub(r'\(\s*BW\s*\+/-\s*\d+(?:\.\d+)?\s*%\s*\)','',text,flags=re.I)
    text=re.sub(r'\b\d+(?:\s*[Xx*]\s*\d+)?\s*%\s*SHRINKAGE\b','',text,flags=re.I)
    text=re.sub(r'\b\d+\s*[Xx*]\s*\d+\s*%','',text)
    text=re.sub(r'\bI?SHRINKAGE\s*:?\s*[^\n]*','',text.upper())
    # Letter-shaped digits are repaired only inside an explicit percentage token.
    text=re.sub(r'\b[0-9IO]{1,3}(?=\s*%)',lambda m:m[0].translate(str.maketrans('IO','10')),text)
    text=re.sub(r'\s+',' ',text)
    text=re.sub(r'%\s*/','%',text)
    text=re.sub(r'\bPOLY\b','POLYESTER',text)
    text=re.sub(r'\bGENERIC\s+(?=RECYCLED)','',text)
    text=re.sub(r'\s*\(BC[IL1]\)','',text)
    text=re.sub(r'\bBC[IL1]\s+(?=COTTON\b)','',text)
    text=re.sub(r'\bRECYCLE\s+(?=POLYESTER\b)','RECYCLED ',text)
    fibers=r'(?:PCW RECYCLED |GRS |RECYCLED |RECYCLE |ORGANIC |BCI |USA? )?(?:VISCOSE RAYON|COTTON|POLYESTER|POLYAMIDE|NYLON|WOOL|ELASTANE|SPANDEX|LYOCELL|VISCOSE|RAYON|LINEN|SILK|METALLIC|TENCEL|STRETCH|OTHERS)'
    matches=list(re.finditer(rf'\d{{1,3}}\s*%\s*{fibers}(?![A-Z])',text))
    kind=re.search(r'\b(WOVEN|KNIT(?:TED)?)\b',fabric_type+' '+text.upper())
    if not matches:return []
    if not fabric_type and not re.search(r'\bFABRICS?\b',text) and re.search(r'\b(?:SHIRTS?|PANTS?|SHORTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?)\b',text):return []
    if len(matches)!=len(re.findall(r'\d+(?:\.\d+)?\s*%',text)):return []
    groups=[]
    for match in matches:
        if groups and not text[groups[-1][-1].end():match.start()].strip(' ,/&+'):
            groups[-1].append(match)
        else:groups.append([match])
    headings=[]
    for group in groups:
        after=text[group[-1].end():]
        if re.match(r'[ ,/&+]*\d+(?:\.\d+)?\s*%',after):return []
        if sum(int(re.match(r'\d+',m[0])[0]) for m in group)!=100:return []
        if re.match(r'\s*(?:(?:MENS?|WOMENS?|LADIES|LADY|KIDS?|GIRLS?|BOYS?)\s+)?(?:(?:WOVEN|KNIT(?:TED)?)\s+)?(?:SHIRTS?|PANTS?|SHORTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?)\b',after):return []
        composition=' '.join(re.sub(r'\s*%\s*','% ',m[0]) for m in group)
        headings.append(composition+(' '+('KNIT' if kind[1].startswith('KNIT') else 'WOVEN')+' FABRICS' if kind else ''))
    return headings


def _material_heading(text, fabric_type=''):
    headings=set(_material_headings(text,fabric_type))
    return next(iter(headings)) if len(headings)==1 else None


def _extract_items_from_text(text):
    items=[]
    for line in text.splitlines():
        if re.search(r'SHIPPER|CONSIGNEE|TOTAL|INVOICE|PACKING LIST|PARTICULARS|BUYER|FOC\b',line,re.I):continue
        m=QTY_UNIT.search(line)
        if m and len(line[:m.start()].strip())>=3:
            desc=line[:m.start()].strip()
            if _normalize_unit(m['unit']) in ('ROLLS','PACKS') and re.search(r'(?<![A-Z])KGS?\b',desc,re.I):continue
            items.append(LineItem(desc,_number(m['qty']),_normalize_unit(m['unit'])))
    return items


def _table_fields(table):
    """Find columns by labels, not fixed sample-specific column indices."""
    for row in sorted({c.row_index for c in table.cells}):
        columns={}
        for c in table.cells:
            if c.row_index!=row:continue
            t=re.sub(r'\s+',' ',c.content.upper())
            for name,pattern in [('description',r'PAR[TIL]IC[UV]LAR|DESCRIPTION'),('quantity',r'^Q[TI][YX]|QUANTITY'),
                                 ('item',r'^I[TIL]?EMS?$'),('purpose',r'^PURP'),
                                 ('weight',r'WEIGH[TIL]|WEGHT|^KGS$'),('packages',r'NO[ ._]*OF[ _]*PACK|PACKAGE[ /]|NO OF ROLL'),
                                 ('fabric_type',r'W[OQ]VEN.*KNI'),('sender',r'SENDE[RB]|SENDED')]:
                if re.search(pattern,t):columns[name]=c.column_index
        if columns.get('packages') is not None and columns.get('packages')==columns.get('weight'):
            following=[c.column_index for c in table.cells if c.row_index==row and c.column_index>columns['weight']
                       and re.search(r'\bROLLS?\b|\bPACKAGES?\b',c.content,re.I)]
            if following:columns['packages']=min(following)
        if ('quantity' not in columns or columns.get('quantity')==columns.get('weight')) and {'description','weight'}<=columns.keys():
            candidate=columns['weight']-1
            values=[c.content for c in table.cells if c.row_index>row and c.column_index==candidate]
            if candidate>columns['description'] and any(QTY_UNIT.search(_quantity_text(v)) for v in values):columns['quantity']=candidate
            elif columns.get('quantity')==columns['weight']:columns.pop('quantity',None)
        if {'description','quantity'}<=columns.keys():return columns,row
    return {},-1


def _quantity_descriptions(ocr,table,row,columns,matches,source_ref):
    """Recover merged item rows only when source positions corroborate every quantity."""
    from .ocr_engine import _cluster_into_lines
    cells={c.column_index:c for c in table.cells if c.row_index==row}
    description=cells.get(columns['description']);quantity=cells.get(columns['quantity'])
    if not description or not description.bbox or not quantity or not quantity.bbox:return []
    left,top,right,bottom=quantity.bbox
    words=[w for w in ocr.words if w.page==table.page and left<=(w.x0+w.x1)/2<right
           and top<=(w.y0+w.y1)/2<bottom]
    anchors=[]
    for word in sorted(words,key=lambda w:(w.y0,w.x0)):
        reading=QTY_UNIT.fullmatch(_quantity_text(word.text))
        if not reading and re.fullmatch(NUM,word.text.strip()):
            line=[w for w in words if abs((w.y0+w.y1-word.y0-word.y1)/2)
                  <=min(w.y1-w.y0,word.y1-word.y0)/2]
            reading=QTY_UNIT.fullmatch(_quantity_text(' '.join(w.text for w in sorted(line,key=lambda w:w.x0))))
        if reading:anchors.append((word,reading))
    if len(anchors)!=len(matches):return []
    if any(a[0].y1>=b[0].y0 for a,b in zip(anchors,anchors[1:])):return []
    if any((_number(a['qty']),_normalize_unit(a['unit']))!=(_number(b['qty']),_normalize_unit(b['unit']))
           for (_,a),b in zip(anchors,matches)):return []
    left,top,right,bottom=description.bbox
    boundaries=[top,*[(a.y0+a.y1+b.y0+b.y1)/4 for (a,_),(b,_) in zip(anchors,anchors[1:])],bottom]
    words=[w for w in ocr.words if w.page==table.page and left<=(w.x0+w.x1)/2<right
           and top<=(w.y0+w.y1)/2<bottom]
    if any(w.y0<boundary<w.y1 for w in words for boundary in boundaries[1:-1]):return []
    descriptions=[];entries=[]
    for start,end,(_,match) in zip(boundaries,boundaries[1:],anchors):
        selected=[w for w in words if start<=(w.y0+w.y1)/2<end]
        text='\n'.join(_cluster_into_lines(selected))
        if not text.strip() or re.match(r'\s*(?:SUB[ -]?)?TOTAL\b',text,re.I):return []
        descriptions.append(text)
        entries.append({'bbox':[left,start,right,end],'description':text,
                        'quantity':_number(match['qty']),'unit':_normalize_unit(match['unit'])})
    emit('field_evidence',field='goods_quantity',source_ref=source_ref,page=table.page+1,
         evidence={'method':'physical_quantity_rows','entries':entries})
    return descriptions


def _extract_table_data(ocr):
    items=[]; weights=[]; parsed_pages=set(); warnings=[]
    continuation_sources={}
    category_sources={}
    for table_index,table in enumerate(ocr.tables):
        table_start=len(items)
        cols,header=_table_fields(table)
        if not {'description','quantity'}<=cols.keys():
            warnings.append(f'Page {table.page+1}: table columns not established.')
            continue
        rows={}
        for c in table.cells:rows.setdefault(c.row_index,{})[c.column_index]=c.content
        # Join a percentage continuation only when it completes one valid blend.
        ordered=sorted(r for r in rows if r>header)
        for first,second in zip(ordered,ordered[1:]):
            a,b=rows[first],rows[second]
            text=a.get(cols['description'],'')
            tail=b.get(cols['description'],'')
            kind=a.get(cols.get('fabric_type',-1),'')
            joined=text+' '+tail
            blend=re.split(r'\b(?:WOVEN|KNIT(?:TED)?)\b',joined,maxsplit=1,flags=re.I)[0]
            if ('%' in text and not _material_heading(text,kind)
                    and re.match(r'^\s*\d{1,3}\s*%',tail)
                    and not b.get(cols.get('sender',-1),'').strip()
                    and (_material_heading(joined,kind) or _material_heading(blend))):
                if b.get(cols['quantity'],'').strip() and not a.get(cols['quantity'],'').strip():
                    b[cols['description']]=joined;a[cols['description']]=''
                    continuation_sources[f'{table.page+1}:{table_index+1}:{second+1}']=f'{table.page+1}:{table_index+1}:{first+1}'
                elif not b.get(cols['quantity'],'').strip():
                    a[cols['description']]=joined;b[cols['description']]=''
        material=None
        kinds={c.content.strip().upper() for c in table.cells if c.row_index>header
               and c.column_index==cols.get('fabric_type') and c.content.strip().upper() in ('WOVEN','KNIT')}
        fabric_type=next(iter(kinds)) if len(kinds)==1 else ''
        sample_note=next((_fabric_sample_category(c.content) for c in table.cells
                         if c.row_index>header and c.column_index>cols['quantity']
                         and _fabric_sample_note(c.content)),None)
        category_note=_fabric_sample_category(rows[header].get(cols['description'],''))
        category_ref=f'{table.page+1}:{table_index+1}:{header+1}' if category_note else None
        sender=None
        quantity_header=next((c.content for c in table.cells if c.row_index==header and c.column_index==cols['quantity']),'')
        header_units={_normalize_unit(u) for u in re.findall(rf'\b(?:{UNITS})\b',quantity_header,re.I)}
        header_unit=next(iter(header_units)) if len(header_units)==1 else None
        for r,cells in sorted(rows.items()):
            if r<=header:continue
            raw_desc=cells.get(cols['description'],'').strip()
            explicit_item=cells.get(cols.get('item',-1),'').strip()
            first=max((c for c,v in rows[header].items() if c<cols['description'] and v.strip()),default=cols['description']-1)+1
            unnamed=[c for c in range(first,cols['quantity']) if c not in cols.values() and not rows[header].get(c,'').strip()]
            if unnamed and 'item' not in cols:
                raw_desc='\n'.join(cells[c] for c in range(first,cols['quantity']) if cells.get(c))
            repaired=_repair_goods_text(raw_desc)
            if repaired!=raw_desc:
                warnings.append(f'Page {table.page+1}, row {r+1}: repaired fiber-adjacent OCR glyphs {raw_desc!r} -> {repaired!r}.')
                raw_desc=repaired
            if (re.fullmatch(r'FABRIC SWATCH(?:ES)?',explicit_item,re.I)
                    and re.search(r'\bFABRIC SWATCH(?:ES)? CARD\b',raw_desc,re.I)):
                explicit_item='FABRIC SWATCHES CARD'
            if explicit_item.upper()=='CSI' and re.search(r'\bCSI\s+COLOU?R\s+STANDARD\b',raw_desc,re.I):explicit_item='COLOR STANDARD'
            desc=explicit_item or raw_desc
            qtext=cells.get(cols['quantity'],'').strip()
            total=QTY_UNIT.fullmatch(_quantity_text(qtext))
            titles=re.findall(r'^\s*\d+\.\s*[^\n]*\b(JACKET|DRESS|SHIRT|PANTS|BLOUSE)\)?\s*$',raw_desc,re.I|re.M)
            inline=[m for c in unnamed for m in QTY_UNIT.finditer(_quantity_text(cells.get(c,'')))
                    if _normalize_unit(m['unit'])=='PCS']
            garment_parts=[]
            if (total and _normalize_unit(total['unit'])=='PCS' and len(titles)>1 and len(titles)==len(inline)
                    and abs(sum(_number(m['qty']) for m in inline)-_number(total['qty']))<1e-6):
                profile=re.search(r'\b(MENS?|WOMENS?|LADIES|LADY|KIDS?|GIRLS?|BOYS?)\s+((?:\d+%\s+[A-Z]+\s+)+)(WOVEN|KNIT)\b',raw_desc,re.I)
                prefix=' '.join(profile.groups())+' ' if profile else ''
                garment_parts=[((prefix+title).upper(),quantity) for title,quantity in zip(titles,inline)]
                warnings.append(f'Page {table.page+1}, row {r+1}: split numbered garments using source inline quantities; total preserved.')
            if r==max(rows) and re.search(r'\b(?:DRESS|SHIRT|PANTS|JACKET|BLOUSE)\b',raw_desc,re.I):
                # Only a complete matching garment label immediately below the last row may refine it.
                note_left=next((c.bbox[2] for c in table.cells if c.row_index==r and c.column_index==first-1 and c.bbox),table.bbox[0] if table.bbox else 0)
                note_right=next((c.bbox[0] for c in table.cells if c.row_index==r and c.column_index==cols['quantity'] and c.bbox),table.bbox[2] if table.bbox else 0)
                labels=[_repair_goods_text(w.text) for w in ocr.words if w.page==table.page and table.bbox
                        and table.bbox[3]-3<=w.y0<=table.bbox[3]+ocr.dpi*.4 and w.confidence>=.7
                        and note_left-5<=w.x0 and w.x1<=note_right+5]
                for label in labels:
                    if re.fullmatch(r'(?:LADIES|LADY|MENS?|WOMENS?|KIDS?)\s+100%\s+COTTON\s+WOVEN\s+(DRESS|SHIRT|PANTS|JACKET|BLOUSE)',label,re.I):
                        kind=re.search(r'(DRESS|SHIRT|PANTS|JACKET|BLOUSE)$',label,re.I)[0]
                        if re.search(r'\b'+kind+r'\b',raw_desc,re.I):
                            raw_desc=desc=label
                            warnings.append(f'Page {table.page+1}: matching garment annotation below the final row retained: {label!r}.')
            if not raw_desc and not explicit_item and qtext:
                neighbour=cells.get(cols['description']-1,'').strip()
                if re.match(r'^STYLE\s*[:#]',neighbour,re.I) and re.search(r'\b(?:DRESS|SHIRT|PANTS|BLOUSE|JACKET)\s*$',neighbour,re.I):
                    raw_desc=neighbour
                    desc=raw_desc
            if explicit_item and QTY_UNIT.search(explicit_item):
                lines=[line.strip() for line in explicit_item.splitlines() if line.strip()]
                embedded=[(QTY_UNIT.search(line),line) for line in lines]
                if (len(lines)>1 and sum(m is not None for m,line in embedded)==len(lines)-1
                        and len(list(QTY_UNIT.finditer(qtext)))==1
                        and all(not m or (not line[m.end():].strip(' +') and re.search(
                            re.escape(line[:m.start()].strip(' +:'))+r'\s*(?:X\s*)?'+re.escape(m[0]),
                            raw_desc,re.I)) for m,line in embedded)):
                    labels=[];quantities=[]
                    for match,line in embedded:
                        if match:
                            labels.append(line[:match.start()].strip(' +:'))
                            quantities.append(match[0])
                        else:
                            labels.append(line);quantities.append(qtext)
                    if all(labels):
                        explicit_item='\n'.join(labels)
                        desc=explicit_item
                        qtext='\n'.join(quantities)
            original_quantity=qtext
            qtext=_quantity_text(qtext)
            if qtext!=original_quantity:
                warnings.append(f'Page {table.page+1}: normalized OCR quantity {original_quantity!r} to {qtext!r}; verify.')
            if re.match(r'^(?:SUB[ -]?)?TOTAL\b',desc,re.I):continue
            current_sender=cells.get(cols.get('sender',-1),'').strip()
            if current_sender and current_sender!=sender:
                continuation=sender and sender.rstrip().endswith('-') and not re.search(r'(?:DEPT|TEXTILES)',current_sender,re.I)
                if sender and not continuation:
                    material=None
                    fabric_type=''
                    category_note=category_ref=None
                sender=(sender+' '+current_sender) if continuation else current_sender
            fabric_type=cells.get(cols.get('fabric_type',-1),'').strip().upper() or fabric_type
            if material and fabric_type:
                refined=_material_heading(material,fabric_type) or material
                if refined!=material:
                    for previous in reversed(items[table_start:]):
                        if previous.description!=material:break
                        previous.description=refined
                material=refined
            metadata=not qtext and re.match(r'^\s*(?:STYLE|ITEM|COL(?:OU?R)?\.?)\s*[:#]',raw_desc,re.I)
            row_note=_fabric_sample_category(raw_desc) or _fabric_sample_category(
                ' '.join(v for c,v in cells.items() if c>cols['quantity']))
            if row_note:sample_note=row_note
            heading=_material_heading(desc,fabric_type)
            if heading and row_note:
                heading=row_note
                warnings.append(f'Page {table.page+1}, row {r+1}: FAB annotation supplies broad fabric-sample heading for continuation rows.')
            named_product=re.search(r'\b(?:BUTTONS?|MOULDS?|CARDS?|RIVETS?|ZIPPERS?|SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|JACKETS?)\b',raw_desc,re.I)
            textile=(not named_product and (heading or material or re.search(r'%.*\b(?:COTTON|NYLON|POLYESTER)\b',raw_desc,re.I))) or re.search(r'\b(?:HANDLOOM|STRIKE OFF)\b',raw_desc,re.I)
            if (len(list(QTY_UNIT.finditer(_quantity_text(qtext))))==1 and (sample_note or _fabric_sample_note(raw_desc))
                    and not explicit_item and textile):
                desc=raw_desc=row_note or sample_note
                heading=None
                material=desc
                warnings.append(f'Page {table.page+1}, row {r+1}: broad fabric-sample category from FAB annotation; subtype not asserted.')
            elif (not heading and fabric_type and re.search(r'\bSHELL FABRIC\b',raw_desc,re.I)
                  and re.search(r'\b[0O]{3}\s+COTTON\b',raw_desc,re.I)):
                heading='COTTON '+fabric_type+' FABRICS'
                warnings.append(f'Page {table.page+1}, row {r+1}: cotton fabric retained without an unreadable percentage.')
            new_product=explicit_item or re.search(r'\b(?:SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|JACKETS?|TOPS|BUTTONS?|ZIPPERS?|STICKERS?|LABELS?|SWATCH(?:ES)?|CARDS?|MOULDS?|TAPES?|THREADS?|ELASTIC|RIVETS?)\b',desc,re.I)
            if ('%' in desc or new_product) and not heading and not metadata:
                material=None
            if re.fullmatch(r'TRIMS?\s+CARDS?',qtext,re.I) and not explicit_item:
                category_note='TRIM CARD'
                category_ref=f'{table.page+1}:{table_index+1}:{r+1}'
                qtext=''
            if heading:material=heading
            elif not qtext and row_note:
                material=row_note
            elif not qtext and (re.fullmatch(r'(?:FABRIC SWATCH(?:ES)?(?: CARD)?|TRIMS? CARD)',desc,re.I)
                                 or re.match(r'^FELT PATCH\b',desc,re.I)):
                material=_clean_material_description(desc)
            for name,target in [('weight',weights)]:
                t=cells.get(cols.get(name,-1),'').strip()
                if t:
                    suffix=r'\s*K(?:GS?|CS|ES)\b'
                    found=re.findall(rf'(?<![\w.,+\-])({NUM})'+suffix,t,re.I)
                    if len(found)==1:target.append(_number(found[0]))
                    elif found:warnings.append(f'Page {table.page+1}: ambiguous {name} cell {t!r}.')
            if not qtext:continue
            parsed_pages.add(table.page)
            desc=(category_note if not explicit_item else None) or heading or (desc if explicit_item else material or desc)
            if category_note and not explicit_item:
                category_sources[f'{table.page+1}:{table_index+1}:{r+1}']=category_ref
            if not desc:
                warnings.append(f'Page {table.page+1}: quantity {qtext!r} has no established goods description.')
                continue
            # Parentheses commonly contain packing factors: 5 SETS (4 PCS/SET).
            main_q=re.sub(r'\([^)]*\)|\[[^]]*\]','',qtext)
            if re.fullmatch(NUM,main_q.strip()):
                unit=header_unit
                if unit is None and sample_note:desc=sample_note
                if unit is None and _clean_material_description(desc) in ('TRIM CARD','FABRIC CARD','FABRIC SWATCHES CARD') and _number(main_q.strip()).is_integer():
                    unit='PCS'
                    warnings.append(f'Page {table.page+1}, row {r+1}: PCS inferred from integer count of named cards; source unit not explicit.')
                items.append(LineItem(_clean_material_description(desc),_number(main_q.strip()),unit,
                                      source_page=table.page+1,source_refs=[f'{table.page+1}:{table_index+1}:{r+1}']))
                continue
            main_matches=list(QTY_UNIT.finditer(main_q))
            complete=not QTY_UNIT.sub('',main_q).strip(' \t\n\r+&,;:.()[]')
            if not raw_desc and not explicit_item and r==max(rows) and len(main_matches)==1 and complete:
                previous=items[table_start:]
                unit=_normalize_unit(main_matches[0]['unit'])
                if previous and all(it.quantity is not None and it.unit==unit for it in previous) and abs(sum(it.quantity for it in previous)-_number(main_matches[0]['qty']))<1e-6:
                    warnings.append(f'Page {table.page+1}: unlabelled final quantity equals preceding rows; possible total excluded from goods.')
                    continue
            parts=[]
            if garment_parts:
                parts=garment_parts
            elif len(main_matches)==1 and complete:
                parts=[(desc,main_matches[0])]
            elif len(main_matches)>1 and complete:
                descriptions=[line.strip() for line in desc.splitlines() if line.strip()]
                if len(descriptions)!=len(main_matches):
                    descriptions=_material_headings(raw_desc,fabric_type)
                if len(descriptions)!=len(main_matches):
                    # Composition/product lines remain associated despite extra style/color lines.
                    lines=raw_desc.splitlines()
                    descriptions=[]
                    for index,line in enumerate(lines):
                        if '%' in line and re.search(r'\b(?:SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|TOPS?)\b',line,re.I):
                            previous=lines[index-1] if index else ''
                            gender=re.search(r'\b(MENS?|WOMENS?|LADIES|LADY|KIDS?|GIRLS?|BOYS?)\s*$',previous,re.I)
                            prefix=gender[1]+' ' if gender else ('MENS ' if re.search(r"\bM['â€™]S\b",previous,re.I) else '')
                            descriptions.append(prefix+line)
                if len(descriptions)!=len(main_matches):
                    labels=[re.match(r'^(FABRIC HANGER|(?:EMBY )?MF PART CARD)\b',line.strip(),re.I)
                            for line in raw_desc.splitlines()]
                    named=[m[1].upper() for m in labels if m]
                    if len(named)==len(main_matches):
                        if _fabric_sample_note(raw_desc):
                            named=['FABRIC SAMPLES' if n=='FABRIC HANGER' else n for n in named]
                        notes=' '.join(v for c,v in cells.items() if c>cols['quantity'])
                        if re.search(r'\bTRI?M CARD\b',notes,re.I):
                            named=['TRIM CARD' if 'MF PART CARD' in n else n for n in named]
                        descriptions=named
                if len(descriptions)!=len(main_matches) and not material:
                    descriptions=_quantity_descriptions(ocr,table,r,cols,main_matches,
                                                        f'{table.page+1}:{table_index+1}:{r+1}')
                if len(descriptions)==len(main_matches):
                    parts=list(zip(descriptions,main_matches))
                elif material:
                    parts=[(material,m) for m in main_matches]
                elif _fabric_sample_category(raw_desc):
                    parts=[(_fabric_sample_category(raw_desc),m) for m in main_matches]
                elif re.search(r'\bEC\s+SAMPLE\s+LACE\b',raw_desc,re.I):
                    parts=[('EC SAMPLE LACE',m) for m in main_matches]
            if parts:
                for part,m in parts:
                    if not explicit_item and _normalize_unit(m['unit']) in ('YDS','MTRS'):
                        part=_material_heading(part,fabric_type) or part
                    items.append(LineItem(_clean_material_description(part),_number(m['qty']),_normalize_unit(m['unit']),
                                          source_page=table.page+1,source_refs=[f'{table.page+1}:{table_index+1}:{r+1}']))
            else:
                warnings.append(f'Page {table.page+1}: unresolved quantity {qtext!r} for {desc[:80]!r}.')
                unit_match=re.fullmatch(rf'[0-9.,OISZil\s]*({UNITS})',qtext,re.I)
                items.append(LineItem(_clean_material_description(desc),unit=_normalize_unit(unit_match[1]) if unit_match else None,
                                      source_page=table.page+1,source_refs=[f'{table.page+1}:{table_index+1}:{r+1}']))
    for item in items:
        for ref in tuple(item.source_refs):
            note=category_sources.get(ref)
            if note and note not in item.source_refs:item.source_refs.append(note)
            note=continuation_sources.get(ref)
            if note and note not in item.source_refs:item.source_refs.append(note)
    return items,weights,parsed_pages,warnings


def _aggregate_items(items, *, clean=True, sum_weights=False):
    grouped={}
    for it in items:
        if clean:it.description=_clean_material_description(it.description)
        key=(it.description,it.unit,it.hs_code,it.unit_price,it.origin_country)
        if key not in grouped:grouped[key]=it
        elif (it.quantity is not None and grouped[key].quantity is not None
              and (it.amount is None)==(grouped[key].amount is None)):
            grouped[key].quantity=round(grouped[key].quantity+it.quantity,4)
            if it.amount is not None:
                grouped[key].amount=float(Decimal(str(grouped[key].amount))+Decimal(str(it.amount)))
            if sum_weights:
                weights=(grouped[key].weight_kg,it.weight_kg)
                grouped[key].weight_kg=float(sum(Decimal(str(value)) for value in weights)) if all(value is not None for value in weights) else None
            if grouped[key].source_page!=it.source_page:grouped[key].source_page=None
            grouped[key].source_refs=list(dict.fromkeys(grouped[key].source_refs+it.source_refs))
        else:grouped[(key,len(grouped))]=it
    return list(grouped.values())


def _consignee_region(ocr):
    """Read the labelled consignee block from page geometry when present."""
    words=[w for w in ocr.words if w.page==0]
    labels=[w for w in words if re.fullmatch(r'CONSIGNEE\s*:?',w.text.strip(),re.I)]
    if not labels:return ''
    label=labels[0]
    height=max((w.y1 for w in words),default=1)
    width=max((w.x1 for w in words),default=1)
    stops=[w for w in words if w.y0>label.y1 and w.x0<width*.52 and re.search(r'NOTI[FL]Y|DESTINATION|SHIPMENT|COUNTRY',w.text,re.I)]
    bottom=min((w.y0 for w in stops),default=label.y1+height*.2)
    # Use the consignee column; unrelated agent details are to its right.
    right=max((w.x1 for w in words),default=0)*.52
    selected=[w for w in words if label.y1<=w.y0<bottom and w.x0<right]
    from .ocr_engine import _cluster_into_lines
    tolerance=max((label.y1-label.y0)*.45,height*.002)
    return '\n'.join(_cluster_into_lines(selected,tolerance))


def _packing_recipient_address(ocr,consignee):
    """Use a self-contained location from the labelled packing recipient column."""
    # shortcut: joining addresses split across cells needs reviewed row-grouping rules.
    candidates={};entries=[]
    for index,table in enumerate(ocr.tables):
        if table.page!=0:continue
        _,header=_table_fields(table)
        labels=[c for c in table.cells if c.row_index==header
                and re.match(r'^REC(?:E)?IPIENT\b',c.content.strip(),re.I)]
        if len(labels)!=1:continue
        for cell in table.cells:
            if cell.row_index<=header or cell.column_index!=labels[0].column_index:continue
            lines=[]
            for line in cell.content.splitlines():
                value=re.split(r'\b(?:ATTN|ATTENTION|TEL(?:EPHONE)?|FAX|MOBILE|PHONE|DIRECT|CONTACT|E-?MAIL)\b|\S+@\S+',
                               line,maxsplit=1,flags=re.I)[0].strip()
                if (not value or re.fullmatch(r'\+?\d[\d\s()/.-]{6,}',value)
                        or re.fullmatch(r'(?:MERCHANDISING\s+)?TEAM|DEPT(?:ARTMENT)?',value,re.I)
                        or re.sub(r'\s+',' ',value).casefold()==re.sub(r'\s+',' ',consignee).casefold()):continue
                lines.append(value)
            reading='\n'.join(lines)
            supported=bool(re.search(r'\b(?:ROAD|RD|STREET|AVENUE|LANE|VILLAGE|BLOCK|PLOT|INDUSTRIAL)\b|\bBANGLADESH[.,]?\s*$',
                                     reading,re.I|re.M))
            entries.append({'source_ref':f'1:{index+1}:{cell.row_index+1}','bbox':cell.bbox,
                            'column':cell.column_index,'original':cell.content,'reading':reading,'supported':supported})
            if supported:candidates.setdefault(re.sub(r'\s+',' ',reading).casefold(),reading)
    emit('field_evidence',field='consignee_address',evidence={'method':'packing_recipient_column',
         'entries':entries,'candidates':list(candidates.values()),'accepted':len(candidates)==1})
    return next(iter(candidates.values())) if len(candidates)==1 else None


def _apply_bd_header(data,ocr,block):
    """Keep source party text and marks; never fill identities from a directory."""
    from .india import _labelled_readings
    cover=(ocr.pages or [ocr.content])[0]
    if not block:
        for table in ocr.tables:
            for cell in table.cells:
                if table.page==0 and re.search(r'\bCONSIGNEE\s*:',cell.content,re.I):
                    block=re.split(r'\bCONSIGNEE\s*:',cell.content,maxsplit=1,flags=re.I)[1]
                    break
            if block:break
    if not block and not ocr.words:
        match=re.search(r'^\s*CONSIGNEE\s*:?[ \t]*(.*)',cover,re.I|re.M)
        if match:block=cover[match.start(1):]
    block=re.split(r'\b(?:NOTIFY\s+PARTY|MAWB|HAWB|DESTINATION\s+AIRPORT|MARKS\s*&\s*NOS)\b',
                   block,maxsplit=1,flags=re.I)[0]
    lines=[line.strip() for line in block.splitlines() if line.strip()]
    lines=[re.split(r'\b(?:ATTN|TEL(?:EPHONE)?|FAX|CTC|MOBILE)\b|@',line,maxsplit=1,flags=re.I)[0].strip()
           for line in lines]
    lines=[line for line in lines if line]
    heading=re.split(r'\bPACKING\s+LIST\b',cover,maxsplit=1,flags=re.I)[0]
    recipient=re.search(r'^[ \t]*TO\s*:[ \t]*([^\n]+)',heading,re.I|re.M)
    bare=re.search(r'^[ \t]*[A-Z]{2,8}(?:[ \t-]+\d{1,2})?[ \t-]*(?:FOC|FABRIC|GMT)[ \t]*$',heading,re.I|re.M)
    data.consignee=lines[0] if lines else (recipient[1].strip() if recipient else bare[0].strip() if bare else None)
    data.consignee_address='\n'.join(lines[1:]) or None
    if not lines and data.consignee:
        data.consignee_address=_packing_recipient_address(ocr,data.consignee)
    entries=list(_labelled_readings(ocr,r'\b(?:SHIPPING\s+MARKS|MARKS\s*(?:&|AND)?\s*NOS?\.?)',
                                   cover_only=True,form_heading=r'NO\.?\s+AND\s+KIND\s+OF\s+PACKAGES'))
    marks=set()
    section=re.search(r'\b(?:SHIPPING\s+MARKS|MARKS\s*(?:&|AND)?\s*NOS?\.?)\s*[:=]?(.*)',cover,re.I|re.S)
    if section:
        marks_text=re.split(r'C\s*/\s*NO|SPECIFY\s+CURRENCY|WAREHOUSE',section[1],maxsplit=1,flags=re.I)[0]
        visible=_extract_shipping_marks(marks_text)
        if visible:marks.add(visible)
    if not marks:
        for entry in entries:
            value=re.split(r'\s+\d+(?:\.\d+)?\s*(?:PACKAGES?|PACKS?|PKGS?|PK|CTNS?|CARTONS?)\b',
                           entry['reading'],maxsplit=1,flags=re.I)[0].strip()
            if re.fullmatch(r'[A-Z0-9][A-Z0-9 _/-]{1,39}',value,re.I) and not re.search(
                    r'\b(?:PACKAGES?|ONLY|KGS?|WEIGHT|DESCRIPTION|GOODS|BANGLADESH|USD|FABRICS)\b',value,re.I):
                marks.add(value.upper())
    if not entries and not re.search(r'\bSHIPPER\b',cover,re.I):
        value=recipient[1].strip() if recipient else bare[0].strip() if bare else ''
        visible=_extract_shipping_marks(value)
        if visible:marks.add(visible)
    data.shipping_marks=next(iter(marks)) if len(marks)==1 else None
    source='\n'.join(lines) or data.consignee_address or ''
    data.destination_country='Bangladesh' if re.search(r'\bBANGLADESH\b',source,re.I) else None
    destinations=list(_labelled_readings(ocr,r'\bDESTINATION\s+AIRPORT(?:\s*/\s*PLACE)?',
                                        cover_only=True,form_heading=r'AIRLINE\b'))
    cities={entry['reading'].strip(' ()').upper() for entry in destinations
            if re.fullmatch(r'\(?[A-Z][A-Z ,.-]{1,49}\)?',entry['reading'],re.I)
            and not re.search(r'\b(?:AIRLINE|COUNTER|SIGNATURE|YES|NO)\b',entry['reading'],re.I)}
    data.destination_city=next(iter(cities)) if len(cities)==1 else None
    for field in ('consignee','consignee_address','shipping_marks','destination_country','destination_city'):
        emit('field_source',field=field,value=getattr(data,field),method='bangladesh_pdf_header',page=1)
    emit('field_evidence',field='shipping_marks',evidence={'entries':entries,'candidates':sorted(marks)})


def _extract_tin(text):
    matches = re.findall(r'\bT[IL1]N\s*(?:NO\.?|NUMBER|[:#])\s*[:#]?\s*(\d+(?:\s*[-/]\s*[A-Z0-9]+)*)', text, re.I)
    values = list(dict.fromkeys(re.sub(r'\s*([-/])\s*', r'\1', value) for value in matches
                                if 7 <= sum(c.isdigit() for c in value) <= 20))
    return values[0] if len(values) == 1 else None


def _extract_import_cover_note(text):
    lines = text.splitlines()
    notes = []
    for index, line in enumerate(lines):
        if not re.search(r'\bIMPORT\s+(?:OPEN\s+)?COVER\s+NOTE\b', line, re.I):
            continue
        note = line.strip()
        for following in lines[index+1:index+3]:
            if re.match(r'\s*(?:DATED\b|[A-Z]+/[A-Z0-9/]+)', following, re.I):
                note += ' ' + following.strip()
            else:
                break
        if re.search(r'[A-Z0-9]+/[A-Z0-9/]+', note, re.I):
            notes.append(re.sub(r'\s+', ' ', note))
    return notes[0] if notes and len(set(notes)) == 1 else None


def parse_result(ocr_result, source, *, region=None):
    text=ocr_result.content; upper=text.upper()
    consignee_block=_consignee_region(ocr_result)
    first_page=ocr_result.pages[0] if ocr_result.pages else text
    india = region=='INDIA' or (region is None and bool(re.search(
        r'\bTRIMETRO\b|^\s*TO\s*:\s*TG[IP]*L\b',consignee_block or first_page,re.I|re.M)))
    jordan = region=='JORDAN' or (region is None and not india and bool(re.search(
        r'\bEPIC\s+DESIGNERS\b|\bEJU1\b',consignee_block or first_page,re.I)))
    if region is not None:
        from .regions import region_code
        region_code(region)
    data=FOCData(source_file=Path(source).name,template_type='BD')
    from .india import source_currency
    data.currency=source_currency(ocr_result)
    data.ocr_backend=ocr_result.backend or None
    data.pages_processed=len(ocr_result.pages)
    data.pages_total=ocr_result.total_pages or None
    data.warnings.extend(ocr_result.warnings)
    data.invoice_number=_extract_invoice_number(first_page if jordan else text)
    emit('field_source', field='invoice_number', method='jordan_shipment_cover' if jordan else 'pdf_invoice_reference',
         value=data.invoice_number)
    if india or jordan:
        from .india import export_date
        data.export_date,explicit_export=export_date(ocr_result)
        explicit_export=explicit_export or bool(re.search(EXPORT_DATE_LABEL,text,re.I))
    else:
        data.export_date=_extract_export_date(text)
        explicit_export=bool(re.search(EXPORT_DATE_LABEL,text,re.I))
    emit('field_source', field='export_date', method='explicit_export_label', value=data.export_date)
    if data.export_date is None and not explicit_export:
        if india or jordan:
            from .india import latest_packing_date
            data.export_date=latest_packing_date(ocr_result)
        else:
            data.export_date=_extract_packing_date(ocr_result.pages or [text])
        emit('field_source', field='export_date', method='latest_labelled_packing_date' if india or jordan else 'first_labelled_packing_date', value=data.export_date)
        if data.export_date:
            data.warnings.append('Export date supplied by '+('latest labelled' if india or jordan else 'first dated')+' PDF packing-list page (numeric dates: month/day/year).')
    data.shipping_marks=_extract_shipping_marks(text)
    data.carton_range=_extract_carton_range(text)
    # Header weight declarations precede packing tables.
    summary=_shipment_summary(ocr_result)
    data.gross_weight_kg=_extract_gross_weight(summary)
    data.tin_number = _extract_tin(text)
    data.import_cover_note = _extract_import_cover_note(text)
    if jordan:
        from .jordan import source_total
        data.total_value=source_total(ocr_result,data.currency)
    else:
        data.total_value=_extract_total_value(text)
    for field in ('shipping_marks','gross_weight_kg','tin_number','import_cover_note','total_value'):
        emit('field_source', field=field, method='explicit_pdf_reading', value=getattr(data,field))
    if india:
        from .india import prepare_tables, enrich_items
        prepared,headings=prepare_tables(ocr_result)
        items,weights,parsed_pages,warnings=_extract_table_data(prepared)
        enrich_items(items,ocr_result,headings)
    elif jordan:
        from .india import enrich_money
        from .jordan import prepare_goods, enrich_goods
        prepared,details=prepare_goods(ocr_result)
        items,weights,parsed_pages,warnings=_extract_table_data(prepared)
        enrich_money(items,ocr_result,data.currency)
        enrich_goods(items,details)
    else:
        items,weights,parsed_pages,warnings=_extract_table_data(ocr_result)
        from .india import enrich_money
        enrich_money(items,ocr_result,data.currency)
    data.warnings.extend(warnings)
    for page,content in enumerate(ocr_result.pages or [text]):
        if 'SHIPPER' in content.upper():continue
        page_tables=[t for t in ocr_result.tables if t.page==page]
        if ocr_result.words and not any(t.bbox for t in page_tables):
            data.warnings.append(f'Page {page+1}: goods table boundaries unavailable; unrestricted page text excluded from invoice items.')
            continue
        if page in parsed_pages:
            # Outside annotations can repeat totals or describe future requests.
            page_tables=[t for t in page_tables if not _table_fields(t)[0] and t.bbox]
            if not page_tables:continue
        if page_tables and ocr_result.words and all(t.bbox for t in page_tables):
            from .ocr_engine import _cluster_into_lines
            inside=[w for w in ocr_result.words if w.page==page and any(
                t.bbox[0]<=(w.x0+w.x1)/2<=t.bbox[2] and t.bbox[1]<=(w.y0+w.y1)/2<=t.bbox[3] for t in page_tables)]
            content='\n'.join(_cluster_into_lines(inside))
        fallback=_extract_items_from_text(content)
        if fallback:
            data.warnings.append(f'Page {page+1}: unstructured item extraction requires review.')
            for index,it in enumerate(fallback):
                it.source_page=page+1
                it.source_refs=[f'{page+1}:text:{index+1}']
            items.extend(fallback)
        elif page not in parsed_pages:data.warnings.append(f'Page {page+1}: no goods extracted; check page coverage.')
    coverage=[]
    pages=ocr_result.pages or [text]
    for page in range(max(len(pages),ocr_result.total_pages)):
        content=pages[page] if page<len(pages) else ''
        goods=[it for it in items if it.source_page==page+1]
        missing=sum(it.quantity is None or not it.unit for it in goods)
        if goods:status='goods_partial' if missing else 'goods_extracted'
        elif page>=len(pages):status='not_processed'
        elif 'SHIPPER' in content.upper():status='shipment_cover'
        elif re.search(r'PACKING\s*LIST',content,re.I):status='packing_list_unresolved'
        else:status='unclassified' if content.strip() else 'unreadable'
        coverage.append({'page':page+1,'status':status,'goods_rows':len(goods),
                         'unresolved_quantities':missing,
                         'source_refs':[ref for it in goods for ref in it.source_refs]})
        if status in ('not_processed','unclassified','unreadable','packing_list_unresolved'):
            data.warnings.append(f'Page {page+1}: {status.replace("_"," ")}; check page coverage.')
    emit('field_evidence',field='page_coverage',evidence=coverage)
    data.items=_aggregate_items(items,clean=not (india or jordan))
    if data.gross_weight_kg is None and weights:
        data.warnings.append('Packing-list weights are not established as complete gross shipment weight.')
    from .packages import packing_packages
    package_evidence=packing_packages(ocr_result,data.carton_range)
    data.package_count=package_evidence['total']
    data.warnings.append('Package count basis: '+package_evidence['basis']+'.')
    if package_evidence['reason']:data.warnings.append('Package extraction: '+package_evidence['reason'])
    if not india and not jordan:
        _apply_bd_header(data,ocr_result,consignee_block)
    if india:
        from .india import apply_header
        data.template_type='INDIA'
        apply_header(data,ocr_result,consignee_block)
    elif jordan or data.template_type == 'JORDAN':
        from .jordan import apply_header
        apply_header(data,ocr_result,consignee_block)
    if data.template_type != 'BD':
        data.net_weight_kg = _extract_net_weight(text)
    for attr in ['invoice_number','export_date','consignee','consignee_address','shipping_marks','package_count','gross_weight_kg','total_value']:
        if getattr(data,attr) is None:data.warnings.append(f'{attr} not established from source; review required.')
    if not data.items:data.warnings.append('No goods extracted; invoice is incomplete.')
    for it in data.items:
        if it.unit=='G':data.warnings.append('Unit G is ambiguous; confirm meaning without automatic conversion.')
    data.warnings=list(dict.fromkeys(data.warnings))
    return data
