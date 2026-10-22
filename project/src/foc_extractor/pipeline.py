from dataclasses import asdict
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from .processing_evidence import emit, observed, track, accepted_vision_refs
from .ocr_engine import analyze_pdf
from .parser import parse_result
from .excel_writer import populate_template
from .valuation import apply_valuation
from .local_vision import DEFAULT_MODEL
from .regions import REGIONS, region_code, select_region, template_region


def _check_output_directory(output):
    target = Path(output).resolve()
    root = Path(__file__).resolve().parents[2]
    for name in ('expected_output', 'expected_outputs'):
        reference = root / name
        if target == reference or target.is_relative_to(reference) or reference.is_relative_to(target):
            raise ValueError('Output must not overlap manual reference folders')


def _resolve_template(template: Path | None, template_type: str | None) -> Path:
    """Resolve the template path. If none is passed, use the matching blank template."""
    selected_region = region_code(template_type or 'BD')
    if template:
        if template_region(template) not in (None, selected_region):
            raise ValueError('Template does not match the selected invoice region')
        if not Path(template).is_file():
            raise FileNotFoundError(f'Template does not exist: {template}')
        return Path(template)

    base_dir = Path(__file__).resolve().parent.parent.parent / "templates"
    mapping = {
        "BD": base_dir / "BD_template.xlsx",
        "INDIA": base_dir / "INDIA_template.xlsx",
        "JORDAN": base_dir / "JORDAN_template.xlsx",
    }
    selected = mapping[selected_region]
    if not selected.exists():
        # Fallback to templates in current working directory
        cwd_template = Path("templates") / f"{template_type or 'BD'}_template.xlsx"
        if cwd_template.exists():
            return cwd_template
        raise FileNotFoundError(f'Template does not exist: {selected}')
    return selected


