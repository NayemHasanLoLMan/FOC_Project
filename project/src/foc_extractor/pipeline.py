import json
import re
from pathlib import Path

from .ocr_engine import analyze_pdf
from .parser import parse_result
from .excel_writer import populate_template
from .valuation import apply_valuation
from .local_vision import DEFAULT_MODEL


def _resolve_template(template: Path | None, template_type: str | None) -> Path:
    """Resolve the template path. If none is passed, use the matching blank template."""
    if template:
        if not Path(template).is_file():
            raise FileNotFoundError(f'Template does not exist: {template}')
        return Path(template)

    base_dir = Path(__file__).resolve().parent.parent.parent / "templates"
    mapping = {
        "BD": base_dir / "BD_template.xlsx",
        "INDIA": base_dir / "INDIA_template.xlsx",
        "JORDAN": base_dir / "JORDAN_template.xlsx",
    }
    selected = mapping.get(template_type or "BD", mapping["BD"])
    if not selected.exists():
        # Fallback to templates in current working directory
        cwd_template = Path("templates") / f"{template_type or 'BD'}_template.xlsx"
        if cwd_template.exists():
            return cwd_template
        raise FileNotFoundError(f'Template does not exist: {selected}')
    return selected


def run(
    pdf: Path,
    template: Path | None = None,
    output_dir: Path | None = None,
    save_json: bool = False,
    max_pages: int | None = None,
    cache_dir: Path | None = None,
    local_model: str | None = DEFAULT_MODEL,
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
    active_template = _resolve_template(template, 'BD')
    out_dir = Path(output_dir) if output_dir else Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. OCR
    result = analyze_pdf(pdf_path,max_pages=max_pages,cache_dir=cache_dir)
    if local_model:
        from .local_vision import resolve_quantities
        resolve_quantities(result, pdf_path, local_model, cache_dir)

    # 2. Parse structured data
    data = parse_result(result, pdf_path)
    from .packages import packing_packages
    package_evidence=packing_packages(result,data.carton_range,pdf_path,cache_dir,local_model=local_model)
    data.package_count=package_evidence['total']
    data.warnings=[w for w in data.warnings if not w.startswith(('Package count basis:','Package extraction:'))
                   and not (data.package_count is not None and w.startswith('package_count not established'))]
    data.warnings.append(f'Package count basis: {package_evidence["basis"]}; selected count {data.package_count}.')
    if package_evidence['reason']:
        data.warnings.append('Package extraction: '+package_evidence['reason'])
    if data.gross_weight_kg is None and not re.search(r'\bGROSS\s+WEIGHT|\bG\.?\s*W\.?(?:\s*:|\s+\d)',result.content,re.I):
        from .weights import packing_weight
        weight = packing_weight(result, pdf_path, cache_dir,local_model=local_model)
        if weight['total_kg'] is not None:
            data.gross_weight_kg = weight['total_kg']
            data.warnings = [w for w in data.warnings if not w.startswith((
                'Packing-list weights are not established', 'gross_weight_kg not established'))]
            if any(c.get('method')=='local vision' for c in weight['cells']):
                data.warnings.append('Corrected weight cells transcribed by local vision; model and source coordinates retained in source-keyed cell evidence.')
            data.warnings.append('Gross weight supplied by corrected packing-list weight sum; shared cells counted once, no allowance or rounding.')
        elif weight['reason']:
            data.warnings.append('Packing-list weight sum unavailable: '+weight['reason'])

    if (data.net_weight_kg is not None and data.gross_weight_kg is not None
            and data.net_weight_kg > data.gross_weight_kg):
        data.net_weight_kg = None
        data.warnings.append('Declared net weight exceeds gross weight; net weight left empty.')

    apply_valuation(data)

    # 3. Resolve template and populate Excel
    if not template:
        active_template = _resolve_template(None, data.template_type)
    out_name = pdf_path.name.replace("-D.pdf", "-I.xlsx") if "-D.pdf" in pdf_path.name else f"{pdf_path.stem}.xlsx"
    xlsx_path = out_dir / out_name
    populate_template(active_template, xlsx_path, data)
    if save_json:
        json_path = out_dir / f"{pdf_path.stem}.json"
        temporary = json_path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(data.to_dict(), indent=2, ensure_ascii=False), encoding='utf-8')
        temporary.replace(json_path)

    return xlsx_path
