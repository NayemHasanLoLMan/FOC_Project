"""Identify approved factories and apply explicitly enabled regional defaults."""
import hashlib
import json
from pathlib import Path
import re
import unicodedata

from .processing_evidence import emit
from .regions import REGIONS, region_code

MASTER_FILE = Path(__file__).resolve().parents[2]/'factory_profiles.json'


def _address(value):
    return ' '.join(re.sub(r'[^A-Z0-9]+',' ',unicodedata.normalize('NFKC',value).upper()).split())


def _name(value):
    value = unicodedata.normalize('NFKC',value).upper()
    value = re.split(r'\bHEREINAFTER\b|\bATTN\b',value,maxsplit=1)[0]
    value = re.sub(r'\bF\s*\.\s*O\s*\.\s*C\s*\.?', 'FOC', value)
    value = re.sub(r'[^A-Z0-9]+',' ',value).strip()
    value = re.sub(r'\b(?:CO|LTD|PVT)\b',lambda m:{'CO':'COMPANY','LTD':'LIMITED','PVT':'PRIVATE'}[m[0]],value)
    value = re.sub(r'\s*(?:FOC(?:TS)?|FABRIC|GMT)(?:\s+\d+)?$','',value).strip()
    value = re.sub(r'\bUNIT\s*(\d+)\b',lambda m:'UNIT '+(m[1].lstrip('0') or '0'),value)
    return re.sub(r'\bEGMCL\s*(?:UNIT\s*)?(\d+)\b',lambda m:'EGMCL UNIT '+(m[1].lstrip('0') or '0'),value)


def _party_blocks(ocr,consignee):
    from .parser import _consignee_region
    cover = (ocr.pages or [ocr.content])[0]
    heading = re.split(r'\bPACKING\s+LIST\b|\bSENDER\s*/?\s*DEPT\b',cover,maxsplit=1,flags=re.I)[0]
    labels = list(re.finditer(r'^[ \t]*(CONSIGNEE\b\s*:?|TO\s*:)[ \t]*([^\n]*)',heading,re.I|re.M))
    blocks = []
    if labels and consignee:
        blocks.append(('parsed_consignee',consignee))
    if any(m[1].upper().startswith('CONSIGNEE') for m in labels):
        block = _consignee_region(ocr)
        if block:blocks.append(('consignee_geometry',block))
    boundary = r'\b(?:NOTIFY\s+PARTY|SHIPPER|WAREHOUSE|DESTINATION|MARKS|DATE|SENDER|BUYER|PARTICULARS|CONSIGNEE)\b|^[ \t]*TO\s*:'
    for label in labels:
        block = re.split(boundary,heading[label.start(2):],maxsplit=1,flags=re.I|re.M)[0]
        blocks.append((label[1].strip(' :').lower(),'\n'.join(block.splitlines()[:8])))
    if not labels and not re.search(r'\bSHIPPER\b',cover,re.I):
        block = re.split(boundary,heading,maxsplit=1,flags=re.I|re.M)[0].strip()
        if block:blocks.append(('shipment_heading','\n'.join(block.splitlines()[:8])))
        blocks.extend(('shipment_heading',line) for line in heading.splitlines()
                      if re.search(r'(?:FOC(?:TS)?|FABRIC|GMT)\b',line,re.I))
    return blocks


