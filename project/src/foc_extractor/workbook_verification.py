"""Check the printed invoice independently of its extracted-items sheet."""
from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries
from openpyxl.worksheet.print_settings import PrintArea
import pymupdf

from .regions import REGIONS, region_code


def verify_workbook(workbook, data, source, region='BD'):
    region_code(region)
    if data.get('template_type') not in (region, None if region == 'BD' else region):
        raise ValueError('Converter result does not match the queued invoice region')
    if data.get('source_file') != source.name or not isinstance(data.get('items'), list):
        raise ValueError('Converter result does not identify this input snapshot')
    with pymupdf.open(source) as pdf:
        pages = len(pdf)
    if data.get('pages_processed') != pages or data.get('pages_total') != pages:
        raise ValueError('Refusing to publish an invoice with incomplete source-page coverage')
    book = load_workbook(workbook)
    try:
        audit = dict(book['Extraction_Audit'].iter_rows(min_row=2, max_col=2, values_only=True))
        if audit.get('source_file') != source.name or audit.get('pages_processed') != str(pages):
            raise ValueError('Workbook audit does not match the conversion result')
        if audit.get('template_type') not in ({region, None, 'None'} if region == 'BD' else {region}):
            raise ValueError('Workbook audit does not match the invoice region')
        sheet = book.active
        layout = REGIONS[region]
        totals = [row for row in range(layout['start'], sheet.max_row + 1)
                  if sheet.cell(row, layout['total_column']).value == 'TOTAL VALUE:']
        if len(totals) != 1:
            raise ValueError('Printed invoice must have one identifiable total below its goods')
        total_row = totals[0]
        columns = [2, layout['quantity'], layout['unit']]
        keys = ['description', 'quantity', 'unit']
        if region == 'INDIA':
            columns += [5, 9]; keys += ['hs_code', 'amount']
        elif region == 'JORDAN':
            columns += [6, 9]; keys += ['weight_kg', 'amount']
        actual = [tuple(sheet.cell(row, column).value for column in columns)
                  for row in range(layout['start'], total_row) if sheet.cell(row, 2).value is not None]
        expected = [tuple(item.get(key) or None if key in ('unit', 'hs_code') else item.get(key) for key in keys)
                    for item in data['items']]
        if actual != expected:
            raise ValueError('Printed goods do not match the conversion result')
        if region != 'BD':
            # Legacy regional masters still have unsafe overflow/print settings; reject until their writer stage fixes them.
            areas = [range_boundaries(str(area)) for area in PrintArea.from_string(sheet.print_area).ranges] if sheet.print_area else []
            if not any(left <= 1 and right >= 9 and top <= layout['start'] and bottom >= total_row
                       for left, top, right, bottom in areas):
                raise ValueError('Regional print area does not include all goods and the total')
    finally:
        book.close()
