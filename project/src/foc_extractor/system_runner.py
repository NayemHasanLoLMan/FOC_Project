"""Run the existing scanner, extraction worker and local web server together."""
from contextlib import ExitStack
import json
import os
from queue import SimpleQueue
import threading
from uuid import uuid4

from waitress import create_server, wasyncore

from .dashboard import create_app
from .folder_intake import FolderScanner
from .job_store import JobStore
from .process_lock import process_lock
from .pipeline_config import initialize_folders
from .queue_worker import QueueWorker


def run_system(config, port=8080, stop=None):
    stop = stop if stop is not None else threading.Event()
    store = JobStore(config.state_dir / 'jobs.sqlite3')
    channels = {}
    server = None
    failures = SimpleQueue()
    threads = []
    try:
        server = create_server(create_app(config), host='127.0.0.1', port=port, map=channels,
                               threads=0, max_request_body_size=65536,
                               clear_untrusted_proxy_headers=True, asyncore_loop_timeout=0.2)
        # Avoid orphan HTTP threads when binding the port fails.
        server.task_dispatcher.set_thread_count(8)
        with ExitStack() as stack:
            stack.enter_context(process_lock(config.state_dir / 'scanner.lock'))
            worker = stack.enter_context(QueueWorker(config, store))
            initialize_folders(config)
            scanner = FolderScanner(config, store)
            owner = 'scanner:' + uuid4().hex

            def scan():
                failure = None
                try:
                    while not stop.is_set():
                        result = scanner.scan_once()
                        store.component('scanner', owner, os.getpid(),
                                        'degraded' if result['folder_error'] else 'running', result['folder_error'])
                        if stop.wait(config.scan_interval_seconds):
                            break
                except Exception as exc:
                    failure = str(exc)
                    raise
                finally:
                    store.component('scanner', owner, os.getpid(), 'failed' if failure else 'stopped', failure)

            def process():
                while not stop.is_set() and not worker.stop_requested.is_set():
                    attempt = worker.run_once()
                    if attempt is not None:
                        print(json.dumps({'attempt_id': attempt, 'jobs': store.counts()}), flush=True)
                    else:
                        stop.wait(config.scan_interval_seconds)
                worker._healthy()

            def serve():
                server.run()
                if not stop.is_set():
                    raise RuntimeError('The web server stopped unexpectedly')

            def supervise(name, action):
                try:
                    action()
                except BaseException as exc:
                    failures.put((name, exc))
                    stop.set()

            try:
                for name, action in [('scanner', scan), ('worker', process), ('web', serve)]:
                    thread = threading.Thread(target=supervise, args=(name, action), name='invoice-' + name)
                    thread.start()
                    threads.append(thread)
                print(f'Invoice system: http://127.0.0.1:{server.effective_port}', flush=True)
                print(f'PDF inbox: {config.incoming_dir}\nInvoice output: {config.output_dir}', flush=True)
                print('Ctrl+C stops intake and waits for the current invoice to finish.', flush=True)
                while not stop.wait(0.2):
                    if worker.stop_requested.is_set():
                        worker._healthy()
                        raise RuntimeError('The extraction worker stopped unexpectedly')
            except KeyboardInterrupt:
                stop.set()
            finally:
                stop.set()
                worker.stop_requested.set()
                for thread in threads:
                    if thread.name != 'invoice-web':
                        thread.join()
            if not failures.empty():
                name, error = failures.get()
                raise RuntimeError(f'{name} stopped: {error}') from error
    finally:
        stop.set()
        if server is not None:
            server.close()
            server.task_dispatcher.shutdown()
        wasyncore.close_all(map=channels)
        for thread in threads:
            if thread.name == 'invoice-web':
                thread.join()

