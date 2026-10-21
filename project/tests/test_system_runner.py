import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor import system_runner, queue_worker
from src.foc_extractor.excel_writer import populate_template
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.models import FOCData, LineItem
from src.foc_extractor.pipeline_config import load_config
from src.foc_extractor.process_lock import process_lock


class SystemRunnerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        settings = json.loads((ROOT/'pipeline_config.json').read_text())
        settings.update(scan_interval_seconds=0.03, local_model=None)
        path = self.root/'config.json'
        path.write_text(json.dumps(settings))
        self.config = load_config(path)
        self.stop = threading.Event()

    def start(self):
        self.errors = []
        def run():
            try:
                system_runner.run_system(self.config, port=0, stop=self.stop)
            except BaseException as error:
                self.errors.append(error)
        self.thread = threading.Thread(target=run)
        self.thread.start()
        self.addCleanup(self.finish)

    def finish(self):
        self.stop.set()
        self.thread.join(10)
        self.assertFalse(self.thread.is_alive(), 'System did not shut down')

    def wait_for(self, predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail('Timed out waiting for system state')

    def source(self, name='shipment.pdf'):
        self.config.incoming_dir.mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as document:
            document.new_page().insert_text((40,40), 'SHIPMENT')
            document.save(self.config.incoming_dir/name)

    def convert(self, source, *, template, output_dir, **kwargs):
        data = FOCData(source_file=source.name, pages_total=1, pages_processed=1,
                       items=[LineItem('FABRIC', 10, 'YDS')], total_value=2)
        path = output_dir/(source.stem+'.xlsx')
        populate_template(template, path, data)
        (output_dir/(source.stem+'.json')).write_text(json.dumps(data.to_dict()))
        return path

    def test_single_start_discovers_processes_and_stops_without_duplicate_jobs(self):
        self.source()
        with patch.object(queue_worker, 'run', side_effect=self.convert) as converter:
            self.start()
            store = JobStore(self.config.state_dir/'jobs.sqlite3')
            self.wait_for(lambda: store.counts()['completed']==1)
            time.sleep(0.1)
            self.finish()
        self.assertEqual(self.errors, [])
        self.assertEqual(converter.call_count, 1)
        self.assertEqual(len(list(self.config.output_dir.glob('*.xlsx'))),1)
        self.assertTrue(all(c['state']=='stopped' for c in store.components()))
        for name in ('scanner.lock','worker.lock'):
            with process_lock(self.config.state_dir/name):
                pass

    def test_shutdown_finishes_active_invoice_before_returning(self):
        self.source()
        entered = threading.Event()
        release = threading.Event()
        def convert(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError('Test conversion was not released')
            return self.convert(*args, **kwargs)
        with patch.object(queue_worker, 'run', side_effect=convert):
            self.start()
            try:
                self.assertTrue(entered.wait(10))
                self.stop.set()
                self.thread.join(0.1)
                self.assertTrue(self.thread.is_alive())
            finally:
                release.set()
                self.finish()
        self.assertEqual(self.errors, [])
        self.assertEqual(JobStore(self.config.state_dir/'jobs.sqlite3').counts()['completed'],1)

    def test_component_failure_stops_system_and_releases_locks(self):
        with patch.object(system_runner.FolderScanner,'scan_once',side_effect=OSError('scanner unavailable')):
            with self.assertRaisesRegex(RuntimeError,'scanner stopped: scanner unavailable'):
                system_runner.run_system(self.config,port=0,stop=self.stop)
        self.assertTrue(self.stop.is_set())
        for name in ('scanner.lock','worker.lock'):
            with process_lock(self.config.state_dir/name):
                pass

    def test_existing_worker_prevents_combined_start(self):
        with process_lock(self.config.state_dir/'worker.lock'):
            with self.assertRaisesRegex(RuntimeError,'Another process owns'):
                system_runner.run_system(self.config,port=0)
        with process_lock(self.config.state_dir/'scanner.lock'):
            pass

    def test_occupied_web_port_does_not_start_processing(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0))
            listener.listen()
            port = listener.getsockname()[1]
            with patch.object(system_runner,'QueueWorker') as worker:
                with self.assertRaises(OSError):
                    system_runner.run_system(self.config,port=port)
                worker.assert_not_called()


if __name__=='__main__':
    unittest.main()
