"""
Excel template populator for customs invoices.

Supports 3 regional blank template formats:
  - BD (Bangladesh / EGMCL / PGCL) -> templates/BD_template.xlsx
  - INDIA (India / TGPL)           -> templates/INDIA_template.xlsx
  - JORDAN (Jordan / EJU1)         -> templates/JORDAN_template.xlsx

Includes safe merged-cell handling, label-search fallback for custom templates,
and Extraction_Audit / Extracted_Items sheets.
"""

from pathlib import Path
from copy import copy
from datetime import date
import math
import re
from tempfile import NamedTemporaryFile
from textwrap import wrap
from openpyxl import load_workbook
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont
from .models import FOCData
from .regions import select_region, template_region


def _safe_write(ws, r: int, c: int, val):
    """Safely write to a cell, redirecting to anchor cell if MergedCell."""
    cell = ws.cell(r, c)
    if type(cell).__name__ == "MergedCell":
        for rng in ws.merged_cells.ranges:
            if cell.coordinate in rng:
                cell = ws.cell(rng.min_row, rng.min_col)
                break
    cell.value = val
    if isinstance(val, str):
        cell.data_type = 's'


def _find_label(ws, label: str):
    """Find a cell containing a case-insensitive label substring."""
    label = label.upper()
    for row in ws.iter_rows():
        for cell in row:
            if cell.value and label in str(cell.value).upper():
                return cell
    return None


def _next_writable(ws, cell):
    """Search right, then below, avoiding merged non-anchor cells."""
    merged_nonanchors = {
        c.coordinate for rng in ws.merged_cells.ranges
        for row in ws[rng.coord] for c in row
        if c.coordinate != rng.start_cell.coordinate
    }
    for dc, dr in [(1, 0), (2, 0), (0, 1), (1, 1), (0, 2)]:
        c = ws.cell(cell.row + dr, cell.column + dc)
        if c.coordinate not in merged_nonanchors and (c.value is None or str(c.value).strip() == ""):
            return c
    return ws.cell(cell.row, cell.column + 1)


def _split_address_lines(address: str | None) -> list[str]:
    """Split multi-line or comma-separated address into clean lines."""
    if not address:
        return []
    lines = [l.strip() for l in address.split("\n") if l.strip()]
    if len(lines) == 1 and len(lines[0]) > 60:
        parts = [p.strip() for p in lines[0].split(",") if p.strip()]
        lines = parts
    return lines


