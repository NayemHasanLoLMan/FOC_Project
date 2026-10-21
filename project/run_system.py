"""Start PDF intake, invoice processing and the local dashboard with one command."""
import argparse
from pathlib import Path
import signal
import threading

from src.foc_extractor.pipeline_config import ROOT, load_config
from src.foc_extractor.system_runner import run_system


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'pipeline_config.json')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    config = load_config(args.config)
    stop = threading.Event()

    def request_stop(number, frame):
        if not stop.is_set():
            print('Stopping intake; waiting for the current invoice to finish...', flush=True)
        stop.set()

    stop_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, 'SIGBREAK'):
        stop_signals.append(signal.SIGBREAK)
    previous = {number: signal.signal(number, request_stop) for number in stop_signals}
    try:
        run_system(config, args.port, stop)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    main()