def identify_factory(ocr,region,consignee=None):
    region_code(region)
    content = MASTER_FILE.read_bytes()
    master = json.loads(content)
    if not isinstance(master,dict) or master.get('schema_version')!=1 or master.get('status') not in ('approved_identification_only','approved'):
        raise ValueError('Factory master is not approved for identification')
    profiles = master.get('factories')
    if not isinstance(profiles,dict) or not {'EGMCL','EG2'}<=profiles.keys():
        raise ValueError('Factory master needs the EGMCL and EG2 identities')
    aliases = {}; addresses = {}
    for code,profile in profiles.items():
        region_code(profile['region'])
        configured = profile.get('aliases',[])
        if not isinstance(configured,list):raise ValueError('Factory aliases must be a list')
        names = [profile['consignee'],*configured]
        if code not in ('INDIA','JORDAN'):names.append(code)
        if not all(isinstance(name,str) and name.strip() for name in names):
            raise ValueError('Factory identity names must be nonempty text')
        for name in names:
            key = _name(name)
            if key in {r['country'].upper() for r in REGIONS.values()}:
                raise ValueError('A factory identity cannot be only a country name')
            aliases.setdefault(key,set()).add(code)
        clues = profile.get('address_match',[])
        if (not isinstance(clues,list) or len(clues)<2
                or not all(isinstance(clue,str) and _address(clue) for clue in clues)):
            raise ValueError('Factory address matching needs at least two text clues')
        clues = [_address(clue) for clue in clues]
        if len(set(clues))!=len(clues) or not all(' '+clue+' ' in ' '+_address(profile['consignee_address'])+' ' for clue in clues):
            raise ValueError('Factory address clues must be distinct and present in its approved address')
        addresses[code] = clues
    evidence = []; seen = set(); unsupported_unit = False
    family = _name(profiles['EGMCL']['consignee'])
    blocks = _party_blocks(ocr,consignee)
    for source,block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()][:3]
        readings = lines+[' '.join(lines[:end]) for end in range(2,len(lines)+1)]
        for reading in readings:
            name = _name(reading)
            if (source,name) in seen:continue
            seen.add((source,name))
            if (name.startswith('EGMCL ') or name.startswith(family+' ')) and len(set(re.findall(r'\bUNIT\s+(\d+)\b',name)))>1:
                unsupported_unit = True
                evidence.append({'source':source,'text':reading,'reason':'conflicting_unit_labels'})
                continue
            unit = re.fullmatch(r'(?:EGMCL|'+re.escape(family)+r')\s+UNIT\s+(\d+)',name)
            codes = aliases.get(name,set())
            if unit:
                if unit[1] not in ('1','2'):
                    unsupported_unit = True
                    evidence.append({'source':source,'text':reading,'unsupported_unit':unit[1]})
                    continue
                codes = {'EG2' if unit[1]=='2' else 'EGMCL'}
            for code in sorted(codes):
                evidence.append({'source':source,'text':reading,'factory_id':code,'explicit_unit':bool(unit),'method':'name'})
    for source,block in blocks:
        # Geometry isolates the recipient column from the adjacent freight agent.
        if source=='parsed_consignee':continue
        if source.startswith('consignee') and source!='consignee_geometry' and any(s=='consignee_geometry' for s,_ in blocks):continue
        address = ' '+_address(block)+' '
        for code,clues in addresses.items():
            if all(' '+clue+' ' in address for clue in clues):
                evidence.append({'source':source,'text':block,'factory_id':code,
                                 'method':'address','matched_clues':clues})
    candidates = {entry['factory_id'] for entry in evidence if 'factory_id' in entry}
    # UNIT-2 refines a generic family name, never explicit UNIT-1 or a main-site address.
    if {'EGMCL','EG2'}<=candidates and not any(e.get('factory_id')=='EGMCL' and
                                            (e.get('explicit_unit') or e.get('method')=='address') for e in evidence):
        candidates.remove('EGMCL')
    foreign = any(profiles[code]['region']!=region for code in candidates)
    status = ('country_conflict' if foreign else 'ambiguous' if unsupported_unit or len(candidates)>1
              else 'matched' if candidates else 'unknown')
    result = {'factory_id':next(iter(candidates)) if status=='matched' else None,'status':status,
              'region':region,'candidates':sorted(candidates),'evidence':evidence,'page':1,
              'headings':[{'source':source,'text':text} for source,text in blocks],
              'profile_sha256':hashlib.sha256(content).hexdigest()}
    emit('factory_identification',**result)
    return result


def _defaults_master(identification):
    content = MASTER_FILE.read_bytes()
    if hashlib.sha256(content).hexdigest()!=identification['profile_sha256']:
        raise ValueError('Factory master changed after identification')
    master = json.loads(content)
    enabled = master.get('defaults_regions',[])
    if not isinstance(enabled,list) or any(region not in REGIONS for region in enabled):
        raise ValueError('Factory defaults regions must be a list of supported invoice regions')
    return master if master.get('status')=='approved' and identification['region'] in enabled else None


def apply_defaults(data, identification):
    """Apply enabled factory profiles once, during generation only."""
    region = data.template_type
    if region not in REGIONS or identification['region']!=region or identification['status']!='matched':return
    master = _defaults_master(identification)
    if master is None:return
    code = identification['factory_id']
    profile = master['factories'][code]
    if profile['region']!=region:raise ValueError('Factory defaults do not match the invoice region')
    fields = ('consignee','consignee_address','destination_country','tin_number',
              'import_cover_note','shipment_text','remarks')
    values = {field:profile[field] for field in fields if field in profile}
    required = ['consignee','consignee_address']
    if 'destination_country' in values:required.append('destination_country')
    if (not all(isinstance(values[field],str) and values[field].strip()
                for field in required)
            or any(value is not None and (not isinstance(value,str) or not value.strip() or len(value)>2000)
                   for value in values.values())):
        raise ValueError('Factory defaults must contain approved text or explicit omissions')
    for field,value in values.items():
        original = getattr(data,field)
        # None retains legacy template wording; an explicit empty string omits it.
        if value is None and field in ('shipment_text','remarks'):value = ''
        setattr(data,field,value)
        emit('field_source',field=field,value=value,original_value=original,method='approved_factory_master',
             action='omit' if value in (None,'') else 'replace',factory_id=code,
             profile_sha256=identification['profile_sha256'],source_row=profile['source_row'])
    data.warnings = [warning for warning in data.warnings if not any(
        warning.startswith(field+' not established') for field,value in values.items() if value is not None)]
    data.warnings.append('Approved factory master '+code+' applied; original PDF readings retained in processing evidence.')


def apply_jordan_origin(data, identification):
    """Apply the approved regional origin rule after source enrichment, not during edits."""
    if data.template_type!='JORDAN' or identification['region']!='JORDAN':return
    master = _defaults_master(identification)
    if master is None:return
    profile = master['factories']['JORDAN']
    if profile['origin_country']!='CHINA' or master['policies']['jordan_origin']!='always_china':
        raise ValueError('Jordan origin policy is not the approved CHINA rule')
    for index,item in enumerate(data.items,1):
        original = item.origin_country
        item.origin_country = profile['origin_country']
        emit('field_source',field='origin_country',item_index=index,value=item.origin_country,original_value=original,
             method='approved_regional_rule',policy='jordan_always_china',factory_id=identification['factory_id'],
             source_row=profile['source_row'],source_page=item.source_page,source_refs=list(item.source_refs),
             profile_sha256=identification['profile_sha256'])
    data.warnings.append('Approved Jordan origin rule applied: CHINA; original item origins retained in processing evidence.')