def _populate_bd(ws, data: FOCData):
    """Populate BD (Bangladesh) customs invoice template."""
    def red(cell):
        font = copy(cell.font)
        font.color = 'FFFF0000'
        cell.font = font

    for coordinate in ('C9', 'H11', 'H12', 'I13', 'B11', 'E21', 'A23', 'C25', 'B27', 'G27', 'F28', 'G28', 'H28', 'A29', 'G40'):
        cell = ws[coordinate]
        _safe_write(ws, cell.row, cell.column, None)
    for row in range(12, 18):
        _safe_write(ws, row, 2, None)
    ws.merge_cells('C9:F9')
    ws.merge_cells('H9:I9')
    ws['H9'].alignment=copy(ws['H9'].alignment)
    header_alignment=copy(ws['H9'].alignment)
    header_alignment.wrap_text=True
    ws['H9'].alignment=header_alignment
    ws.row_dimensions[9].height=max(30,ws.row_dimensions[9].height or 0)
    if data.export_date:
        _safe_write(ws, 9, 3, date.fromisoformat(data.export_date[:10]))
        ws['C9'].number_format = 'dd-mmm-yyyy'
    if data.shipping_marks:
        _safe_write(ws, 11, 8, data.shipping_marks)  # H11
    _safe_write(ws, 12, 8, data.destination_city)  # H12
    if data.carton_range:
        ws.merge_cells('H13:I13')
        _safe_write(ws, 13, 8, f'C/NO. {data.carton_range}')
        font = ws['H13'].font
        ws['H13'].value = CellRichText(
            TextBlock(InlineFont(rFont=font.name,sz=font.sz,color='FF000000'),'C/NO. '),
            TextBlock(InlineFont(rFont=font.name,sz=font.sz,color='FFFF0000'),data.carton_range))
        carton_alignment=copy(ws['H13'].alignment)
        carton_alignment.wrap_text=True
        carton_alignment.vertical='top'
        ws['H13'].alignment=carton_alignment
        ws.row_dimensions[13].height=max(30,15*math.ceil((6+len(data.carton_range))/13))

    if data.consignee:
        _safe_write(ws, 11, 2, data.consignee)  # B11
        alignment = copy(ws['B11'].alignment)
        alignment.wrap_text = True
        alignment.vertical = 'top'
        ws['B11'].alignment = alignment
        ws.row_dimensions[11].height = max(ws.row_dimensions[11].height or 19,
                                           15 * math.ceil(len(data.consignee) / 55))
    addr_lines = _split_address_lines(data.consignee_address)
    addr_lines = [re.sub(r'^[\[(]?\s*BIN\s*[:#]?\s*([0-9 -]+?)\s*[)\]]?$',
                         lambda match:'BIN : '+match[1].strip(),line,flags=re.I) for line in addr_lines]
    if len(addr_lines) > 6:
        addr_lines = addr_lines[:5] + ['\n'.join(addr_lines[5:])]
    for row in range(12 + len(addr_lines), 18):
        if row != 13 or not data.carton_range:
            ws.row_dimensions[row].height = 4
    for i, line in enumerate(addr_lines):
        ws.merge_cells(start_row=12+i,start_column=2,end_row=12+i,end_column=6)
        _safe_write(ws, 12 + i, 2, line)
        if re.search(r'\bBIN\b',line,re.I):
            red(ws.cell(12+i,2))
        alignment = copy(ws.cell(12 + i, 2).alignment)
        alignment.wrap_text = True
        alignment.vertical='top'
        ws.cell(12 + i, 2).alignment = alignment
        ws.row_dimensions[12 + i].height = max(ws.row_dimensions[12 + i].height or 15,
                                              15 * sum(max(1, math.ceil(len(s) / 55)) for s in line.splitlines()))

    if data.destination_country:
        _safe_write(ws, 21, 5, data.destination_country.upper())  # E21
    if data.invoice_number:
        _safe_write(ws, 25, 3, data.invoice_number)  # C25
    if data.import_cover_note:
        ws.merge_cells('A23:I23')
        _safe_write(ws,23,1,data.import_cover_note)
        ws['A23']._style=copy(ws['A42']._style)
        red(ws['A23'])
        alignment=copy(ws['A23'].alignment)
        alignment.wrap_text=True
        ws['A23'].alignment=alignment
        ws.row_dimensions[23].height=max(18,16*math.ceil(len(data.import_cover_note)/105))
    if data.package_count is not None:
        _safe_write(ws, 27, 2, int(data.package_count))  # B27
    if data.gross_weight_kg is not None:
        _safe_write(ws, 27, 7, float(data.gross_weight_kg))  # G27
        ws['G27'].number_format='0.00############'
    ws.row_dimensions[28].height = 4


    # Preserve the BD design, growing its detail area before totals/footer.
    start_row = 33
    carton_labels=[part.strip() for part in (data.carton_range or '').split(',') if part.strip()]
    if not carton_labels and data.package_count:
        # Rose's invoice uses a bare count; other BD formats use the PKGS label.
        carton_labels=[str(int(data.package_count)) if data.shipping_marks=='ROSE-FOC' else f'{int(data.package_count)} PKGS']
    extra = max(0, max(len(data.items),len(carton_labels)) - 6)
    shifted_merges = [copy(rng) for rng in ws.merged_cells.ranges if rng.min_row >= 39]
    if extra:
        for rng in shifted_merges:
            ws.unmerge_cells(str(rng))
        dimensions = {r:copy(dim) for r,dim in ws.row_dimensions.items() if r>=39}
        ws.insert_rows(39, extra)
        for r,dim in sorted(dimensions.items(),reverse=True):
            ws.row_dimensions[r+extra] = dim
            ws.row_dimensions[r+extra].index = r+extra
        for rng in shifted_merges:
            rng.shift(row_shift=extra)
            ws.merge_cells(str(rng))
    # Remove the duplicate footer already present in the supplied blank template.
    ws.cell(45+extra,1).value = None
    ws.cell(46+extra,1).value = None
    for i, item in enumerate(data.items):
        r = start_row + i
        for col in range(1,10):
            ws.cell(r,col)._style = copy(ws.cell(start_row,col)._style)
        ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=6)
        ws.cell(r,2).alignment = copy(ws.cell(start_row,2).alignment)
        alignment = copy(ws.cell(r,2).alignment)
        alignment.wrap_text = True
        alignment.vertical = 'top'
        ws.cell(r,2).alignment = alignment
        line_count = sum(max(1, len(wrap(part, width=55))) for part in item.description.splitlines())
        ws.row_dimensions[r].height = max(24, 15 * line_count + 4)
        _safe_write(ws, r, 2, item.description)
        if item.quantity is not None:
            _safe_write(ws, r, 7, item.quantity)
            ws.cell(r,7).number_format='#,##0' if float(item.quantity).is_integer() else '#,##0.####'
        if item.unit:
            _safe_write(ws, r, 8, item.unit)
        for col in (7,8):
            numeric_alignment=copy(ws.cell(r,col).alignment)
            numeric_alignment.vertical='top'
            ws.cell(r,col).alignment=numeric_alignment

    for index,label in enumerate(carton_labels):
        cell=ws.cell(start_row+index,1)
        cell._style=copy(ws.cell(start_row,1)._style)
        _safe_write(ws,cell.row,1,label)
        red(cell)
        alignment=copy(cell.alignment)
        alignment.wrap_text=True
        alignment.vertical='top'
        cell.alignment=alignment
        ws.row_dimensions[cell.row].height=max(ws.row_dimensions[cell.row].height or 15,
                                               15*math.ceil(len(label)/max(1,ws.column_dimensions['A'].width)))

    tot_row = 40 + extra
    _safe_write(ws,tot_row+1,1,None)
    if data.tin_number:
        ws.merge_cells(start_row=tot_row+1,start_column=1,end_row=tot_row+1,end_column=9)
        _safe_write(ws,tot_row+1,1,'TIN # '+data.tin_number)
        ws.cell(tot_row+1,1)._style=copy(ws.cell(tot_row+2,1)._style)
        red(ws.cell(tot_row+1,1))
        ws.row_dimensions[tot_row+1].height=max(18,ws.row_dimensions[tot_row+1].height or 0)
    _safe_write(ws, tot_row, 6, "TOTAL VALUE:")
    for rng in list(ws.merged_cells.ranges):
        if rng.min_row==tot_row and rng.min_col==7:ws.unmerge_cells(str(rng))
    ws.merge_cells(start_row=tot_row,start_column=7,end_row=tot_row,end_column=9)
    _safe_write(ws, tot_row, 7, data.total_value)
    ws.cell(tot_row,7).number_format = '"USD "0.00'
    total_alignment=copy(ws.cell(tot_row,7).alignment)
    total_alignment.wrap_text=True
    ws.cell(tot_row,7).alignment=total_alignment
    ws.row_dimensions[tot_row].height=max(30,ws.row_dimensions[tot_row].height or 0)
    for r in (tot_row+2,tot_row+3):
        ws.row_dimensions[r].height=max(15,ws.row_dimensions[r].height or 0)
    ws.print_area = f'A1:I{43+extra}'
    ws.print_title_rows = '30:30'
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = 'portrait'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins.left = ws.page_margins.right = .4
    ws.page_margins.top = .5
    ws.page_margins.bottom = .55
    ws.page_margins.header = ws.page_margins.footer = .2
    # Excel interprets ampersands in header/footer text as field codes.
    identity = (data.invoice_number or Path(data.source_file).stem).replace('&', '&&')
    ws.HeaderFooter.differentFirst = True
    ws.HeaderFooter.differentOddEven = False
    company = str(ws['A1'].value or ws['E1'].value or '').replace('&', '&&')
    ws.oddHeader.left.text = company
    ws.oddHeader.right.text = identity
    for part in (ws.oddHeader.left, ws.oddHeader.right):
        part.font = 'Arial'
        part.size = 8
        part.color = '606060'
    ws.firstHeader.left.text = ws.firstHeader.center.text = ws.firstHeader.right.text = None
    ws.oddFooter.left.text = identity
    ws.oddFooter.center.text = None
    ws.oddFooter.right.text = 'Page &P of &N'
    for part in (ws.oddFooter.left, ws.oddFooter.right):
        part.font = 'Arial'
        part.size = 8
        part.color = '606060'
    ws.firstFooter = copy(ws.oddFooter)


