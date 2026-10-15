import argparse
from pathlib import Path
from src.foc_extractor.pipeline import run

p = argparse.ArgumentParser(description="Extract FOC packing-list PDF data with Azure Document Intelligence and populate an Excel invoice template.")
p.add_argument("--pdf", required=True, type=Path)
p.add_argument("--template", type=Path)
p.add_argument("--output-dir", default=Path("output"), type=Path)
p.add_argument("--model-id", default=None)
p.add_argument('--backend', choices=['auto','easyocr','azure'], default='auto')
p.add_argument('--max-pages', type=int, default=None)
p.add_argument('--cache-dir', type=Path)
p.add_argument('--save-json', action='store_true')
a = p.parse_args()
print(run(a.pdf, a.template, a.output_dir, a.model_id, backend=a.backend,
          max_pages=a.max_pages, cache_dir=a.cache_dir, save_json=a.save_json))
