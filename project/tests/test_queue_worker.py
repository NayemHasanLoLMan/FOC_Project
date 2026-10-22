from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor import queue_worker
from src.foc_extractor.excel_writer import populate_template
from src.foc_extractor.job_store import APPLICATION_ID, INTAKE_SCHEMA, SCHEMA, SCHEMA_VERSION, JobStore
from src.foc_extractor.models import FOCData, LineItem
from src.foc_extractor.pipeline_config import load_config
from src.foc_extractor.queue_worker import QueueWorker


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.config_path = self.root / 'pipeline_config.json'
        settings = json.loads((ROOT / 'pipeline_config.json').read_text())
        settings['local_model'] = None
        self.config_path.write_text(json.dumps(settings))
        self.config = load_config(self.config_path)
        self.store = JobStore(self.config.state_dir / 'jobs.sqlite3')

    def enqueue(self, name='shipment.pdf', text='FIRST'):
        original = self.config.incoming_dir / name
        snapshot = self.config.artifact_dir / 'inputs' / text / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as document:
            document.new_page().insert_text((40, 40), text)
            document.save(snapshot)
        return self.store.enqueue(original, hashlib.sha256(snapshot.read_bytes()).hexdigest(), snapshot)

    def convert(self, source, *, template, output_dir, save_json, cache_dir, local_model, observer=None, region='BD'):
        self.assertEqual(region, 'BD')
        self.assertEqual(template, ROOT / 'templates/BD_template.xlsx')
        self.assertEqual(cache_dir, ROOT / '.cache/ocr')
        self.assertTrue(save_json)
        self.assertIsNone(local_model)
        data = FOCData(source_file=source.name, ocr_backend='paddle', pages_total=1, pages_processed=1,
                       invoice_number='S/NEW/27', destination_country='Bangladesh', gross_weight_kg=3,
                       total_value=2, items=[LineItem('NEW FABRIC', 10, 'YDS')], warnings=['Source diagnostic'])
        path = output_dir / (source.stem + '.xlsx')
        populate_template(template, path, data)
        (output_dir / (source.stem + '.json')).write_text(json.dumps(data.to_dict()))
        return path

    def test_existing_converter_is_used_and_verified_workbook_is_published(self):
        job = self.enqueue()
        with patch.object(queue_worker, 'run', side_effect=self.convert) as convert, QueueWorker(self.config, self.store) as worker:
            attempt_id = worker.run_once()
        attempt = self.store.get_attempt(attempt_id)
        self.assertEqual(self.store.get_job(job)['state'], 'completed')
        self.assertEqual(attempt['state'], 'completed')
        self.assertEqual(convert.call_count, 1)
        self.assertEqual(Path(attempt['output_path']).name, 'shipment.xlsx')
        receipt = json.loads(Path(attempt['receipt_path']).read_text())
        self.assertEqual(hashlib.sha256(Path(attempt['output_path']).read_bytes()).hexdigest(), receipt['workbook_sha256'])
        self.assertEqual(self.store.components()[0]['state'], 'stopped')
        book = queue_worker.load_workbook(attempt['output_path'])
        self.assertEqual(book.active['G27'].font.color.rgb[-6:], 'FF0000')
        self.assertEqual(book.active['G33'].alignment.horizontal, 'right')
        book.close()

    def test_changed_input_is_rejected_before_converter_runs(self):
        job = self.enqueue()
        Path(self.store.get_job(job)['snapshot_path']).write_bytes(b'tampered source')
        with patch.object(queue_worker, 'run') as convert, QueueWorker(self.config, self.store) as worker:
            worker.run_once()
        convert.assert_not_called()
        self.assertEqual(self.store.get_job(job)['state'], 'failed')

    def test_prepared_restart_retains_evidence_and_issues_without_conversion(self):
        job = self.enqueue()
        def convert(source, **kwargs):
            kwargs['observer']({'kind':'invoice_evidence','vision_contributions':[],
                                'unresolved_fields':['net_weight_kg']})
            return self.convert(source, **kwargs)
        with patch.object(queue_worker, 'run', side_effect=convert), QueueWorker(self.config, self.store) as worker:
            with patch.object(queue_worker, '_publish_copy', side_effect=PermissionError('locked')):
                attempt_id = worker.run_once()
        with patch.object(queue_worker, 'run') as converter, QueueWorker(self.config, self.store) as worker:
            worker.run_once()
        converter.assert_not_called()
        attempt = self.store.get_attempt(attempt_id)
        self.assertEqual(attempt['state'], 'completed')
        self.assertEqual(attempt['issues'], ['missing:net_weight_kg'])
        self.assertEqual(attempt['metadata']['processing']['vision_contributions'], [])
        self.assertEqual(len([e for e in self.store.events(job) if e['kind']=='processing']), 1)

    def test_bad_job_does_not_stop_the_next_pdf(self):
        first = self.enqueue('bad.pdf')
        second = self.enqueue('good.pdf', 'SECOND')
        def convert(source, **kwargs):
            if source.name == 'bad.pdf':
                raise RuntimeError('Conversion failed')
            return self.convert(source, **kwargs)
        with patch.object(queue_worker, 'run', side_effect=convert), QueueWorker(self.config, self.store) as worker:
            worker.run_once()
            worker.run_once()
        self.assertEqual(self.store.get_job(first)['state'], 'failed')
        self.assertEqual(self.store.get_job(second)['state'], 'completed')

    def test_existing_files_and_new_versions_are_never_overwritten(self):
        self.config.output_dir.mkdir(parents=True)
        original = self.config.output_dir / 'shipment.xlsx'
        original.write_bytes(b'user-owned invoice')
        first = self.enqueue()
        second = self.enqueue(text='SECOND')
        with patch.object(queue_worker, 'run', side_effect=self.convert), QueueWorker(self.config, self.store) as worker:
            worker.run_once()
            worker.run_once()
        outputs = [self.store.attempts(job)[0]['output_path'] for job in (first, second)]
        self.assertEqual(original.read_bytes(), b'user-owned invoice')
        self.assertNotEqual(outputs[0], outputs[1])
        self.assertEqual(len(list(self.config.output_dir.glob('*.xlsx'))), 3)

    def test_locked_publication_retries_without_new_conversion_or_attempt(self):
        job = self.enqueue()
        with patch.object(queue_worker, 'run', side_effect=self.convert) as convert, QueueWorker(self.config, self.store) as worker:
            with patch.object(queue_worker, '_publish_copy', side_effect=PermissionError('Excel/output lock')):
                worker.run_once()
            self.assertEqual(self.store.get_job(job)['state'], 'waiting_to_save')
            self.assertIsNone(worker.run_once())
        self.assertEqual(self.store.get_job(job)['state'], 'completed')
        self.assertEqual(convert.call_count, 1)
        self.assertEqual(len(self.store.attempts(job)), 1)

    def test_inaccessible_output_folder_keeps_a_prepared_workbook(self):
        job = self.enqueue()
        self.config.output_dir.parent.mkdir(parents=True,exist_ok=True)
        self.config.output_dir.write_bytes(b'blocking file')
        with patch.object(queue_worker, 'run', side_effect=self.convert) as convert, QueueWorker(self.config, self.store) as worker:
            worker.run_once()
            self.assertEqual(self.store.get_job(job)['state'], 'waiting_to_save')
            self.config.output_dir.unlink()
            worker.run_once()
        self.assertEqual(convert.call_count, 1)
        self.assertEqual(self.store.get_job(job)['state'], 'completed')

    def test_restart_adopts_prepared_output_without_ocr(self):
        job = self.enqueue()
        with patch.object(queue_worker, 'run', side_effect=self.convert), QueueWorker(self.config, self.store) as worker:
            with patch.object(queue_worker, '_publish_copy', side_effect=PermissionError('locked')):
                worker.run_once()
        with patch.object(queue_worker, 'run') as convert, QueueWorker(self.config, self.store) as worker:
            worker.run_once()
        convert.assert_not_called()
        self.assertEqual(self.store.get_job(job)['state'], 'completed')
        self.assertEqual(len(self.store.attempts(job)), 1)
        self.assertIn('recovered_prepared', [event['kind'] for event in self.store.events(job)])

    def test_crash_after_ready_receipt_before_db_prepare_reuses_output(self):
        job = self.enqueue()
        with self.assertRaises(sqlite3.OperationalError):
            with patch.object(queue_worker, 'run', side_effect=self.convert), QueueWorker(self.config, self.store) as worker:
                with patch.object(self.store, 'prepare', side_effect=sqlite3.OperationalError('simulated crash')):
                    worker.run_once()
        with patch.object(queue_worker, 'run') as convert, QueueWorker(self.config, self.store) as worker:
            worker.run_once()
        convert.assert_not_called()
        self.assertEqual(self.store.get_job(job)['state'], 'completed')
        self.assertEqual(len(self.store.attempts(job)), 1)

    def test_crash_after_publication_reconciles_one_output_without_ocr(self):
        job = self.enqueue()
        with self.assertRaises(sqlite3.OperationalError):
            with patch.object(queue_worker, 'run', side_effect=self.convert), QueueWorker(self.config, self.store) as worker:
                with patch.object(self.store, 'finish', side_effect=sqlite3.OperationalError('simulated DB failure')):
                    worker.run_once()
        self.assertEqual(len(list(self.config.output_dir.glob('*.xlsx'))), 1)
        with patch.object(queue_worker, 'run') as convert, QueueWorker(self.config, self.store) as worker:
            worker.run_once()
        convert.assert_not_called()
        self.assertEqual(self.store.get_job(job)['state'], 'completed')
        self.assertEqual(len(list(self.config.output_dir.glob('*.xlsx'))), 1)

    def test_foreign_file_racing_publication_gets_a_new_destination(self):
        job = self.enqueue()
        publish = queue_worker._publish_copy
        raced = False
        def race(source, target, digest):
            nonlocal raced
            if not raced:
                raced = True
                target.write_bytes(b'external invoice')
            publish(source, target, digest)
        with patch.object(queue_worker, 'run', side_effect=self.convert), patch.object(queue_worker, '_publish_copy', side_effect=race):
            with QueueWorker(self.config, self.store) as worker:
                worker.run_once()
        self.assertEqual((self.config.output_dir / 'shipment.xlsx').read_bytes(), b'external invoice')
        self.assertEqual(self.store.get_job(job)['state'], 'completed')
        self.assertEqual(len(list(self.config.output_dir.glob('*.xlsx'))), 2)

    def test_corrupted_publication_copy_is_not_made_visible(self):
        job = self.enqueue()
        copy = queue_worker.shutil.copyfile
        def corrupt(source, target):
            copy(source, target)
            Path(target).write_bytes(b'corrupt copy')
        with patch.object(queue_worker, 'run', side_effect=self.convert), QueueWorker(self.config, self.store) as worker:
            with patch.object(queue_worker.shutil, 'copyfile', side_effect=corrupt):
                worker.run_once()
        self.assertEqual(self.store.get_job(job)['state'], 'failed')
        self.assertEqual(list(self.config.output_dir.glob('*.xlsx')), [])
        self.assertEqual(list(self.config.output_dir.glob('*.tmp')), [])

    def test_corrupted_prepared_workbook_is_not_published(self):
        job = self.enqueue()
        with patch.object(queue_worker, 'run', side_effect=self.convert), QueueWorker(self.config, self.store) as worker:
            with patch.object(queue_worker, '_publish_copy', side_effect=PermissionError('locked')):
                attempt_id = worker.run_once()
            receipt = Path(self.store.get_attempt(attempt_id)['receipt_path'])
            prepared = receipt.parent / json.loads(receipt.read_text())['workbook_name']
            prepared.write_bytes(b'corrupt staged workbook')
            worker.run_once()
        self.assertEqual(self.store.get_job(job)['state'], 'failed')
        self.assertEqual(list(self.config.output_dir.glob('*.xlsx')), [])

    def test_native_lock_blocks_another_worker_even_if_heartbeat_looks_old(self):
        self.enqueue()
        with QueueWorker(self.config, self.store):
            code = ('import sys;sys.path.insert(0,sys.argv[1]);from src.foc_extractor.pipeline_config import load_config;'
                    'from src.foc_extractor.job_store import JobStore;from src.foc_extractor.queue_worker import QueueWorker;'
                    "c=load_config(sys.argv[2]);w=QueueWorker(c,JobStore(c.state_dir/'jobs.sqlite3'));w.__enter__()")
            result = subprocess.run([sys.executable, '-c', code, str(ROOT), str(self.config_path)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Another process owns worker.lock', result.stderr)
        self.assertEqual(self.store.counts()['queued'], 1)

    def test_os_releases_lock_after_a_real_child_process_exits_abruptly(self):
        job = self.enqueue()
        code = ('import os,sys;sys.path.insert(0,sys.argv[1]);from src.foc_extractor.pipeline_config import load_config;'
                'from src.foc_extractor.job_store import JobStore;from src.foc_extractor import queue_worker;'
                'queue_worker.run=lambda *a,**k:os._exit(7);c=load_config(sys.argv[2]);'
                "w=queue_worker.QueueWorker(c,JobStore(c.state_dir/'jobs.sqlite3'));w.__enter__();w.run_once()")
        result = subprocess.run([sys.executable, '-c', code, str(ROOT), str(self.config_path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 7)
        self.assertEqual(self.store.get_job(job)['state'], 'running')
        with patch.object(queue_worker, 'run', side_effect=self.convert), QueueWorker(self.config, self.store) as worker:
            worker.run_once()
        self.assertEqual([a['state'] for a in self.store.attempts(job)], ['interrupted', 'completed'])

    def test_repeated_unprepared_crashes_are_bounded(self):
        job = self.enqueue()
        for _ in range(3):
            with self.assertRaises(KeyboardInterrupt):
                with patch.object(queue_worker, 'run', side_effect=KeyboardInterrupt), QueueWorker(self.config, self.store) as worker:
                    worker.run_once()
        with patch.object(queue_worker, 'run') as convert, QueueWorker(self.config, self.store) as worker:
            worker.run_once()
        convert.assert_not_called()
        self.assertEqual(self.store.get_job(job)['state'], 'failed')
        self.assertEqual(len(self.store.attempts(job)), 3)

    def test_unmanaged_attempt_is_not_stolen(self):
        job = self.enqueue()
        self.store.claim_next('manual-owner', {})
        with self.assertRaisesRegex(RuntimeError, 'refusing automatic takeover'):
            with QueueWorker(self.config, self.store):
                pass
        self.assertEqual(self.store.get_job(job)['state'], 'running')

    def test_heartbeat_progresses_during_slow_conversion(self):
        self.enqueue()
        def slow(source, **kwargs):
            before = self.store.components()[0]['heartbeat_at']
            deadline = time.monotonic() + 2
            while self.store.components()[0]['heartbeat_at'] == before and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertNotEqual(self.store.components()[0]['heartbeat_at'], before)
            return self.convert(source, **kwargs)
        with patch.object(queue_worker, 'HEARTBEAT_SECONDS', .01), patch.object(queue_worker, 'run', side_effect=slow):
            with QueueWorker(self.config, self.store) as worker:
                worker.run_once()

    def test_version_two_migration_preserves_original_attempt_fields(self):
        path = self.root / 'legacy.sqlite3'
        with closing(sqlite3.connect(path)) as db, db:
            for statement in SCHEMA + (INTAKE_SCHEMA,):
                db.execute(statement)
            db.execute(f'PRAGMA application_id={APPLICATION_ID}')
            db.execute('PRAGMA user_version=2')
        store = JobStore(path)
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            self.assertIn('receipt_path', [row[1] for row in db.execute('PRAGMA table_info(attempts)')])
        self.assertEqual(store.components(), [])


if __name__ == '__main__':
    unittest.main()
