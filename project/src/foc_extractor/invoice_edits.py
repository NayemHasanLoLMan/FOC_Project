"""Bounded manual invoice changes; original source records remain unchanged."""
from dataclasses import fields
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import json

from .models import FOCData, LineItem

EDIT_FIELDS = {
    'invoice_number':'Invoice number', 'export_date':'Date', 'consignee':'Consignee',
    'consignee_address':'Address / BIN', 'shipping_marks':'Shipping marks', 'carton_range':'Carton references',
    'destination_country':'Country', 'destination_city':'Destination city', 'package_count':'Packages',
    'gross_weight_kg':'Gross weight (kg)', 'tin_number':'TIN', 'import_cover_note':'Import cover note',
    'total_value':'Total (USD)',
}


def editable_fields(region='BD'):
    if region == 'BD':
        return EDIT_FIELDS
    if region == 'INDIA':
        return {**{key:label for key,label in EDIT_FIELDS.items()
                   if key not in ('destination_country','tin_number','import_cover_note')},
                'consignee_address':'Address / IEC / PAN / GST',
                'port_of_discharge':'Port of discharge', 'shipment_terms':'Shipment terms'}
    raise ValueError('Manual invoice editing is supported for Bangladesh and India')


def _number(value, name):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise ValueError(name+' must be a number or blank')
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        raise ValueError(name+' must be a number or blank') from None
    if not number.is_finite() or number < 0 or number > Decimal('1000000000000'):
        raise ValueError(name+' must be between zero and 1,000,000,000,000')
    return float(number)


def validate_changes(changes, region='BD'):
    edit_fields = editable_fields(region)
    if not isinstance(changes, dict) or not changes or set(changes)-set(edit_fields)-{'items'}:
        raise ValueError('Choose invoice fields or goods to change')
    result = {}
    for key, value in changes.items():
        if key == 'items':
            if not isinstance(value,list) or len(value)>200:
                raise ValueError('Use at most 200 goods rows')
            rows = []
            used = set()
            for row in value:
                required = {'source_index','description','quantity','unit','unit_price'} | ({'hs_code'} if region=='INDIA' else set())
                if not isinstance(row,dict) or set(row)!=required:
                    raise ValueError('Each goods row needs '+', '.join(sorted(required)))
                index = row['source_index']
                if index is not None:
                    if type(index) is not int or index < 0 or index in used:
                        raise ValueError('Invalid or repeated goods row reference')
                    used.add(index)
                description, unit = row['description'], row['unit']
                if not isinstance(description,str) or not description.strip() or len(description)>1000:
                    raise ValueError('Each goods description needs 1–1000 characters')
                if not isinstance(unit,str) or len(unit)>20:
                    raise ValueError('Goods units must be text up to 20 characters')
                rows.append({'source_index':index,'description':description.strip(),'unit':unit.strip(),
                             'quantity':_number(row['quantity'],'Quantity'), 'unit_price':_number(row['unit_price'],'Unit value')})
                if region=='INDIA':
                    code=row['hs_code']
                    if code is not None and (not isinstance(code,str) or len(code)>20):
                        raise ValueError('HS code must be text up to 20 characters or blank')
                    rows[-1]['hs_code']=(code.strip() or None) if code else None
            result[key] = rows
        elif key in ('package_count','gross_weight_kg','total_value'):
            number = _number(value,edit_fields[key])
            if key == 'package_count' and number is not None:
                if number < 1 or not number.is_integer():
                    raise ValueError('Packages must be a positive whole number or blank')
                number = int(number)
            result[key] = number
        else:
            if value is not None and (not isinstance(value,str) or len(value)>2000):
                raise ValueError(edit_fields[key]+' must be text up to 2000 characters')
            value = value.strip() if value else None
            if key == 'export_date' and value:
                try:
                    if date.fromisoformat(value).isoformat()!=value:
                        raise ValueError()
                except ValueError:
                    raise ValueError('Date must use YYYY-MM-DD') from None
            result[key] = value or None
    if len(json.dumps(result).encode())>60000:
        raise ValueError('Invoice changes are too large')
    return result


def edited_data(original, changes):
    region = original.get('template_type') or 'BD'
    changes = validate_changes(changes, region)
    original = json.loads(json.dumps(original))
    item_fields = {f.name for f in fields(LineItem)}
    original['items'] = [LineItem(**{k:v for k,v in row.items() if k in item_fields}) for row in original.get('items',[])]
    data = FOCData(**{k:v for k,v in original.items() if k in {f.name for f in fields(FOCData)}})
    data.template_type = region
    if 'items' in changes:
        rows = []
        money_changed = len(changes['items']) != len(data.items)
        for position, change in enumerate(changes['items']):
            index = change['source_index']
            if index is not None and index >= len(data.items):
                raise ValueError('Goods row reference is outside this invoice')
            item = data.items[index] if index is not None else LineItem('')
            same_money = index is not None and all(getattr(item,k)==change[k] for k in ('quantity','unit','unit_price'))
            money_changed |= not same_money or index != position
            source_keys = ('description','quantity','unit','hs_code') if region=='INDIA' else ('description','quantity','unit')
            same_source = index is not None and all(getattr(item,k)==change[k] for k in source_keys)
            for key in ('description','quantity','unit','unit_price'):
                setattr(item,key,change[key])
            if not same_source:
                item.source_page = None
                item.source_refs = []
                item.confidence = None
                item.hs_code = None
                item.weight_kg = None
            if region=='INDIA':
                item.hs_code=change['hs_code']
            if region!='INDIA' or not same_money:
                item.amount = (float((Decimal(str(item.quantity))*Decimal(str(item.unit_price))).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
                               if item.quantity is not None and item.unit_price is not None else None)
            rows.append(item)
        data.items = rows
        if 'total_value' not in changes and (region!='INDIA' or money_changed):
            data.total_value = (float(sum((Decimal(str(i.amount)) for i in rows),Decimal(0)).quantize(Decimal('.01' if region=='INDIA' else '1'),rounding=ROUND_HALF_UP))
                                if rows and all(i.amount is not None for i in rows) else None)
    for key,value in changes.items():
        if key != 'items':
            setattr(data,key,value)
    if region=='BD':
        data.net_weight_kg = None
    return data
