"""Approved invoice summaries, retaining source rows in processing evidence."""
from collections import defaultdict
from dataclasses import asdict
import re

from .parser import (_aggregate_items, _clean_material_description, _fabric_sample_category,
                     _material_heading, _normalize_unit, _repair_goods_text)
from .processing_evidence import emit


def _heading(description):
    text = re.sub(r'\s+', ' ', _repair_goods_text(description)).strip().upper()
    if re.search(r'\bCARD\b', text):
        return _clean_material_description(text)
    sample = _fabric_sample_category(text)
    if sample:
        return sample
    composition = re.search(r'\d{1,3}\s*%', text)
    kind = re.search(r'\b(?:WOVEN|KNIT(?:TED)?)\b', text)
    garment = re.search(r'\b(?:GARMENTS?|SHIRTS?|PANTS?|DRESS(?:ES)?|BLOUSES?|TOPS?|JACKETS?|'
                        r'HOODIES?|CREW|JOGGERS?|SWEATPANTS?|TEES?|POLOS?|SHORTS?|SKIRTS?|SWEATERS?)\b', text)
    if composition and kind and garment and not re.search(r'\bFABRICS?\b', text):
        material = text[composition.start():kind.end()] if kind.start()>composition.start() else text[composition.start():]
        material = _material_heading(re.sub(r'\bSPANDE\b', 'SPANDEX', material), kind[0])
        if material:
            wearer = re.search(r"\b(MEN'?S?|WOMEN'?S?|LADIES|LADY|KIDS?|CHILDREN|GIRLS?|BOYS?)\b", text[:composition.start()])
            wearer = wearer[0].replace("'", '') if wearer else ''
            wearer = {'MEN':"MEN'S",'MENS':"MEN'S",'WOMEN':"WOMEN'S",'WOMENS':"WOMEN'S",
                      'LADY':'LADIES','KID':'KIDS','CHILDREN':'KIDS'}.get(wearer, wearer)
            condition = (' (NON-MUTILATED)' if re.search(r'\bNON[ -]MUTILATED\b', text) else
                         ' (MUTILATED)' if re.search(r'\bMUTILATED\b', text) else '')
            return (wearer+' '+material.removesuffix(' FABRICS')).strip()+condition
    if not re.search(r'\b(?:DIES?|MOULDS?|MOLDS?)\b', text):
        categories = [('THREAD',r'\bTHREAD\b'),('BUTTON',r'\bBUTTONS?\b'),
                      ('ELASTIC',r'\bELASTIC\b'),('LABEL',r'\bLABELS?\b'),
                      ('SEAL CORD',r'\bSEAL[ -]+CORD\b'),('HANGTAG',r'\bHANG\s*TAGS?E?\b'),
                      ('INTERLINING',r'\bINTERLINING\b'),('SHANK',r'\bSHANK\b'),('SNAP',r'\bSNAPS?\b')]
        matches = [name for name,pattern in categories if re.search(pattern,text)]
        if len(matches)==1:
            material = _material_heading(text) if composition else None
            return ((material.removesuffix(' FABRICS')+' ') if material else '')+matches[0]
    if re.search(r'\bFABRICS?\b', text):
        return _material_heading(text)
    return None


def summarize_goods(data, ocr=None):
    before = [asdict(item) for item in data.items]
    conditions={}
    for index,table in enumerate(ocr.tables if ocr else [],1):
        labels={re.sub(r'\s+',' ',c.content.strip().upper()) for c in table.cells
                if re.fullmatch(r'(?:NON[ -])?MUTILATED(?:\s+SAMPLES)?',c.content.strip(),re.I)}
        if len(labels)==1:
            conditions[table.page+1,index]='NON-MUTILATED' if next(iter(labels)).startswith('NON') else 'MUTILATED'
    for item in data.items:
        labels={conditions.get(tuple(map(int,ref.split(':')[:2]))) for ref in item.source_refs
                if re.fullmatch(r'\d+:\d+:\d+',ref)}-{None}
        if len(labels)==1 and not re.search(r'\bMUTILATED\b',item.description,re.I) and re.search(
                r'\b(?:GARMENTS?|SHIRTS?|PANTS?|SHORTS?|TOPS?|DRESS(?:ES)?|LEG\s+PANELS?)\b',item.description,re.I):
            item.description+=' ('+next(iter(labels))+')'
    headings = [_heading(item.description) or item.description for item in data.items]
    units = defaultdict(dict)
    for item,heading in zip(data.items,headings):
        if item.unit:
            item.unit = _normalize_unit(item.unit)
            units[heading,item.hs_code,item.origin_country].setdefault(item.unit,[]).extend(item.source_refs)
    recovered = []
    for index,(item,heading) in enumerate(zip(data.items,headings)):
        candidates = units[heading,item.hs_code,item.origin_country]
        if not item.unit and len(candidates)==1 and set(candidates)!={'G'}:
            item.unit = next(iter(candidates))
            recovered.append({'item':index+1,'unit':item.unit,'source_refs':list(item.source_refs),
                              'supporting_refs':list(dict.fromkeys(candidates[item.unit]))})
    for item,heading in zip(data.items,headings):
        if item.quantity is not None:
            item.description = heading
    data.items = _aggregate_items(data.items,clean=False,sum_weights=True)
    after = [asdict(item) for item in data.items]
    if before!=after:
        emit('field_evidence',field='goods_grouping',evidence={
            'source_items':before,'grouped_items':after,'recovered_units':recovered,
            'method':'approved_category_and_composition_summary'})