def _populate_india(ws, data: FOCData):
    """Populate INDIA customs invoice template."""
    if data.export_date:
        _safe_write(ws, 9, 3, data.export_date)   # C9
    if data.shipping_marks:
        _safe_write(ws, 11, 8, data.shipping_marks)  # H11
    _safe_write(ws, 12, 8, data.destination_city or "CHENNAI, INDIA")  # H12
    if data.carton_range:
        _safe_write(ws, 13, 9, data.carton_range)  # I13

    if data.consignee:
        _safe_write(ws, 11, 2, data.consignee)  # B11
    addr_lines = _split_address_lines(data.consignee_address)
    for i, line in enumerate(addr_lines[:5]):
        _safe_write(ws, 12 + i, 2, line)

    if data.destination_country:
        _safe_write(ws, 20, 4, data.destination_country.upper())  # D20
    if data.invoice_number:
        _safe_write(ws, 25, 3, data.invoice_number)  # C25
    if data.package_count is not None:
        _safe_write(ws, 27, 2, int(data.package_count))  # B27
    if data.gross_weight_kg is not None:
        _safe_write(ws, 27, 7, float(data.gross_weight_kg))  # G27

    # Line items starting row 33
    start_row = 33
    max_item_rows = 6
    for i, item in enumerate(data.items[:max_item_rows]):
        r = start_row + i
        if data.carton_range and i == 0:
            _safe_write(ws, r, 1, data.carton_range)
        _safe_write(ws, r, 2, item.description)
        if item.hs_code:
            _safe_write(ws, r, 5, item.hs_code)
        if item.quantity is not None:
            _safe_write(ws, r, 6, item.quantity)
        if item.unit:
            _safe_write(ws, r, 7, item.unit)
        if item.amount is not None:
            _safe_write(ws, r, 9, item.amount)

    if data.total_value is not None:
        tot_row = 42
        _safe_write(ws, tot_row, 8, "TOTAL VALUE:")
        _safe_write(ws, tot_row, 9, f"{data.total_value:.2f}")


