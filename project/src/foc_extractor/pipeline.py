import json
from pathlib import Path
from dotenv import load_dotenv

from .ocr_engine import analyze_pdf
from .parser import parse_result
from .excel_writer import populate_template


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
    model_id: str | None = None,
    backend: str = "auto",
    save_json: bool = False,
    max_pages: int | None = None,
    cache_dir: Path | None = None,
):
    """
    Execute end-to-end extraction pipeline:
      1. OCR extraction (Azure Document Intelligence or local EasyOCR)
      2. Structured data parsing & field validation
      3. Auto-select and populate customs Excel invoice template into output/
    """
    load_dotenv()
    pdf_path = Path(pdf)
    if not pdf_path.is_file():
        raise FileNotFoundError(f'PDF does not exist: {pdf_path}')
    if max_pages is not None and max_pages < 1:
        raise ValueError('max_pages must be a positive integer')
    active_template = _resolve_template(template, 'BD')
    out_dir = Path(output_dir) if output_dir else Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. OCR
    result = analyze_pdf(pdf_path, backend=backend, model_id=model_id, max_pages=max_pages, cache_dir=cache_dir)

    # 2. Parse structured data
    data = parse_result(result, pdf_path)

    # 4. Resolve template and populate Excel
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
