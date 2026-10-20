"""Validate configuration and initialize durable state; does not start processing."""
import argparse
import json
from pathlib import Path

from src.foc_extractor.pipeline_config import ROOT, load_config
from src.foc_extractor.job_store import JobStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'pipeline_config.json')
    args = parser.parse_args()
    config = load_config(args.config)
    store = JobStore(config.state_dir / 'jobs.sqlite3')
    print(json.dumps({'configuration': config.to_dict(), 'database': str(store.path),
                      'jobs': store.counts(), 'processing_started': False}, indent=2))


if __name__ == '__main__':
    main()
