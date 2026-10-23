"""Check the printed invoice independently of its extracted-items sheet."""
from openpyxl import load_workbook
from openpyxl.utils.cell import range_boundaries
from openpyxl.worksheet.print_settings import PrintArea
from datetime import date, datetime
import pymupdf

from .regions import REGIONS, region_code, INDIA_DECLARATIONS


def verify_workbook(workbook, data, source, region='BD'):
    region_code(region)
    if region=='INDIA' and data.get('currency')!='USD':
        raise ValueError('India invoice publication requires USD source/default currency')
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
        if region=='INDIA' and audit.get('currency')!='USD':
            raise ValueError('India workbook currency does not match USD conversion result')
        if audit.get('source_file') != source.name or audit.get('pages_processed') != str(pages):
            raise ValueError('Workbook audit does not match the conversion result')
        if audit.get('template_type') not in ({region, None, 'None'} if region == 'BD' else {region}):
            raise ValueError('Workbook audit does not match the invoice region')
        sheet = book.active
        if region=='INDIA' and (sheet!=book.worksheets[0] or sheet.sheet_state!='visible'):
            raise ValueError('Printed India invoice sheet must be visible and active')
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
            if not any(left <= 1 and right >= 9 and top <= (1 if region=='INDIA' else layout['start']) and bottom >= total_row
                       for left, top, right, bottom in areas):
                raise ValueError('Regional print area does not include all goods and the total')
            if region == 'INDIA':
                if sheet.cell(total_row, 9).value != data.get('total_value'):
                    raise ValueError('Printed India total does not match the conversion result')
                expected_date = date.fromisoformat(data['export_date'][:10]) if data.get('export_date') else None
                headers = {
                    'C9':expected_date, 'C25':data.get('invoice_number'), 'B11':data.get('consignee'),
                    'H11':data.get('shipping_marks'), 'H12':data.get('destination_city'),
                    'H13':'C/NO. '+data['carton_range'] if data.get('carton_range') else None,
                    'D20':data['destination_country'].upper() if data.get('destination_country') else None,
                    'B27':data.get('package_count'), 'G27':data.get('gross_weight_kg'),
                    'A17':'SHIPMENT FROM:          TO: '+(data.get('destination_city') or '')+'          BY:',
                    'A18':'ON/ABT.:',
                    'A22':'PORT OF DISCHARGE: '+(data.get('port_of_discharge') or ''),
                    'A23':'SHIPMENT TERMS: '+(data.get('shipment_terms') or ''),
                    'C27':'PKG(S) ONLY.', 'H27':'KGS',
                }
                address = [line.strip() for line in (data.get('consignee_address') or '').splitlines() if line.strip()]
                if len(address)==1 and len(address[0])>60:
                    address = [part.strip() for part in address[0].split(',') if part.strip()]
                if len(address)>5:
                    address = address[:4]+['\n'.join(address[4:])]
                headers.update({f'B{12+index}':address[index] if index<len(address) else None for index in range(5)})
                cartons = [part.strip() for part in (data.get('carton_range') or '').split(',') if part.strip()]
                actual_cartons = [sheet.cell(row,1).value for row in range(layout['start'],total_row)]
                if actual_cartons != cartons+[None]*max(0,len(actual_cartons)-len(cartons)):
                    raise ValueError('Printed India goods carton references do not match the conversion result')
                headers.update({f'A{layout["start"]+index}':value for index,value in enumerate(cartons)})
                for coordinate,expected_value in headers.items():
                    cell = sheet[coordinate]
                    value = cell.value.date() if isinstance(cell.value,datetime) else cell.value
                    if value != (None if expected_value=='' else expected_value) or isinstance(value,bool):
                        raise ValueError(f'Printed India header {coordinate} does not match the conversion result')
                    if value is None:
                        continue
                    formats = {'General','@'} if isinstance(value,str) else {'General','0.00############'}
                    if cell.column==1 and cell.row>=layout['start'] and isinstance(value,str):
                        formats.add('d-mmm')  # The master uses a numeric date format; literal carton text prints unchanged.
                    if coordinate=='C9':
                        formats = {'dd-mmm-yyyy'}
                    if (cell.number_format not in formats or (isinstance(value,str) and cell.data_type!='s')):
                        raise ValueError(f'Printed India header {coordinate} must retain its literal readable format')
                    dimension = sheet.row_dimensions[cell.row]
                    if (sheet.sheet_state!='visible' or dimension.hidden or dimension.height==0
                            or any(d.hidden or d.width==0 for d in sheet.column_dimensions.values()
                                   if d.min<=cell.column<=d.max)
                            or not any(left<=cell.column<=right and top<=cell.row<=bottom
                                       for left,top,right,bottom in areas)):
                        raise ValueError(f'Printed India header {coordinate} must be visible inside the print area')
                for declaration in INDIA_DECLARATIONS:
                    cells = [cell for row in sheet for cell in row if declaration in str(cell.value or '').splitlines()]
                    if len(cells) != 1 or cells[0].row <= total_row or not any(
                            left <= cells[0].column <= right and top <= cells[0].row <= bottom
                            for left, top, right, bottom in areas):
                        raise ValueError('India declarations must appear once below the total inside the print area')
    finally:
        book.close()
