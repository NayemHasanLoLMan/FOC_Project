"""Continuously queue stable incoming PDFs for the separate extraction worker."""
import argparse
import json
import os
from pathlib import Path
import time
from uuid import uuid4

from src.foc_extractor.folder_intake import FolderScanner
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.pipeline_config import ROOT, load_config
from src.foc_extractor.process_lock import process_lock


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'pipeline_config.json')
    parser.add_argument('--once', action='store_true', help='Scan once, print status and exit')
    args = parser.parse_args()
    config = load_config(args.config)
    store = JobStore(config.state_dir / 'jobs.sqlite3')
    scanner = FolderScanner(config, store)
    owner = 'scanner:' + uuid4().hex
    with process_lock(store.path.parent / 'scanner.lock'):
        failure = None
        try:
            while True:
                result = scanner.scan_once()
                store.component('scanner', owner, os.getpid(), 'degraded' if result['folder_error'] else 'running', result['folder_error'])
                print(json.dumps(result), flush=True)
                if args.once:
                    return
                time.sleep(config.scan_interval_seconds)
        except KeyboardInterrupt:
            print(json.dumps({'scanner_stopped': True, 'extraction_started': False}), flush=True)
        except Exception as exc:
            failure = str(exc)
            raise
        finally:
            store.component('scanner', owner, os.getpid(), 'failed' if failure else 'stopped', failure)


if __name__ == '__main__':
    main()
