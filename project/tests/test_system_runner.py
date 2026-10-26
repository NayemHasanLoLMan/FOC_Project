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

    def test_transient_writer_lock_keeps_web_scanner_and_heartbeat_alive(self):
        from contextlib import closing
        import sqlite3
        import urllib.request
        servers=[];create=system_runner.create_server
        def capture(*args,**kwargs):
            server=create(*args,**kwargs);servers.append(server);return server
        with patch.object(system_runner,'create_server',side_effect=capture), \
             patch.object(queue_worker,'run',side_effect=self.convert), \
             patch.object(queue_worker,'HEARTBEAT_SECONDS',.03):
            self.start()
            store=JobStore(self.config.state_dir/'jobs.sqlite3')
            self.wait_for(lambda:servers and len(store.components())==2)
            with closing(sqlite3.connect(store.path)) as holder:
                holder.execute('BEGIN IMMEDIATE')
                base='http://127.0.0.1:'+str(servers[0].effective_port)
                with urllib.request.urlopen(base+'/api/status',timeout=3) as response:
                    self.assertEqual(response.status,200)
                time.sleep(6.5)
                self.assertTrue(self.thread.is_alive())
                self.assertFalse(self.stop.is_set())
            self.wait_for(lambda:all(c['state']=='running' for c in store.components()))
            self.source()
            self.wait_for(lambda:store.counts()['completed']==1)
            self.assertEqual(store.counts()['failed'],0)
            self.finish()
        self.assertEqual(self.errors,[])
        self.assertTrue(all(c['state']=='stopped' for c in store.components()))

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

    def test_shutdown_drains_http_workers_before_closing_their_trigger(self):
        from unittest.mock import MagicMock, call
        server = MagicMock()
        self.stop.set()
        with patch.object(system_runner,'create_server',return_value=server):
            system_runner.run_system(self.config,port=0,stop=self.stop)
        calls = server.mock_calls
        self.assertLess(calls.index(call.task_dispatcher.shutdown()),calls.index(call.close()))

    def test_main_coordinator_enables_clear_callback_without_development_mode(self):
        from unittest.mock import MagicMock
        from src.foc_extractor import development_reset
        self.stop.set()
        with patch.object(development_reset,'validate_workspace'), patch.object(development_reset,'clear_workspace') as clear, \
             patch.object(system_runner,'create_app',return_value=MagicMock()) as app, \
             patch.object(system_runner,'create_server',return_value=MagicMock()):
            system_runner.run_system(self.config,port=0,stop=self.stop)
            self.assertFalse(app.call_args.kwargs['development_mode'])
            app.call_args.kwargs['development_reset']('test-request')
            self.assertEqual(clear.call_args.args[0],self.config)
            self.assertEqual(clear.call_args.args[3],'test-request')
            self.assertFalse(clear.call_args.kwargs['development'])

    def test_saved_folders_apply_to_live_scanner_worker_and_survive_reload(self):
        import urllib.request
        import urllib.error
        from uuid import uuid4
        from src.foc_extractor.runtime_settings import editable_settings,load_runtime_settings
        self.root=self.root.resolve()
        servers=[];create=system_runner.create_server
        def capture(*args,**kwargs):
            server=create(*args,**kwargs);servers.append(server);return server
        with patch.object(system_runner,'create_server',side_effect=capture),patch.object(queue_worker,'run',side_effect=self.convert):
            self.start()
            self.wait_for(lambda:servers and len(JobStore(self.config.state_dir/'jobs.sqlite3').components())==2)
            base='http://127.0.0.1:'+str(servers[0].effective_port)
            with urllib.request.urlopen(base+'/api/controls') as response:token=json.load(response)['csrf_token']
            changes={**editable_settings(self.config),'incoming_dir':str(self.root/'new-incoming'),'output_dir':str(self.root/'new-output'),
                     'vision_output_tokens':1024,'vision_context_tokens':2048,'vision_timeout_seconds':99}
            payload=json.dumps({'request_id':str(uuid4()),'changes':changes}).encode()
            def save():
                request=urllib.request.Request(base+'/api/settings',data=payload,headers={'Origin':base,'X-CSRF-Token':token,'Content-Type':'application/json'})
                try:
                    with urllib.request.urlopen(request) as response:return response.status==200
                except urllib.error.HTTPError as error:
                    if error.code!=409:raise
                    return False
            self.wait_for(save)
            with urllib.request.urlopen(base+'/api/system') as response:self.assertEqual(json.load(response)['settings'],changes)
            source=Path(changes['incoming_dir'])/'new.pdf'
            with pymupdf.open() as document:
                document.new_page().insert_text((40,40),'NEW INBOX');document.save(source)
            store=JobStore(self.config.state_dir/'jobs.sqlite3')
            self.wait_for(lambda:store.counts()['completed']==1)
            self.assertEqual(len(list(Path(changes['output_dir']).glob('*.xlsx'))),1)
            self.assertFalse(self.config.output_dir.exists() and list(self.config.output_dir.glob('*.xlsx')))
            self.finish()
        self.assertEqual(self.errors,[])
        self.assertEqual(editable_settings(load_runtime_settings(self.config)),changes)


if __name__=='__main__':
    unittest.main()
