"""
Parser module: Extracts structured FOCData from OCR text.

Works with the unified OCRResult from ocr_engine.py.
Handles all template types: BD (EGMCL/PGCL), India (TGPL), Jordan (EJU1).

Extraction strategy:
  1. Header fields — entity dictionaries & regex with OCR tolerance
  2. Line items    — Azure tables (when available) or regex-based line item parsing
  3. Validation    — cross-checks package counts, carton numbers, and totals
"""

import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .models import FOCData, LineItem
from .ocr_engine import OCRResult

# ---------------------------------------------------------------------------
# Entity Directory for Known Consignees & Standard Addresses
# ---------------------------------------------------------------------------

KNOWN_CONSIGNEES = {
    "PEARL": {
        "name": "PEARL GARMENTS COMPANY LTD.",
        "address": (
            "POLASHBARI, NABINAGAR, SAVAR\n"
            "PS: DHAKA -1349\n"
            "(BIN : 000817323-0112)"
        ),
        "country": "Bangladesh",
        "city": "DHAKA, BD",
        "template": "BD",
        "shipping_marks": "PGCL-FOC",
    },
    "PGCL": {
        "name": "PEARL GARMENTS COMPANY LTD.",
        "address": (
            "POLASHBARI, NABINAGAR, SAVAR\n"
            "PS: DHAKA -1349\n"
            "(BIN : 000817323-0112)"
        ),
        "country": "Bangladesh",
        "city": "DHAKA, BD",
        "template": "BD",
        "shipping_marks": "PGCL-FOC",
    },
    "EPIC GARMENTS": {
        "name": "EPIC GARMENTS MANUFACTURING CO. LTD.",
        "address": (
            "Plot # 11- 22, 26-34, MS-SFB # 3, Plot # 265-266,\n"
            "271-272,200, 201, 202 & 209, Adamjee EPZ.\n"
            "Siddhirganj PS : Narayanganj-1431\n"
            "Bangladesh\n"
            "BIN : 000322109-1402"
        ),
        "country": "Bangladesh",
        "city": "DHAKA,BD",
        "template": "BD",
        "shipping_marks": "EGMCL-FOC",
    },
    "EGMCL": {
        "name": "EPIC GARMENTS MANUFACTURING CO. LTD.",
        "address": (
            "Plot # 11- 22, 26-34, MS-SFB # 3, Plot # 265-266,\n"
            "271-272,200, 201, 202 & 209, Adamjee EPZ.\n"
            "Siddhirganj PS : Narayanganj-1431\n"
            "Bangladesh\n"
            "BIN : 000322109-1402"
        ),
        "country": "Bangladesh",
        "city": "DHAKA,BD",
        "template": "BD",
        "shipping_marks": "EGMCL-FOC",
    },
    "GREEN TEXTILE": {
        "name": "GREEN TEXTILE LIMITED",
        "address": (
            "NIJHURI, BARAID, 2 NO MEDUARI\n"
            "BHALUKA, MYMENSINGH, BANGLADESH.\n"
            "(BIN:000830659-0104)"
        ),
        "country": "Bangladesh",
        "city": "DHAKA,BD",
        "template": "BD",
        "shipping_marks": "GTL-FOC",
    },
    "GTL": {
        "name": "GREEN TEXTILE LIMITED",
        "address": (
            "NIJHURI, BARAID, 2 NO MEDUARI\n"
            "BHALUKA, MYMENSINGH, BANGLADESH.\n"
            "(BIN:000830659-0104)"
        ),
        "country": "Bangladesh",
        "city": "DHAKA,BD",
        "template": "BD",
        "shipping_marks": "GTL-FOC",
    },
    "ROSE": {
        "name": "THE ROSE DRESSES LTD",
        "address": (
            "DIAKHALI, YEARPUR\n"
            "JAMGORA,ASHULIA, SAVAR,\n"
            "DHAKA-1349, Bangladesh\n"
            "BIN: 000517241-0403"
        ),
        "country": "Bangladesh",
        "city": "DHAKA,BD",
        "template": "BD",
        "shipping_marks": "ROSE-FOC",
    },
    "COSMOPOLITAN": {
        "name": "COSMOPOLITAN INDUSTRIES (PVT.) LIMITED",
        "address": (
            "Khejur Bagan, Bara Ashulia,\n"
            "Savar PS; Dhaka-1341\n"
            "Bangladesh\n"
            "BIN : 000771673-0112"
        ),
        "country": "Bangladesh",
        "city": "DHAKA, BD",
        "template": "BD",
        "shipping_marks": "CIPL-FOC",
    },
    "CIPL": {
        "name": "COSMOPOLITAN INDUSTRIES (PVT.) LIMITED",
        "address": (
            "Khejur Bagan, Bara Ashulia,\n"
            "Savar PS; Dhaka-1341\n"
            "Bangladesh\n"
            "BIN : 000771673-0112"
        ),
        "country": "Bangladesh",
        "city": "DHAKA, BD",
        "template": "BD",
        "shipping_marks": "CIPL-FOC",
    },
    "TRIMETRO": {
        "name": "TRIMETRO GARMENTS INDIA PVT LTD",
        "address": (
            "MOTA VILLAGE,KALIBETI MOUZA,IDCO,PLOT 1 AND 2,\n"
            "REVENUE PLOT NO 282,JANKIA,KHORDA ODISHA-752020,INDIA\n"
            "IEC &PAN : AAJCT7390N\n"
            "GST Number : 21AAJCT7390N1ZS"
        ),
        "country": "India",
        "city": "CHENNAI, INDIA",
        "template": "INDIA",
        "shipping_marks": "TGPLFOCTS",
    },
    "TGPL": {
        "name": "TRIMETRO GARMENTS INDIA PVT LTD",
        "address": (
            "MOTA VILLAGE,KALIBETI MOUZA,IDCO,PLOT 1 AND 2,\n"
            "REVENUE PLOT NO 282,JANKIA,KHORDA ODISHA-752020,INDIA\n"
            "IEC &PAN : AAJCT7390N\n"
            "GST Number : 21AAJCT7390N1ZS"
        ),
        "country": "India",
        "city": "CHENNAI, INDIA",
        "template": "INDIA",
        "shipping_marks": "TGPLFOCTS",
    },
    "EPIC DESIGNERS": {
        "name": "EPIC DESIGNERS LIMITED JORDAN",
        "address": (
            "AD DULAYL INDUSTRIAL PARK, LANE NO. 1201,\n"
            "AD DULAYL BASIN 5, AD DULAYL, ZARQA, JORDAN"
        ),
        "country": "Jordan",
        "city": "JORDAN",
        "template": "JORDAN",
        "shipping_marks": "EJU1FOCTS",
    },
    "EJU1": {
        "name": "EPIC DESIGNERS LIMITED JORDAN",
        "address": (
            "AD DULAYL INDUSTRIAL PARK, LANE NO. 1201,\n"
            "AD DULAYL BASIN 5, AD DULAYL, ZARQA, JORDAN"
        ),
        "country": "Jordan",
        "city": "JORDAN",
        "template": "JORDAN",
        "shipping_marks": "EJU1FOCTS",
    },
}

