"""Process queued PDF snapshots through the existing converter."""
import argparse
import json
from pathlib import Path
import signal

from src.foc_extractor.job_store import JobStore
from src.foc_extractor.pipeline_config import ROOT, load_config
from src.foc_extractor.queue_worker import QueueWorker


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'pipeline_config.json')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--once', action='store_true', help='Process at most one new job and retry waiting outputs')
    modes.add_argument('--drain', action='store_true', help='Process the queued backlog and exit; do not wait for new arrivals')
    args = parser.parse_args()
    config = load_config(args.config)
    store = JobStore(config.state_dir / 'jobs.sqlite3')
    with QueueWorker(config, store) as worker:
        previous = signal.signal(signal.SIGINT, lambda number, frame: worker.stop_requested.set())
        try:
            while not worker.stop_requested.is_set():
                attempt_id = worker.run_once()
                print(json.dumps({'attempt_id': attempt_id, 'jobs': store.counts()}), flush=True)
                if args.once or args.drain and attempt_id is None:
                    break
                if attempt_id is None:
                    worker.stop_requested.wait(config.scan_interval_seconds)
            worker._healthy()
        finally:
            signal.signal(signal.SIGINT, previous)
    counts = store.counts()
    if (args.once or args.drain) and any(counts[state] for state in ('failed', 'interrupted', 'waiting_to_save')):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
