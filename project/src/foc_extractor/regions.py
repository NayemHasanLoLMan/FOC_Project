"""Supported invoice layouts and explicit country identity."""
from pathlib import Path
import re

REGIONS = {
    'BD': {'folder': 'bangladesh', 'country': 'Bangladesh', 'start': 33, 'quantity': 7, 'unit': 8, 'total_column': 6},
    'INDIA': {'folder': 'india', 'country': 'India', 'start': 33, 'quantity': 6, 'unit': 7, 'total_column': 8},
    'JORDAN': {'folder': 'jordan', 'country': 'Jordan', 'start': 27, 'quantity': 7, 'unit': 8, 'total_column': 8},
}


def region_code(value):
    if not isinstance(value, str) or value not in REGIONS:
        raise ValueError('Region must be BD, INDIA or JORDAN')
    return value


def template_region(path):
    return next((code for code in REGIONS if re.search(r'(?<![A-Z])'+code+r'(?![A-Z])', Path(path).stem.upper())), None)


def select_region(data, requested=None, cover=''):
    """Check consignment evidence only; packing-page recipient conflicts need separate review."""
    selected = region_code(requested or data.template_type or 'BD')
    countries = [data.destination_country] if data.destination_country else []
    declared = re.search(r'\b(?:DESTINATION\s+COUNTRY|COUNTRY\s+OF\s+(?:ULTIMATE\s+)?DESTINATION)\s*[:\-]?\s*([A-Za-z]+)', cover, re.I)
    if declared:
        countries.append(declared[1])
    for country in countries:
        if country.strip().casefold() != REGIONS[selected]['country'].casefold():
            raise ValueError(f'Invoice region {selected} conflicts with destination {country}')
    if data.template_type not in (None, 'BD', selected):
        raise ValueError('Invoice region conflicts with the recognized consignee')
    data.template_type = selected
    return selected
