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
from tempfile import NamedTemporaryFile
from openpyxl import load_workbook
from .models import FOCData


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


def _next_writable(ws, cell, max_steps=8):
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
    for coordinate in ('C9', 'H11', 'H12', 'I13', 'B11', 'E21', 'C25', 'B27', 'G27', 'A29', 'G40'):
        ws[coordinate] = None
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
        _safe_write(ws, 13, 9, data.carton_range)  # I13

    if data.consignee:
        _safe_write(ws, 11, 2, data.consignee)  # B11
    addr_lines = _split_address_lines(data.consignee_address)
    if len(addr_lines) > 6:
        addr_lines = addr_lines[:5] + ['\n'.join(addr_lines[5:])]
    for i, line in enumerate(addr_lines):
        _safe_write(ws, 12 + i, 2, line)
        alignment = copy(ws.cell(12 + i, 2).alignment)
        alignment.wrap_text = True
        ws.cell(12 + i, 2).alignment = alignment
        ws.row_dimensions[12 + i].height = max(ws.row_dimensions[12 + i].height or 15,
                                              15 * sum(max(1, math.ceil(len(s) / 55)) for s in line.splitlines()))

    if data.destination_country:
        _safe_write(ws, 21, 5, data.destination_country.upper())  # E21
    if data.invoice_number:
        _safe_write(ws, 25, 3, data.invoice_number)  # C25
    if data.package_count is not None:
        _safe_write(ws, 27, 2, int(data.package_count))  # B27
    if data.gross_weight_kg is not None:
        _safe_write(ws, 27, 7, float(data.gross_weight_kg))  # G27

    # Preserve the BD design, growing its detail area before totals/footer.
    start_row = 33
    extra = max(0, len(data.items) - 6)
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
        ws.row_dimensions[r].height = max(24, 15 * math.ceil(len(item.description) / 65))
        if i == 0:
            if data.carton_range:
                _safe_write(ws, r, 1, data.carton_range)
            elif data.package_count:
                _safe_write(ws, r, 1, f"{int(data.package_count)} PKGS")
        _safe_write(ws, r, 2, item.description)
        if item.quantity is not None:
            _safe_write(ws, r, 7, item.quantity)
        if item.unit:
            _safe_write(ws, r, 8, item.unit)

    tot_row = 40 + extra
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
    ws.print_area = f'A1:I{43+extra}'
    ws.print_title_rows = '1:30'
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_margins.bottom = max(.75, ws.page_margins.bottom)
    ws.page_margins.footer = .3


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
    wb = load_workbook(template)
    ws = wb.active

    tname = Path(template).name.upper()
    ttype = (data.template_type or "").upper()

    selected = next((region for region in ('BD','INDIA','JORDAN') if region in tname), ttype)
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
        if k != "items":
            audit.append([k, str(v) if v is not None else ""])

    if data.items:
        items_sheet = wb.create_sheet("Extracted_Items")
        items_sheet.append(["Index", "Description", "Quantity", "Unit", "Weight_KG", "HS_Code", "Unit_Price", "Amount", "Source_Page", "Confidence", "Source_Rows"])
        for idx, it in enumerate(data.items, 1):
            items_sheet.append([
                idx, it.description, it.quantity, it.unit,
                it.weight_kg, it.hs_code, it.unit_price, it.amount, it.source_page, it.confidence, '; '.join(it.source_refs),
            ])
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