def _populate_jordan(ws, data: FOCData):
    """Populate JORDAN customs invoice template."""
    if data.export_date:
        _safe_write(ws, 9, 3, data.export_date)   # C9
    if data.shipping_marks:
        _safe_write(ws, 9, 9, data.shipping_marks)   # I9
    _safe_write(ws, 10, 9, data.destination_city or "JORDAN")  # I10
    if data.carton_range:
        _safe_write(ws, 11, 10, data.carton_range)  # J11

    if data.consignee:
        _safe_write(ws, 11, 3, data.consignee)  # C11
    addr_lines = _split_address_lines(data.consignee_address)
    for i, line in enumerate(addr_lines[:4]):
        _safe_write(ws, 12 + i, 3, line)

    if data.destination_country:
        _safe_write(ws, 16, 4, data.destination_country.upper())  # D16
    if data.invoice_number:
        _safe_write(ws, 18, 3, data.invoice_number)  # C18
    if data.package_count is not None:
        _safe_write(ws, 21, 2, int(data.package_count))  # B21
    if data.gross_weight_kg is not None:
        _safe_write(ws, 21, 6, float(data.gross_weight_kg))  # F21

    # Line items starting row 27
    start_row = 27
    max_item_rows = 15
    for i, item in enumerate(data.items[:max_item_rows]):
        r = start_row + i
        if data.carton_range and i == 0:
            _safe_write(ws, r, 1, data.carton_range)
        _safe_write(ws, r, 2, item.description)
        if item.weight_kg is not None:
            _safe_write(ws, r, 6, item.weight_kg)
        if item.quantity is not None:
            _safe_write(ws, r, 7, item.quantity)
        if item.unit:
            _safe_write(ws, r, 8, item.unit)
        if item.amount is not None:
            _safe_write(ws, r, 9, item.amount)
        if item.unit_price is not None:
            _safe_write(ws, r, 11, item.unit_price)
            _safe_write(ws, r, 12, "$")

    if data.total_value is not None:
        tot_row = 50
        _safe_write(ws, tot_row, 8, "TOTAL VALUE:")
        _safe_write(ws, tot_row, 9, f"{data.total_value:.2f}")


