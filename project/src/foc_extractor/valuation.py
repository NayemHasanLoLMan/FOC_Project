"""Apply approved unit-based estimates, preserving explicit PDF money values."""
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from pathlib import Path

from .processing_evidence import emit

RATES_FILE = Path(__file__).resolve().parents[2] / 'valuation_rates.json'


def _positive(value, *, allow_zero=False):
    try:
        number = Decimal(str(value))
        return number if number.is_finite() and (number >= 0 if allow_zero else number > 0) else None
    except InvalidOperation:
        return None


def apply_valuation(data):
    if data.template_type not in ('BD', 'INDIA', 'JORDAN') or data.currency != 'USD':
        return
    configured = json.loads(RATES_FILE.read_text(encoding='utf-8'))
    rates = {key: _positive(configured[key]) for key in ('fabric_per_yd', 'other_per_unit', 'estimate_cap_usd')}
    if any(value is None for value in rates.values()):
        raise ValueError('Valuation rates and estimate cap must be finite positive USD numbers')
    estimates = []
    for index, item in enumerate(data.items):
        quantity = _positive(item.quantity, allow_zero=True)
        if item.unit == 'G' and re.fullmatch(r'(?:(?:METAL )?BUTTONS?|SHANK|SNAP|27L (?:SHANK|SNAP)|24L (?:SHANK|SNAP)|9\.5\s*MM RIVET|HIDDEN SNAP)', item.description.strip(), re.I):
            item.unit = 'GROSS'
        sample_count=not item.unit and bool(re.fullmatch(r'FABRIC (?:SAMPLES|SWATCHES)',item.description.strip(),re.I))
        if item.unit_price is None and item.amount is None and quantity is not None and (item.unit and item.unit.strip() or sample_count):
            key = 'fabric_per_yd' if (item.unit or '').strip().upper() in ('YD', 'YDS', 'YARD', 'YARDS') else 'other_per_unit'
            item.unit_price = float(rates[key])
            estimates.append((index, quantity, rates[key]))
        price = _positive(item.unit_price, allow_zero=True)
        if item.amount is None and quantity is not None and price is not None:
            item.amount = float((quantity * price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))
    estimated_indices = {index for index, _, _ in estimates}
    source_sum = sum((_positive(item.amount, allow_zero=True) or Decimal(0)
                      for index, item in enumerate(data.items) if index not in estimated_indices), Decimal(0))
    estimate_sum = sum((Decimal(str(data.items[index].amount)) for index in estimated_indices), Decimal(0))
    budget = max(Decimal(0), rates['estimate_cap_usd'] - source_sum).quantize(Decimal('.01'), rounding=ROUND_DOWN)
    factor = min(Decimal(1), budget / estimate_sum) if estimate_sum else Decimal(1)
    if factor < 1:
        exact = [Decimal(str(data.items[index].amount)) * factor for index, _, _ in estimates]
        allocated = [value.quantize(Decimal('.01'), rounding=ROUND_DOWN) for value in exact]
        cents = int((budget - sum(allocated)) * 100)
        order = sorted(range(len(estimates)), key=lambda i: (exact[i] - allocated[i], -i), reverse=True)
        for position in order[:cents]:
            allocated[position] += Decimal('.01')
        for (index, quantity, _), amount in zip(estimates, allocated):
            data.items[index].amount = float(amount)
            data.items[index].unit_price = float(amount / quantity) if quantity else 0.0
        emit('valuation_cap', method='estimates_only_proportional', cap=float(rates['estimate_cap_usd']),
             source_amount=float(source_sum), original_estimate=float(estimate_sum), factor=float(factor))
    for index, quantity, base_rate in estimates:
        item = data.items[index]
        emit('valuation_rate', method='approved_unit_rate', item_index=index+1, quantity=float(quantity),
             base_rate=float(base_rate), rate=item.unit_price, amount=item.amount, unit=item.unit,
             capped=factor < 1, source_refs=item.source_refs, description=item.description)
    if not any(item.unit == 'G' for item in data.items):
        data.warnings = [w for w in data.warnings if w != 'Unit G is ambiguous; confirm meaning without automatic conversion.']
    incomplete = (data.pages_processed is not None and data.pages_total is not None
                  and data.pages_processed < data.pages_total)
    amounts = [_positive(item.amount, allow_zero=True) for item in data.items]
    declared = _positive(data.total_value, allow_zero=True)
    if estimates and declared is not None and all(amount is not None for amount in amounts) and declared != sum(amounts):
        emit('field_decision', field='total_value', method='preserve_explicit_pdf_total', value=data.total_value,
             line_sum=float(sum(amounts)), reason='Declared PDF total takes priority over estimated line sums')
        data.warnings.append('Declared PDF total preserved; it differs from the priced line sum.')
    if data.total_value is None and amounts and all(amount is not None for amount in amounts) and not incomplete:
        # Preserve source-only monetary precision; round estimated shipment totals as approved.
        total = sum(amounts).quantize(Decimal('1' if estimates else '.01'), rounding=ROUND_HALF_UP)
        data.total_value = float(total)
        emit('field_source', field='total_value', method='approved_unit_rates_whole_usd' if estimates else 'source_amounts_sum',
             value=data.total_value, unrounded_sum=float(sum(amounts)), rounding_adjustment=float(total-sum(amounts)))
        data.warnings = [w for w in data.warnings if not w.startswith('total_value not established')]
    if estimates:
        data.warnings.append(f'Approved unit estimates: {len(estimates)} rows; estimate-only USD {rates["estimate_cap_usd"]} cap; calculated shipment total rounded half up to whole USD. Explicit PDF values preserved.')
    if incomplete:
        data.warnings.append('Estimated shipment total unavailable: not all PDF pages processed.')
