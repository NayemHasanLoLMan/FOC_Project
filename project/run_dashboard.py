"""Serve the local invoice dashboard on this PC."""
import argparse
from pathlib import Path

from waitress import serve

from src.foc_extractor.dashboard import create_app
from src.foc_extractor.pipeline_config import ROOT, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'pipeline_config.json')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    app = create_app(load_config(args.config))
    print(f'Local dashboard: http://127.0.0.1:{args.port} (Ctrl+C to stop)', flush=True)
    serve(app, host='127.0.0.1', port=args.port, threads=8, max_request_body_size=65536,
          clear_untrusted_proxy_headers=True)


if __name__ == '__main__':
    main()
