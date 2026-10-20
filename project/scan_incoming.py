"""Continuously queue stable incoming PDFs; does not generate invoices yet."""
import argparse
import json
from pathlib import Path
import time

from src.foc_extractor.folder_intake import FolderScanner
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.pipeline_config import ROOT, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'pipeline_config.json')
    parser.add_argument('--once', action='store_true', help='Scan once, print status and exit')
    args = parser.parse_args()
    config = load_config(args.config)
    scanner = FolderScanner(config, JobStore(config.state_dir / 'jobs.sqlite3'))
    try:
        while True:
            print(json.dumps(scanner.scan_once()), flush=True)
            if args.once:
                return
            time.sleep(config.scan_interval_seconds)
    except KeyboardInterrupt:
        print(json.dumps({'scanner_stopped': True, 'extraction_started': False}), flush=True)


if __name__ == '__main__':
    main()