@observed
def run(
    pdf: Path,
    template: Path | None = None,
    output_dir: Path | None = None,
    save_json: bool = False,
    max_pages: int | None = None,
    cache_dir: Path | None = None,
    local_model: str | None = DEFAULT_MODEL,
    observer=None,
    region: str | None = None,
):
    """
    Execute end-to-end extraction pipeline:
      1. Local OCR extraction (PaddleOCR by default)
      2. Structured data parsing & field validation
      3. Auto-select and populate customs Excel invoice template into output/
    """
    pdf_path = Path(pdf)
    if not pdf_path.is_file():
        raise FileNotFoundError(f'PDF does not exist: {pdf_path}')
    if max_pages is not None and max_pages < 1:
        raise ValueError('max_pages must be a positive integer')
    if region is not None:
        region_code(region)
    initial_region = region or (template_region(template) if template else None) or 'BD'
    active_template = _resolve_template(template, initial_region)
    out_dir = Path(output_dir) if output_dir else Path('output') / REGIONS[initial_region]['folder']
    _check_output_directory(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. OCR
    result = track('ocr', analyze_pdf, pdf_path,max_pages=max_pages,cache_dir=cache_dir)
    emit('ocr_document', document=asdict(result))
    if local_model:
        from .local_vision import resolve_quantities
        track('goods_vision', resolve_quantities, result, pdf_path, local_model, cache_dir)

    # 2. Parse structured data
    data = track('parse', parse_result, result, pdf_path)
    selected = select_region(data, region or (template_region(template) if template else None),
                             (result.pages or [result.content])[0])
    active_template = _resolve_template(template, selected)
    if output_dir is None:
        out_dir = Path('output') / REGIONS[selected]['folder']
        out_dir.mkdir(parents=True, exist_ok=True)
    emit('field_source', field='template_type', method='selected_invoice_region', value=selected,
         template=str(active_template))
    from .packages import packing_packages
    package_evidence=track('packages', packing_packages, result,data.carton_range,pdf_path,cache_dir,local_model=local_model)
    emit('field_evidence', field='package_count', evidence=package_evidence)
    data.package_count=package_evidence['total']
    data.warnings=[w for w in data.warnings if not w.startswith(('Package count basis:','Package extraction:'))
                   and not (data.package_count is not None and w.startswith('package_count not established'))]
    data.warnings.append(f'Package count basis: {package_evidence["basis"]}; selected count {data.package_count}.')
    if package_evidence['reason']:
        data.warnings.append('Package extraction: '+package_evidence['reason'])
    if data.gross_weight_kg is None and not re.search(r'\bGROSS\s+WEIGHT|\bG\.?\s*W\.?(?:\s*:|\s+\d)',result.content,re.I):
        from .weights import packing_weight
        weight = track('weights', packing_weight, result, pdf_path, cache_dir,local_model=local_model)
        emit('field_evidence', field='gross_weight_kg', evidence=weight)
        if weight['total_kg'] is not None:
            data.gross_weight_kg = weight['total_kg']
            emit('field_source', field='gross_weight_kg', method='corrected_packing_weight_sum', value=data.gross_weight_kg)
            data.warnings = [w for w in data.warnings if not w.startswith((
                'Packing-list weights are not established', 'gross_weight_kg not established'))]
            if any(c.get('method')=='local vision' for c in weight['cells']):
                data.warnings.append('Corrected weight cells transcribed by local vision; model and source coordinates retained in source-keyed cell evidence.')
            data.warnings.append('Gross weight supplied by corrected packing-list weight sum; shared cells counted once, no allowance or rounding.')
        elif weight['reason']:
            data.warnings.append('Packing-list weight sum unavailable: '+weight['reason'])

    if (data.net_weight_kg is not None and data.gross_weight_kg is not None
            and data.net_weight_kg > data.gross_weight_kg):
        emit('field_decision', field='net_weight_kg', candidate=data.net_weight_kg, accepted=False,
             reason='Declared net weight exceeds gross weight', gross_weight_kg=data.gross_weight_kg)
        data.net_weight_kg = None
        data.warnings.append('Declared net weight exceeds gross weight; net weight left empty.')

    track('valuation', apply_valuation, data)
    contributions=[]
    refs={ref for item in data.items for ref in item.source_refs}
    contributions.extend({'field':'goods_quantity','source_ref':ref} for ref in sorted(accepted_vision_refs() & refs))
    if data.package_count is not None and any('local vision' in e.get('method','') for e in package_evidence['entries']):
        contributions.append({'field':'package_count'})
    if data.gross_weight_kg is not None and 'weight' in locals() and weight['total_kg'] is not None and any(c.get('method')=='local vision' for c in weight['cells']):
        contributions.append({'field':'gross_weight_kg'})
    unresolved=[field for field in ('invoice_number','export_date','consignee','consignee_address','shipping_marks',
                'package_count','gross_weight_kg','total_value') if getattr(data,field) is None]
    unresolved.extend(f'goods:{i+1}:{field}' for i,item in enumerate(data.items)
                      for field in ('description','quantity','unit','unit_price') if getattr(item,field) in (None,''))
    if not data.items:unresolved.append('goods')
    emit('invoice_evidence', vision_contributions=contributions, unresolved_fields=unresolved,
         goods=[asdict(item) for item in data.items], diagnostics=data.warnings)

    # 3. Resolve template and populate Excel
    out_name = pdf_path.name.replace("-D.pdf", "-I.xlsx") if "-D.pdf" in pdf_path.name else f"{pdf_path.stem}.xlsx"
    xlsx_path = out_dir / out_name
    if selected == 'BD':
        track('workbook', populate_template, active_template, xlsx_path, data)
    else:
        from .workbook_verification import verify_workbook
        with TemporaryDirectory(dir=out_dir) as staging:
            prepared = Path(staging) / out_name
            track('workbook', populate_template, active_template, prepared, data)
            verify_workbook(prepared, data.to_dict(), pdf_path, selected)
            prepared.replace(xlsx_path)
    if save_json:
        json_path = out_dir / f"{pdf_path.stem}.json"
        temporary = json_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(data.to_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
        temporary.replace(json_path)

    return xlsx_path
