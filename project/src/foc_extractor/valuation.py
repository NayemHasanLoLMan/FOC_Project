"""Apply the approved approximate USD rates to supported BD goods only."""
from .processing_evidence import emit
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


RATES_FILE = Path(__file__).resolve().parents[2] / 'valuation_rates.json'
RULES = [
    ('fabric_per_yd', 'YDS', r'\bFABRICS?\b|%\s*(?:COTTON|POLYESTER|NYLON|LINEN|VISCOSE|RAYON|LYOCELL|POLYAMIDE)\b'),
    ('die_mould_per_set', 'SETS', r'^DIE MOULD(?:\s*\([^)]*\))?$'),
    ('shank_rivet_per_pc', 'PCS', r'^SHANK\s*&\s*RIVET\b'),
    ('fabric_card_per_pc', 'PCS', r'^FABRIC CARD$'),
    ('metal_snap_per_set', 'SETS', r'^(?:METAL|MEATAL) SNAP$'),
    ('zipper_clip_per_pc', 'PCS', r'^ZIPPER CLIP$'),
    ('fabric_swatch_per_set', 'SETS', r'^FABRIC SWATCH(?:ES)?$'),
    ('bulk_trim_card_per_set', 'SETS', r'^BULK TRIM CARD$'),
    ('27l_shank_per_gross', 'GROSS', r'^27L SHANK$'),
    ('27l_snap_per_gross', 'GROSS', r'^27L SNAP$'),
    ('24l_shank_per_gross', 'GROSS', r'^24L SHANK$'),
    ('24l_snap_per_gross', 'GROSS', r'^24L SNAP$'),
    ('9_5mm_rivet_per_gross', 'GROSS', r'^9\.5\s*MM RIVET$'),
    ('hidden_snap_per_gross', 'GROSS', r'^HIDDEN SNAP$'),
    ('fabric_swatch_card_per_set', 'SETS', r'^FABRIC SWATCH(?:ES)? CARD$'),
    ('trim_card_per_pc', 'PCS', r'^TRIM CARD$'),
    ('ladies_cotton_stretch_pants_per_pc', 'PCS', r'^(?:LADY|LADIES|WOMENS?)\b.*\bCOTTON\b.*\b(?:SPANDEX|ELASTANE|STRETCH)\b.*\bPANTS$'),
    ('mens_cotton_pants_per_pc', 'PCS', r"^MEN'?S?\b.*\b100% COTTON\b.*\bPANTS$"),
    ('kids_cotton_dress_per_pc', 'PCS', r"^KIDS?'?\b.*\b100% COTTON\b.*\bDRESS$"),
    ('ladies_cotton_dress_per_pc', 'PCS', r'^(?:LADY|LADIES|WOMENS?)\b.*\b100% COTTON\b.*\bDRESS$'),
    # Sample evidence takes priority over garment words inside booking descriptions.
    ('fabric_sample_per_pc', 'PCS',
     r'\b(?:FABRIC (?:SWATCH(?:ES)?|SAMPLES?)|STRIKE\s*OFF|HANDLOOM|YARN DYED|FABRIC BOOKING|CVC CARRYOVER)\b'
     r'|^(?!.*\b(?:PANTS|SHIRTS?|BLOUSES?|DRESS|JACKET)\b).*?\b\d+(?:\.\d+)?%\s*'
     r'(?:COTTON|US(?:A)? COTTON|NYLON|POLYESTER|VISCOSE|RAYON|LINEN|LYOCELL|POLYAMIDE)\b'),
    ('fabric_sample_per_set', 'SETS', r'\bFAB(?:RIC)?\b'),
    ('zipper_per_pc', 'PCS', r'^ZIPPERS?$'),
    ('shirt_per_pc', 'PCS', r'\bSHIRTS?\b'),
    ('blouse_per_pc', 'PCS', r'\bBLOUSES?\b'),
    ('fabric_blanket_per_pack', 'PACKS', r'^BULK FABRIC BLANKET\b'),
    ('taper_card_per_pack', 'PACKS', r'^TAPER CARD\b'),
    ('lace_per_yd', 'YDS', r'\bLACE\b'),
    ('size_sticker_per_pc', 'PCS', r'^SIZE STICKERS?$'),
    ('fabric_hanger_per_pc', 'PCS', r'^FABRIC HANGERS?$'),
    ('part_card_per_pc', 'PCS', r'^(?:EMBY\s+)?MF PART CARDS?$'),
    ('felt_patch_per_pc', 'PCS', r'^FELT PATCH(?:ES)?$'),
    ('button_per_gross', 'GROSS', r'^(?:SHANK|SNAP) BUTTONS?$'),
    ('pants_per_pc', 'PCS', r'\bPANTS\b'),
    ('dress_per_pc', 'PCS', r'\bDRESS(?:ES)?\b'),
    ('jacket_per_pc', 'PCS', r'\bJACKETS?\b'),
]


def _positive(value):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and number > 0 else None
    except InvalidOperation:
        return None


def apply_valuation(data):
    if data.template_type != 'BD' or data.currency != 'USD':
        return
    configured = json.loads(RATES_FILE.read_text(encoding='utf-8'))
    rates = {key: _positive(configured[key]) for key, _, _ in RULES}
    if any(rate is None for rate in rates.values()):
        raise ValueError('Valuation rates must be finite positive USD numbers')
    for item in data.items:
        description = ' '.join(item.description.upper().split())
        for key, unit, pattern in RULES:
            if not re.search(pattern, description):
                continue
            # Only these confirmed button categories interpret abbreviated G as gross.
            if key in ('27l_shank_per_gross', '27l_snap_per_gross', '24l_shank_per_gross',
                       '24l_snap_per_gross', '9_5mm_rivet_per_gross', 'hidden_snap_per_gross') and item.unit == 'G':
                item.unit = 'GROSS'
            if item.unit == unit:
                if item.unit_price is None:
                    item.unit_price = float(rates[key])
                    emit('valuation_rate', method='approved_approximate_rate', rule=key, rate=item.unit_price,
                         unit=item.unit, source_refs=item.source_refs, description=item.description)
                break
        quantity, price = _positive(item.quantity), _positive(item.unit_price)
        if item.amount is None and quantity is not None and price is not None:
            item.amount = float((quantity * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
    if not any(item.unit == 'G' for item in data.items):
        data.warnings = [w for w in data.warnings if w != 'Unit G is ambiguous; confirm meaning without automatic conversion.']
    priced = sum(item.amount is not None for item in data.items)
    data.warnings.append(f'Approved approximate USD valuation: {priced}/{len(data.items)} rows priced; final calculated total rounded to nearest whole USD (half up).')
    incomplete_pdf = (data.pages_processed is not None and data.pages_total is not None
                      and data.pages_processed < data.pages_total)
    if incomplete_pdf:
        data.warnings.append('Estimated shipment total unavailable: not all PDF pages processed.')
    if data.total_value is None and data.items and priced == len(data.items) and not incomplete_pdf:
        total = sum(Decimal(str(item.amount)) for item in data.items)
        data.total_value = float(total.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        emit('field_source', field='total_value', method='approved_rates_sum_whole_usd_half_up', value=data.total_value)
        data.warnings = [w for w in data.warnings if not w.startswith('total_value not established')]