# Numbers have no nested captures; quantity and unit are named explicitly.
NUM = r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{1,3}(?:\.\d{3})+,\d+|\d+(?:[.,]\d+)?)"
UNITS = r"YARDS?|YDS?|YS?|PIECES?|PCS?|SETS?|GROSS|GRS|CONES?|ROLLS?|MTRS?|METERS?|PACKS?|G"
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
    text=re.sub(r'\b[Iil](?=\s*(?:PCS?\b|YDS\b|SETS?\b))','1',text,flags=re.I)
    return re.sub(r'(?<=\d)\s*VD[S:]?\b',' YDS',text,flags=re.I)


def _extract_invoice_number(text, filename=''):
    candidates = re.findall(r'\b[S5]\s*/\s*(\d{3,5})\s*/\s*(\d{2})\b', text, re.I)
    unique = list(dict.fromkeys(f'S/{n}/{y}' for n,y in candidates))
    return unique[0] if len(unique) == 1 else None


def _parse_date(text):
    from datetime import date, datetime
    months = {m:i+1 for i,m in enumerate('JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC'.split())}
    values=set()
    patterns = [r'ON/ABT\.?\s*([A-Z]{3})[A-Z]*[.\s-]*(\d{1,2})[,\s-]+(\d{4})',
                r'\b(\d{1,2})[-\s]+([A-Z]{3})[A-Z]*[,\s-]+(\d{4}|\d{2})\b']
    for idx,pattern in enumerate(patterns):
        for m in re.finditer(pattern,text.upper()):
            a,b,y=m.groups(); month,day=(months.get(a),b) if idx==0 else (months.get(b),a)
            try:values.add(date(int(y) if len(y)==4 else datetime.strptime(y,'%y').year,month,int(day)).isoformat())
            except (ValueError,TypeError):continue
    if values:return next(iter(values)) if len(values)==1 else None
    dates=set()
    for a,b,y in re.findall(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',text):
        a,b,y=int(a),int(b),int(y)
        # An ambiguous slash date is not silently interpreted.
        for month,day in ((a,b),(b,a)):
            try:dates.add(date(y,month,day).isoformat())
            except ValueError:pass
    return next(iter(dates)) if len(dates)==1 else None


def _extract_export_date(text):
    # A nearby packing date must never stand in for an absent export date.
    labelled=re.findall(r'(?:DATE\s+OF\s+EXPORT(?:ATION)?|EXPORT\s+DATE|ON/ABT\.?)\s*[:.-]?\s*([^\n]+)',text,re.I)
    values={_parse_date('ON/ABT '+value) for value in labelled}
    values.discard(None)
    return next(iter(values)) if len(values)==1 else None


def _extract_carton_range(text):
    ranges=[]
    # Correct O only inside a labelled carton number, never in style codes.
    text=re.sub(r'(C\s*[/I1]?\s*NO[.:]?[^\n]*)',lambda m:re.sub(r'(?<=[0-9])O\b','0',m[0]),text.upper())
    for m in re.finditer(r'C\s*[/I1]?\s*NO[.:]?\s*([A-Z]\s*\d{1,3})(?:(?:[ \t]*[-–][ \t]*|[ \t]+(?=[A-Z]\d))([A-Z]?\s*\d{1,3}))?',text):
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
    m=re.search(r'\b([A-Z]{2,8})(?:\s+\d{1,2})?\s*[-–]?\s*FOC\b',text.upper())
    return f'{m[1]}-FOC' if m else None


def _extract_package_count(text):
    values={int(v) for v in re.findall(r'\b(\d{1,3})[ \t]*(?:PACKAGE\(?S?\)?|PKG\(?S?\)?|CARTONS?)\b',text.upper())}
    return next(iter(values)) if len(values)==1 else None


def _extract_gross_weight(text):
    patterns=[rf'(?:\bG\.?\s*W\.?|GROSS\s+WEIGHT)\s*:?\s*({NUM})\s*KGS?\b']
    if 'SHIPPER' in text.upper() and 'PACKAGES' in text.upper():
        patterns.append(rf'\b(?:APP\.?|EST\.?)\s*:?\s*({NUM})\s*KGS?\b')
    values={_number(v) for p in patterns for v in re.findall(p,text.upper())}
    return next(iter(values)) if len(values)==1 else None


def _extract_total_value(text):
    values={_number(v) for v in re.findall(rf'TOTAL\s+VALUE\s*:?\s*(?:USD\s*|\$\s*)?({NUM})',text.upper())}
    return next(iter(values)) if len(values)==1 else None


def _clean_material_description(raw_desc):
    """Normalize source text without converting garments to fabric or losing blends."""
    s=re.sub(r'\s+',' ',raw_desc).strip().upper()
    s=re.sub(r'(\d)\s*%\s*',r'\1% ',s)
    s=re.sub(r'\bFABRICS? SWATCH(?:ES)?\b','FABRIC SWATCHES',s)
    s=re.sub(r'\bWOVEN FABRIC\b','WOVEN FABRICS',s)
    s=re.sub(r'\bKNIT FABRIC\b','KNIT FABRICS',s)
    s=re.sub(r'^\d+[).]\s+','',s)
    s=re.sub(r'\bMOOULD\b','MOULD',s)
    if re.search(r'\bDIE\s+MOULD\b',s):
        kinds=set(re.findall(r'\bSNAP|\bSHANK|\bRIVET',s))
        if len(kinds)==1:return f'DIE MOULD ({next(iter(kinds))})'
    if re.search(r'\bFABRIC SWATCHES\b',s):return 'FABRIC SWATCHES'
    if re.search(r'\bBULK TRIMS? CARD\b',s):return 'BULK TRIM CARD'
    if re.search(r'\bTRIMS? CARD\b',s):return 'TRIM CARD'
    if re.search(r'\bSIZE STICKER\b',s):return 'SIZE STICKER'
    # Composition starts after supplier/style metadata. Keep the complete blend.
    comp=re.search(r'\b\d{1,3}\s*%',s)
    if comp:
        material=s[comp.start():]
        end=re.search(r'\b(?:WOVEN|KNIT(?:TED)?)\s+(?:FABRICS?|SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|TOPS?)\b',material)
        percentages=[int(v) for v in re.findall(r'(\d{1,3})\s*%',material)]
        if end and sum(percentages)==100:
            prefix=s[:comp.start()]
            garment=re.search(r'\b(MENS?|WOMENS?|LADIES|LADY|KIDS?)\s*$',prefix)
            return ((garment[1]+' ') if garment else '')+material[:end.end()]
    return s


def _material_headings(text, fabric_type=''):
    text=re.sub(r'\bI?SHRINKAGE\s*:?[^\n]*','',text.upper())
    text=re.sub(r'\s+',' ',text)
    text=re.sub(r'%\s*/','%',text)
    text=re.sub(r'\bPOLY\b','POLYESTER',text)
    fibers=r'(?:RECYCLED |RECYCLE |ORGANIC |BCI |USA? )?(?:VISCOSE RAYON|COTTON|POLYESTER|POLYAMIDE|NYLON|WOOL|ELASTANE|SPANDEX|LYOCELL|VISCOSE|RAYON|LINEN|SILK|METALLIC|TENCEL|OTHERS)'
    matches=list(re.finditer(rf'\d{{1,3}}\s*%\s*{fibers}\b',text))
    kind=re.search(r'\b(WOVEN|KNIT(?:TED)?)\b',fabric_type+' '+text.upper())
    if not matches or not kind:return []
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
        if re.match(r'\s*(?:(?:WOVEN|KNIT(?:TED)?)\s+)?(?:SHIRTS?|PANTS?|DRESSES?|BLOUSES?|TOPS?)\b',after):return []
        composition=' '.join(re.sub(r'\s*%\s*','% ',m[0]) for m in group)
        headings.append(composition+' '+('KNIT' if kind[1].startswith('KNIT') else 'WOVEN')+' FABRICS')
    return headings


def _material_heading(text, fabric_type=''):
    headings=set(_material_headings(text,fabric_type))
    return next(iter(headings)) if len(headings)==1 else None


def _extract_items_from_text(text, default_carton=None):
    items=[]
    for line in text.splitlines():
        if re.search(r'SHIPPER|CONSIGNEE|TOTAL|INVOICE|PACKING LIST|PARTICULARS|BUYER|FOC\b',line,re.I):continue
        m=QTY_UNIT.search(line)
        if m and len(line[:m.start()].strip())>=3:
            desc=line[:m.start()].strip()
            if _normalize_unit(m['unit']) in ('ROLLS','PACKS') and re.search(r'\bKGS?\b',desc,re.I):continue
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
        if 'quantity' not in columns and {'description','weight'}<=columns.keys():
            candidate=columns['weight']-1
            values=[c.content for c in table.cells if c.row_index>row and c.column_index==candidate]
            if candidate>columns['description'] and any(QTY_UNIT.search(_quantity_text(v)) for v in values):columns['quantity']=candidate
        if {'description','quantity'}<=columns.keys():return columns,row
    return {},-1


def _extract_table_data(ocr):
    items=[]; weights=[]; packages=[]; parsed_pages=set(); warnings=[]
    for table_index,table in enumerate(ocr.tables):
        cols,header=_table_fields(table)
        if not {'description','quantity'}<=cols.keys():
            warnings.append(f'Page {table.page+1}: table columns not established.')
            continue
        rows={}
        for c in table.cells:rows.setdefault(c.row_index,{})[c.column_index]=c.content
        material=None
        fabric_type=''
        for r,cells in sorted(rows.items()):
            if r<=header:continue
            raw_desc=cells.get(cols['description'],'').strip()
            explicit_item=cells.get(cols.get('item',-1),'').strip()
            desc=explicit_item or raw_desc
            qtext=cells.get(cols['quantity'],'').strip()
            original_quantity=qtext
            qtext=_quantity_text(qtext)
            if qtext!=original_quantity:
                warnings.append(f'Page {table.page+1}: normalized OCR quantity {original_quantity!r} to {qtext!r}; verify.')
            if re.match(r'^(?:SUB[ -]?)?TOTAL\b',desc,re.I):continue
            if cells.get(cols.get('sender',-1),'').strip():
                material=None
                fabric_type=''
            fabric_type=cells.get(cols.get('fabric_type',-1),'').strip().upper() or fabric_type
            heading=_material_heading(desc,fabric_type)
            if ('%' in desc or re.search(r'\b(?:SHIRTS?|PANTS?|DRESSES|BLOUSES?|TOPS|BUTTONS?|ZIPPERS?)\b',desc,re.I)) and not heading:
                material=None
            if heading:material=heading
            elif not qtext and re.fullmatch(r'(?:FABRIC SWATCH(?:ES)?(?: CARD)?|TRIMS? CARD)',desc,re.I):
                material=_clean_material_description(desc)
            for name,target in [('weight',weights),('packages',packages)]:
                t=cells.get(cols.get(name,-1),'').strip()
                if t:
                    suffix=r'\s*K(?:GS?|CS|ES)\b' if name=='weight' else r'\s*(?:PACK(?:AGE)?S?|ROLLS?|BOX(?:ES)?|CARTONS?)\b'
                    found=re.findall(rf'(?<![\w.,+\-])({NUM})'+suffix,t,re.I)
                    if len(found)==1:target.append(_number(found[0]))
                    elif found:warnings.append(f'Page {table.page+1}: ambiguous {name} cell {t!r}.')
            if not qtext:continue
            parsed_pages.add(table.page)
            desc=heading or material or desc
            if not desc:
                warnings.append(f'Page {table.page+1}: quantity {qtext!r} has no established goods description.')
                continue
            # Parentheses commonly contain packing factors: 5 SETS (4 PCS/SET).
            main_q=re.sub(r'\([^)]*\)|\[[^]]*\]','',qtext)
            main_matches=list(QTY_UNIT.finditer(main_q))
            complete=not QTY_UNIT.sub('',main_q).strip(' \t\n\r+&,;:.()[]')
            parts=[]
            if len(main_matches)==1 and complete:
                parts=[(desc,main_matches[0])]
            elif len(main_matches)>1 and complete:
                descriptions=[line.strip() for line in desc.splitlines() if line.strip()]
                if len(descriptions)!=len(main_matches):
                    descriptions=_material_headings(raw_desc,fabric_type)
                if len(descriptions)!=len(main_matches):
                    # Composition/product lines remain associated despite extra style/color lines.
                    descriptions=[line for line in raw_desc.splitlines()
                                  if '%' in line and re.search(r'\b(?:SHIRTS?|PANTS?|DRESSES|BLOUSES?|TOPS?)\b',line,re.I)]
                if len(descriptions)==len(main_matches):
                    parts=list(zip(descriptions,main_matches))
                elif material:
                    parts=[(material,m) for m in main_matches]
            if parts:
                for part,m in parts:
                    items.append(LineItem(_clean_material_description(part),_number(m['qty']),_normalize_unit(m['unit']),
                                          source_page=table.page+1,source_refs=[f'{table.page+1}:{table_index+1}:{r+1}']))
            else:
                warnings.append(f'Page {table.page+1}: unresolved quantity {qtext!r} for {desc[:80]!r}.')
                unit_match=re.fullmatch(rf'[0-9.,OISZil\s]*({UNITS})',qtext,re.I)
                items.append(LineItem(_clean_material_description(desc),unit=_normalize_unit(unit_match[1]) if unit_match else None,
                                      source_page=table.page+1,source_refs=[f'{table.page+1}:{table_index+1}:{r+1}']))
    return items,weights,packages,parsed_pages,warnings


def _aggregate_items(items):
    grouped={}
    for it in items:
        it.description=_clean_material_description(it.description)
        key=(it.description,it.unit,it.hs_code,it.unit_price)
        if key not in grouped:grouped[key]=it
        elif it.quantity is not None and grouped[key].quantity is not None:
            grouped[key].quantity=round(grouped[key].quantity+it.quantity,4)
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


def parse_result(ocr_result, source):
    text=ocr_result.content; upper=text.upper()
    data=FOCData(source_file=Path(source).name,template_type='BD')
    data.ocr_backend=ocr_result.backend or None
    data.pages_processed=len(ocr_result.pages)
    data.pages_total=ocr_result.total_pages or None
    data.warnings.extend(ocr_result.warnings)
    data.invoice_number=_extract_invoice_number(text)
    filename=re.search(r'(\d{2})S(\d{3,5})',Path(source).stem,re.I)
    filename_invoice=f'S/{filename[2]}/{filename[1]}' if filename else None
    if not data.invoice_number and filename_invoice:
        data.invoice_number=filename_invoice
        data.warnings.append('Invoice number inferred from filename; verify against document.')
    elif filename_invoice and filename_invoice!=data.invoice_number:
        data.warnings.append('Document invoice number differs from filename.')
    data.export_date=_extract_export_date(text)
    data.shipping_marks=_extract_shipping_marks(text)
    data.carton_range=_extract_carton_range(text)
    # Header totals precede packing tables. Detail-page quantities are not totals.
    summary='\n'.join(p for p in ocr_result.pages if 'SHIPPER' in p.upper() and 'PACKAGES' in p.upper())
    summary=summary or (ocr_result.pages[0] if ocr_result.pages else text)
    data.package_count=_extract_package_count(summary)
    data.gross_weight_kg=_extract_gross_weight(summary)
    data.total_value=_extract_total_value(text)
    items,weights,packages,parsed_pages,warnings=_extract_table_data(ocr_result)
    data.warnings.extend(warnings)
    for page,content in enumerate(ocr_result.pages or [text]):
        if page in parsed_pages:continue
        if 'SHIPPER' in content.upper():continue
        fallback=_extract_items_from_text(content)
        if fallback:
            data.warnings.append(f'Page {page+1}: unstructured item extraction requires review.')
            for index,it in enumerate(fallback):
                it.source_page=page+1
                it.source_refs=[f'{page+1}:text:{index+1}']
            items.extend(fallback)
        else:data.warnings.append(f'Page {page+1}: no goods extracted; check page coverage.')
    data.items=_aggregate_items(items)
    if data.gross_weight_kg is None and weights:
        data.warnings.append('Packing-list weights are not established as complete gross shipment weight.')
    count=_carton_count(data.carton_range)
    if count and data.package_count is None:
        data.package_count=count
        data.warnings.append('Package count inferred from labelled carton ranges.')
    elif count and count!=data.package_count:
        data.warnings.append('Explicit package total conflicts with carton count; explicit total retained.')
    if data.package_count is None and packages:
        detail_pages={p for p,content in enumerate(ocr_result.pages) if 'SHIPPER' not in content.upper()}
        if len(ocr_result.tables)==1 and len(packages)==1 and detail_pages<=parsed_pages and packages[0].is_integer():
            data.package_count=int(packages[0])
        else:data.warnings.append('Packing-list package cells do not establish a complete shipment total.')
    region=_consignee_region(ocr_result)
    lookup=region.upper() or (ocr_result.pages[0].upper() if ocr_result.pages else upper)
    directory=list(KNOWN_CONSIGNEES.items())
    if not region and data.shipping_marks:
        directory.sort(key=lambda kv:kv[1]['shipping_marks']!=data.shipping_marks)
    for key,entity in directory:
        if key in lookup:
            data.consignee=entity['name']
            data.destination_country=entity['country']
            data.destination_city=entity['city']
            data.template_type=entity['template']
            if not data.shipping_marks:
                data.shipping_marks=entity['shipping_marks']
                data.warnings.append('Shipping marks supplied by existing consignee directory; verify.')
            if region:
                lines=region.splitlines()
                unit=re.search(r'\bUNIT\s*[-:#]?\s*\d+\b',region,re.I)
                if unit:data.consignee+=' '+unit[0].upper()
                data.consignee_address='\n'.join(lines[1:]) or None
            else:data.warnings.append('Consignee name normalized using known alias; address not available in labelled block.')
            break
    if region and not data.consignee:
        data.consignee=region.splitlines()[0]
        data.consignee_address='\n'.join(region.splitlines()[1:]) or None
    if not data.destination_country and ('BANGLADESH' in upper or 'DHAKA' in upper):
        data.destination_country='Bangladesh';data.destination_city='DHAKA, BD'
    for attr in ['invoice_number','export_date','consignee','consignee_address','shipping_marks','package_count','gross_weight_kg','total_value']:
        if getattr(data,attr) is None:data.warnings.append(f'{attr} not established from source; review required.')
    if not data.items:data.warnings.append('No goods extracted; invoice is incomplete.')
    for it in data.items:
        if it.unit=='G':data.warnings.append('Unit G is ambiguous; confirm meaning without automatic conversion.')
    data.warnings=list(dict.fromkeys(data.warnings))
    return data
