"""Run PDFs independently of the manual expected workbooks."""
import argparse
import json
from pathlib import Path
from src.foc_extractor.pipeline import run

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend',choices=['auto','easyocr','azure'],default='auto')
    parser.add_argument('--input-dir',type=Path,default=ROOT/'examples')
    parser.add_argument('--output-dir',type=Path,default=ROOT/'output')
    parser.add_argument('--max-pages',type=int,default=None)
    parser.add_argument('--cache-dir',type=Path,default=ROOT/'.cache/ocr')
    args=parser.parse_args()
    files=sorted(args.input_dir.glob('*.pdf'))
    if not files:raise SystemExit(f'No PDFs in {args.input_dir}')
    results=[{'source':pdf.name,'status':'pending'} for pdf in files]
    args.output_dir.mkdir(parents=True,exist_ok=True)
    manifest=args.output_dir/'run_manifest.json'
    manifest.write_text(json.dumps(results,indent=2),encoding='utf-8')
    for index,pdf in enumerate(files,1):
        print(f'[{index}/{len(files)}] {pdf.name}',flush=True)
        try:
            output=run(pdf,template=ROOT/'templates/BD_template.xlsx',output_dir=args.output_dir,
                       backend=args.backend,max_pages=args.max_pages,cache_dir=args.cache_dir)
            results[index-1]={'source':pdf.name,'output':str(output),'status':'written'}
            print(f'Written {output.name}',flush=True)
        except Exception as exc:
            results[index-1]={'source':pdf.name,'status':'failed','error':str(exc)}
            print(f'FAILED: {exc}',flush=True)
        manifest.write_text(json.dumps(results,indent=2),encoding='utf-8')
    if any(r['status']=='failed' for r in results):raise SystemExit(1)


if __name__=='__main__':main()
