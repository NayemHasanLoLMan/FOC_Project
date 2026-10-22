"""Convert one PDF to an invoice using local OCR."""
import argparse
from pathlib import Path
from src.foc_extractor.pipeline import run
from src.foc_extractor.local_vision import DEFAULT_MODEL

ROOT=Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',required=True,type=Path)
    parser.add_argument('--template',type=Path)
    parser.add_argument('--region',choices=('BD','INDIA','JORDAN'),default='BD')
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--cache-dir',type=Path,default=ROOT/'.cache/ocr')
    parser.add_argument('--max-pages',type=int)
    parser.add_argument('--save-json',action='store_true')
    parser.add_argument('--local-model',default=DEFAULT_MODEL,help='Installed Ollama vision model for unresolved weight, package and quantity cells')
    parser.add_argument('--no-local-vision',dest='local_model',action='store_const',const=None,help='Use OCR only')
    args=parser.parse_args()
    from src.foc_extractor.regions import REGIONS
    print(run(args.pdf,template=args.template,output_dir=args.output_dir or ROOT/'output'/REGIONS[args.region]['folder'],region=args.region,
              cache_dir=args.cache_dir,max_pages=args.max_pages,
              save_json=args.save_json,local_model=args.local_model))


if __name__=='__main__':main()
