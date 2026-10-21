"""Start PDF intake, invoice processing and the local dashboard with one command."""
import argparse
import json
from pathlib import Path
import signal
import threading

from src.foc_extractor.pipeline_config import ROOT, load_config
from src.foc_extractor.system_runner import run_system


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'pipeline_config.json')
    parser.add_argument('--port', type=int, default=8080)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--startup', choices=['install','start','stop','status','uninstall'],
                      help='Manage the current-user Windows sign-in task')
    mode.add_argument('--background', action='store_true', help='Run hidden with rotated logs and graceful stop control')
    mode.add_argument('--development', action='store_true', help='Use an isolated test workspace with recoverable Clear data tools')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    config = load_config(args.config)
    if args.development:
        if args.config.resolve() != (ROOT/'pipeline_config.json').resolve():
            parser.error('--development uses its own isolated workspace; do not pass --config')
        from src.foc_extractor.development_reset import development_config
        config = development_config(config)
    if args.startup:
        from src.foc_extractor.windows_startup import manage_startup
        print(json.dumps(manage_startup(args.startup,config,args.config,args.port),indent=2))
        return
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
        if args.background:
            from src.foc_extractor.windows_startup import background_runtime
            with background_runtime(config,stop):
                run_system(config,args.port,stop)
        else:
            run_system(config, args.port, stop, development=args.development)
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


if __name__ == '__main__':
    main()
