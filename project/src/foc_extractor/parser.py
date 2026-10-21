"""
Parser module: Extracts structured FOCData from OCR text.

Works with the unified OCRResult from ocr_engine.py.
Handles all template types: BD (EGMCL/PGCL), India (TGPL), Jordan (EJU1).

Extraction strategy:
  1. Header fields â€” entity dictionaries & regex with OCR tolerance
  2. Line items    â€” recovered tables or regex-based line item parsing
  3. Validation    â€” cross-checks package counts, carton numbers, and totals
"""

from .processing_evidence import emit
import re
from collections import Counter
from pathlib import Path

from .models import FOCData, LineItem

# ---------------------------------------------------------------------------
# Entity Directory for Known Consignees & Standard Addresses
# ---------------------------------------------------------------------------

KNOWN_CONSIGNEES = {
    "EGMCL 2": {
        "name": "EPIC GARMENTS MANUFACTURING CO.LTD.,(UNIT-2)",
        "address": (
            "SFB NO.08 (GROUND, 1ST,2ND,3RD & 4TH FLOOR)\n"
            "DEPZ EXTENSION AREA, GONOK BARI, SAVAR,\n"
            "DHAKA-1349, BANGLADESH.\n"
            "(BIN:000320579-0403)"
        ),
        "country": "Bangladesh",
        "city": "DHAKA,BD",
        "template": "BD",
        "shipping_marks": "EGMCL-FOC",
    },
    "PEARL": {
        "name": "PEARL GARMENTS COMPANY LTD.",
        "address": (
            "POLASHBARI, NABINAGAR, SAVAR\n"
            "PS: DHAKA -1349\n"
            "Bangladesh\n"
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
            "Bangladesh\n"
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
    text=re.sub(r'\b[Iil](?=\s*(?:PCS?\b|YDS\b|SETS?\b))','1',text,flags=re.I)
    return re.sub(r'(?<=\d)\s*VD[S:]?\b',' YDS',text,flags=re.I)


def _extract_invoice_number(text, filename_invoice=None):
    candidates=[f'S/{n}/{y}' for n,y in re.findall(r'\b[S5]\s*/\s*(\d{3,5})\s*/\s*(\d{2})\b',text,re.I)]
    if not candidates or filename_invoice in candidates:
        return filename_invoice
    selected=Counter(candidates).most_common(1)[0][0]
    # One uncorroborated OCR reading may use a close filename; repeated PDF evidence wins otherwise.
    if (len(candidates)==1 and filename_invoice and len(selected)==len(filename_invoice)
            and sum(a!=b for a,b in zip(selected,filename_invoice))<=2):
        return filename_invoice
    return selected


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
    m=re.search(r'\b([A-Z]{2,8})(?:\s+\d{1,2})?\s*[-â€“]?\s*FOC\b',text.upper())
    return f'{m[1]}-FOC' if m else None


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
        category=re.search(r'\b(MENS?|WOMENS?|LADIES|LADY|KIDS?)\s+(WOVEN|KNIT(?:TED)?)\b',prefix)
        garments=set(re.findall(r'\b(?:SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?)\b',prefix))
        if category and len(garments)==1 and not re.search(r'\bFABRICS?\b',s):
            composition=_material_heading(material)
            if composition:
                return f'{composition} {category[1]} {category[2]} {next(iter(garments))}'
        end=re.search(r'\b(?:WOVEN|KNIT(?:TED)?)\s+(?:FABRICS?|SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?)\b',material)
        percentages=[int(v) for v in re.findall(r'(\d{1,3})\s*%',material)]
        if end and sum(percentages)==100:
            prefix=s[:comp.start()]
            garment=re.search(r'(?<![A-Z])(MENS?|WOMENS?|LADIES|LADY|KIDS?)\s*$',prefix)
            return ((garment[1]+' ') if garment else '')+material[:end.end()]
    style=re.fullmatch(r'STYLE\s*[:#]\s*[A-Z0-9-]+\s+(.+\b(?:DRESS|SHIRT|PANTS|BLOUSE|JACKET))',s)
    return style[1] if style else s


def _material_headings(text, fabric_type=''):
    text=re.sub(r'\b\d+(?:\s*[Xx*]\s*\d+)?\s*%\s*SHRINKAGE\b','',text,flags=re.I)
    text=re.sub(r'\b\d+\s*[Xx*]\s*\d+\s*%','',text)
    text=re.sub(r'\bI?SHRINKAGE\s*:?[^\n]*','',text.upper())
    # Letter-shaped digits are repaired only inside an explicit percentage token.
    text=re.sub(r'\b[0-9IO]{1,3}(?=\s*%)',lambda m:m[0].translate(str.maketrans('IO','10')),text)
    text=re.sub(r'\s+',' ',text)
    text=re.sub(r'%\s*/','%',text)
    text=re.sub(r'\bPOLY\b','POLYESTER',text)
    text=re.sub(r'\bGENERIC\s+(?=RECYCLED)','',text)
    text=re.sub(r'\s*\(BC[IL1]\)','',text)
    text=re.sub(r'\bBC[IL1]\s+(?=COTTON\b)','',text)
    text=re.sub(r'\bRECYCLE\s+(?=POLYESTER\b)','RECYCLED ',text)
    fibers=r'(?:RECYCLED |RECYCLE |ORGANIC |BCI |USA? )?(?:VISCOSE RAYON|COTTON|POLYESTER|POLYAMIDE|NYLON|WOOL|ELASTANE|SPANDEX|LYOCELL|VISCOSE|RAYON|LINEN|SILK|METALLIC|TENCEL|STRETCH|OTHERS)'
    matches=list(re.finditer(rf'\d{{1,3}}\s*%\s*{fibers}(?![A-Z])',text))
    kind=re.search(r'\b(WOVEN|KNIT(?:TED)?)\b',fabric_type+' '+text.upper())
    if not matches:return []
    if not fabric_type and not re.search(r'\bFABRICS?\b',text) and re.search(r'\b(?:SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?)\b',text):return []
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
        if re.match(r'\s*(?:(?:MENS?|WOMENS?|LADIES|LADY|KIDS?)\s+)?(?:(?:WOVEN|KNIT(?:TED)?)\s+)?(?:SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?)\b',after):return []
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
        if ('quantity' not in columns or columns.get('quantity')==columns.get('weight')) and {'description','weight'}<=columns.keys():
            candidate=columns['weight']-1
            values=[c.content for c in table.cells if c.row_index>row and c.column_index==candidate]
            if candidate>columns['description'] and any(QTY_UNIT.search(_quantity_text(v)) for v in values):columns['quantity']=candidate
            elif columns.get('quantity')==columns['weight']:columns.pop('quantity',None)
        if {'description','quantity'}<=columns.keys():return columns,row
    return {},-1


def _extract_table_data(ocr):
    items=[]; weights=[]; parsed_pages=set(); warnings=[]
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
            if ('%' in text and not _material_heading(text,kind)
                    and re.match(r'^\s*\d{1,3}\s*%',tail)
                    and not b.get(cols['quantity'],'').strip()
                    and not b.get(cols.get('sender',-1),'').strip()
                    and _material_heading(text+' '+tail,kind)):
                a[cols['description']]=text+' '+tail
                b[cols['description']]=''
        material=None
        kinds={c.content.strip().upper() for c in table.cells if c.row_index>header
               and c.column_index==cols.get('fabric_type') and c.content.strip().upper() in ('WOVEN','KNIT')}
        fabric_type=next(iter(kinds)) if len(kinds)==1 else ''
        sample_note=any(c.row_index>header and c.column_index>cols['quantity']
                        and _fabric_sample_note(c.content) for c in table.cells)
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
            desc=explicit_item or raw_desc
            qtext=cells.get(cols['quantity'],'').strip()
            total=QTY_UNIT.fullmatch(_quantity_text(qtext))
            titles=re.findall(r'^\s*\d+\.\s*[^\n]*\b(JACKET|DRESS|SHIRT|PANTS|BLOUSE)\)?\s*$',raw_desc,re.I|re.M)
            inline=[m for c in unnamed for m in QTY_UNIT.finditer(_quantity_text(cells.get(c,'')))
                    if _normalize_unit(m['unit'])=='PCS']
            garment_parts=[]
            if (total and _normalize_unit(total['unit'])=='PCS' and len(titles)>1 and len(titles)==len(inline)
                    and abs(sum(_number(m['qty']) for m in inline)-_number(total['qty']))<1e-6):
                profile=re.search(r'\b(MENS?|WOMENS?|LADIES|LADY|KIDS?)\s+((?:\d+%\s+[A-Z]+\s+)+)(WOVEN|KNIT)\b',raw_desc,re.I)
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
                sender=(sender+' '+current_sender) if continuation else current_sender
            fabric_type=cells.get(cols.get('fabric_type',-1),'').strip().upper() or fabric_type
            if material and fabric_type:
                refined=_material_heading(material,fabric_type) or material
                if refined!=material:
                    for previous in reversed(items[table_start:]):
                        if previous.description!=material:break
                        previous.description=refined
                material=refined
            heading=_material_heading(desc,fabric_type)
            if heading and _fabric_sample_note(raw_desc):
                heading='FABRIC SAMPLES'
                warnings.append(f'Page {table.page+1}, row {r+1}: FAB annotation supplies broad fabric-sample heading for continuation rows.')
            named_product=re.search(r'\b(?:BUTTONS?|MOULDS?|CARDS?|RIVETS?|ZIPPERS?|SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|JACKETS?)\b',raw_desc,re.I)
            textile=(not named_product and (heading or material or re.search(r'%.*\b(?:COTTON|NYLON|POLYESTER)\b',raw_desc,re.I))) or re.search(r'\b(?:HANDLOOM|STRIKE OFF)\b',raw_desc,re.I)
            if (len(list(QTY_UNIT.finditer(_quantity_text(qtext))))==1 and (sample_note or _fabric_sample_note(raw_desc))
                    and not explicit_item and textile):
                desc=raw_desc='FABRIC SAMPLES'
                heading=None
                material='FABRIC SAMPLES'
                warnings.append(f'Page {table.page+1}, row {r+1}: broad fabric-sample category from FAB annotation; subtype not asserted.')
            elif (not heading and fabric_type and re.search(r'\bSHELL FABRIC\b',raw_desc,re.I)
                  and re.search(r'\b[0O]{3}\s+COTTON\b',raw_desc,re.I)):
                heading='COTTON '+fabric_type+' FABRICS'
                warnings.append(f'Page {table.page+1}, row {r+1}: cotton fabric retained without an unreadable percentage.')
            new_product=explicit_item or re.search(r'\b(?:SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|JACKETS?|TOPS|BUTTONS?|ZIPPERS?|STICKERS?|LABELS?|SWATCH(?:ES)?|CARDS?|MOULDS?|TAPES?|THREADS?|ELASTIC|RIVETS?)\b',desc,re.I)
            if ('%' in desc or new_product) and not heading:
                material=None
            if heading:material=heading
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
            desc=heading or (desc if explicit_item else material or desc)
            if not desc:
                warnings.append(f'Page {table.page+1}: quantity {qtext!r} has no established goods description.')
                continue
            # Parentheses commonly contain packing factors: 5 SETS (4 PCS/SET).
            main_q=re.sub(r'\([^)]*\)|\[[^]]*\]','',qtext)
            if re.fullmatch(NUM,main_q.strip()):
                unit=header_unit
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
                            gender=re.search(r'\b(MENS?|WOMENS?|LADIES|LADY|KIDS?)\s*$',previous,re.I)
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
                if len(descriptions)==len(main_matches):
                    parts=list(zip(descriptions,main_matches))
                elif material:
                    parts=[(material,m) for m in main_matches]
                elif re.search(r'\bEC\s+SAMPLE\s+LACE\b',raw_desc,re.I):
                    parts=[('EC SAMPLE LACE',m) for m in main_matches]
            if parts:
                for part,m in parts:
                    items.append(LineItem(_clean_material_description(part),_number(m['qty']),_normalize_unit(m['unit']),
                                          source_page=table.page+1,source_refs=[f'{table.page+1}:{table_index+1}:{r+1}']))
            else:
                warnings.append(f'Page {table.page+1}: unresolved quantity {qtext!r} for {desc[:80]!r}.')
                unit_match=re.fullmatch(rf'[0-9.,OISZil\s]*({UNITS})',qtext,re.I)
                items.append(LineItem(_clean_material_description(desc),unit=_normalize_unit(unit_match[1]) if unit_match else None,
                                      source_page=table.page+1,source_refs=[f'{table.page+1}:{table_index+1}:{r+1}']))
    return items,weights,parsed_pages,warnings


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


def parse_result(ocr_result, source):
    text=ocr_result.content; upper=text.upper()
    data=FOCData(source_file=Path(source).name,template_type='BD')
    data.ocr_backend=ocr_result.backend or None
    data.pages_processed=len(ocr_result.pages)
    data.pages_total=ocr_result.total_pages or None
    data.warnings.extend(ocr_result.warnings)
    filename=re.search(r'(\d{2})S(\d{3,5})',Path(source).stem,re.I)
    filename_invoice=f'S/{filename[2]}/{filename[1]}' if filename else None
    data.invoice_number=_extract_invoice_number(text,filename_invoice)
    emit('field_source', field='invoice_number', method='best_effort_pdf_and_filename',
         value=data.invoice_number, filename_hint=filename_invoice)
    if data.invoice_number:
        data.warnings.append(f'Best-effort invoice number: {data.invoice_number}; filename hint: {filename_invoice or "none"}. '
                             'PDF/filename agreement preferred, otherwise repeated PDF reading (first on ties); '
                             'a lone reading may use a filename within two character substitutions; filename fallback if no PDF reading.')
    data.export_date=_extract_export_date(text)
    emit('field_source', field='export_date', method='explicit_export_label', value=data.export_date)
    if data.export_date is None and not re.search(EXPORT_DATE_LABEL,text,re.I):
        data.export_date=_extract_packing_date(ocr_result.pages or [text])
        emit('field_source', field='export_date', method='first_labelled_packing_date', value=data.export_date)
        if data.export_date:
            data.warnings.append('Export date supplied by first dated PDF packing-list page (numeric dates: month/day/year).')
    data.shipping_marks=_extract_shipping_marks(text)
    data.carton_range=_extract_carton_range(text)
    # Header weight declarations precede packing tables.
    summary='\n'.join(p for p in ocr_result.pages if 'SHIPPER' in p.upper() and 'PACKAGES' in p.upper())
    summary=summary or (ocr_result.pages[0] if ocr_result.pages else text)
    data.gross_weight_kg=_extract_gross_weight(summary)
    data.tin_number = _extract_tin(text)
    data.import_cover_note = _extract_import_cover_note(text)
    data.total_value=_extract_total_value(text)
    for field in ('shipping_marks','gross_weight_kg','tin_number','import_cover_note','total_value'):
        emit('field_source', field=field, method='explicit_pdf_reading', value=getattr(data,field))
    items,weights,parsed_pages,warnings=_extract_table_data(ocr_result)
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
    data.items=_aggregate_items(items)
    if data.gross_weight_kg is None and weights:
        data.warnings.append('Packing-list weights are not established as complete gross shipment weight.')
    from .packages import packing_packages
    package_evidence=packing_packages(ocr_result,data.carton_range)
    data.package_count=package_evidence['total']
    data.warnings.append('Package count basis: '+package_evidence['basis']+'.')
    if package_evidence['reason']:data.warnings.append('Package extraction: '+package_evidence['reason'])
    region=_consignee_region(ocr_result)
    first_page=ocr_result.pages[0] if ocr_result.pages else text
    header=re.split(r'\bPACKING\s+LIST\b',first_page,maxsplit=1,flags=re.I)[0]
    recipient=re.search(r'^\s*TO\s*:\s*(.+)$',header,re.I|re.M)
    lookup=(region or (recipient[1] if recipient else header)).upper()
    lookup=re.sub(r'\bEGMCL\s*-?\s*(\d+)\b',r'EGMCL \1',lookup)
    unit=re.search(r'\b(?:UNIT\s*[-:#]?\s*|EGMCL\s+)(\d+)\b',lookup)
    directory=list(KNOWN_CONSIGNEES.items())
    if not region and data.shipping_marks:
        directory.sort(key=lambda kv:kv[1]['shipping_marks']!=data.shipping_marks)
    for key,entity in directory:
        if re.search(r'(?<![A-Z0-9])'+re.escape(key)+r'(?![A-Z0-9])',lookup):
            epic=entity['shipping_marks']=='EGMCL-FOC'
            if epic and unit and unit[1]=='2':entity=KNOWN_CONSIGNEES['EGMCL 2']
            unknown_unit=epic and unit and unit[1]!='2'
            data.consignee=entity['name']
            if unknown_unit:data.consignee+=' UNIT-'+unit[1]
            data.destination_country=entity['country']
            data.destination_city=entity['city']
            data.template_type=entity['template']
            if not data.shipping_marks:
                data.shipping_marks=entity['shipping_marks']
                data.warnings.append('Shipping marks supplied by existing consignee directory; verify.')
                emit('field_source', field='shipping_marks', method='company_directory', key=key, value=data.shipping_marks)
            if region:
                lines=region.splitlines()
                address=[line for line in lines[1:] if not re.fullmatch(r'\s*(?:TEL(?:EPHONE)?|FAX)(?:\s+NO\.?)?\s*:?\s*',line,re.I)]
                data.consignee_address='\n'.join(address) or None
                emit('field_source', field='consignee_address', method='labelled_pdf_block', value=data.consignee_address)
            if not unknown_unit:
                if not data.consignee_address:
                    data.consignee_address=entity['address']
                    data.warnings.append('Consignee address/BIN supplied by company directory.')
                    emit('field_source', field='consignee_address', method='company_directory', key=key, value=data.consignee_address)
                elif not re.search(r'\bBIN\b',data.consignee_address,re.I):
                    bin_line=next((line for line in entity['address'].splitlines() if re.search(r'\bBIN\b',line,re.I)),None)
                    if bin_line:
                        data.consignee_address+='\n'+bin_line
                        data.warnings.append('Consignee BIN supplied by company directory.')
                        emit('field_source', field='consignee_BIN', method='company_directory', key=key, value=bin_line)
            break
    if region and not data.consignee:
        data.consignee=region.splitlines()[0]
        data.consignee_address='\n'.join(region.splitlines()[1:]) or None
    if not data.destination_country and ('BANGLADESH' in upper or 'DHAKA' in upper):
        data.destination_country='Bangladesh';data.destination_city='DHAKA, BD'
    if data.template_type != 'BD':
        data.net_weight_kg = _extract_net_weight(text)
    for attr in ['invoice_number','export_date','consignee','consignee_address','shipping_marks','package_count','gross_weight_kg','total_value']:
        if getattr(data,attr) is None:data.warnings.append(f'{attr} not established from source; review required.')
    if not data.items:data.warnings.append('No goods extracted; invoice is incomplete.')
    for it in data.items:
        if it.unit=='G':data.warnings.append('Unit G is ambiguous; confirm meaning without automatic conversion.')
    data.warnings=list(dict.fromkeys(data.warnings))
    return data