def populate_template(template: Path, output: Path, data: FOCData):
    """
    Populate a customs invoice template with extracted FOC data.
    """
    selected = select_region(data)
    if template_region(template) not in (None, selected):
        raise ValueError('Template does not match the selected invoice region')
    wb = load_workbook(template)
    ws = wb.active

    if selected == "BD":
        _populate_bd(ws, data)
    elif selected == "INDIA":
        _populate_india(ws, data)
    elif selected == "JORDAN":
        _populate_jordan(ws, data)
    else:
        # Fallback to label search
        labels = {
            "DATE OF EXPORTATION": "export_date",
            "CUSTOMS INVOICE NO": "invoice_number",
            "COUNTRY OF ULTIMATE DESTINATION": "destination_country",
            "TOTAL VALUE": "total_value",
            "G.W": "gross_weight_kg",
            "GW": "gross_weight_kg",
            "TOTAL": "package_count",
        }
        for label, attr in labels.items():
            src = _find_label(ws, label)
            val = getattr(data, attr, None)
            if src and val is not None:
                target = _next_writable(ws, src)
                _safe_write(ws, target.row, target.column, val)

        desc = _find_label(ws, "DESCRIPTION  OF  GOODS") or _find_label(ws, "DESCRIPTION OF GOODS")
        qty = _find_label(ws, "QUANTITY")
        hs = _find_label(ws, "HS CODE")
        if desc and qty:
            start = max(desc.row, qty.row) + 1
            for i, item in enumerate(data.items[:10]):
                r = start + i
                _safe_write(ws, r, desc.column, item.description)
                _safe_write(ws, r, qty.column, item.quantity)
                if qty.column + 1 <= ws.max_column:
                    _safe_write(ws, r, qty.column + 1, item.unit)
                if hs and item.hs_code:
                    _safe_write(ws, r, hs.column, item.hs_code)

    # Add audit sheet for traceability and compliance
    audit = wb.create_sheet("Extraction_Audit")
    audit.append(["Field", "Extracted Value"])
    for k, v in data.to_dict().items():
        if k != "items" and not (selected == 'BD' and k == 'net_weight_kg'):
            audit.append([k, str(v) if v is not None else ""])

    if data.items:
        items_sheet = wb.create_sheet("Extracted_Items")
        items_sheet.append(["Index", "Description", "Quantity", "Unit", "Weight_KG", "HS_Code", "Unit_Price", "Amount", "Source_Page", "Confidence", "Source_Rows"])
        for idx, it in enumerate(data.items, 1):
            items_sheet.append([
                idx, it.description, it.quantity, it.unit,
                it.weight_kg, it.hs_code, it.unit_price, it.amount, it.source_page, it.confidence, '; '.join(it.source_refs),
            ])
            items_sheet.cell(idx + 1, 7).number_format = '0.00####'
            items_sheet.cell(idx + 1, 8).number_format = '0.00'
        items_sheet.column_dimensions['B'].width = 90
        items_sheet.freeze_panes = 'A2'
    audit.column_dimensions['A'].width = 25
    audit.column_dimensions['B'].width = 100
    audit.freeze_panes = 'A2'
    for sheet in wb.worksheets:
        if sheet is ws:
            continue
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=Path(output).parent, suffix='.xlsx', delete=False) as handle:
        temporary = Path(handle.name)
    try:
        wb.save(temporary)
        temporary.replace(output)
    finally:
        wb.close()
        temporary.unlink(missing_ok=True)
