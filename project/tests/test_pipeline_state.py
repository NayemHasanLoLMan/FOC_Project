import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor.pipeline_config import load_config, attempt_metadata
from src.foc_extractor.job_store import JobStore, STATES, SCHEMA_VERSION


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.path = self.root / 'pipeline_config.json'
        self.raw = json.loads((ROOT / 'pipeline_config.json').read_text())
        self.write()

    def write(self):
        self.path.write_text(json.dumps(self.raw), encoding='utf-8')

    def test_paths_are_relative_to_config_and_loading_creates_nothing(self):
        config = load_config(self.path)
        self.assertEqual(config.incoming_dir, self.root / 'incoming/bangladesh')
        self.assertEqual(config.output_dir, self.root / 'output/bangladesh')
        self.assertFalse(config.state_dir.exists())
        self.assertFalse(config.incoming_dir.exists())
        self.assertEqual(config.to_dict()['incoming_dir'], str(config.incoming_dir))
        self.raw['local_model'] = None
        self.write()
        self.assertIsNone(load_config(self.path).local_model)

    def test_rejects_unknown_missing_and_invalid_configuration(self):
        original = dict(self.raw)
        for key, value in [('scan_interval_seconds', 0), ('scan_interval_seconds', True),
                           ('scan_interval_seconds', float('inf')), ('scan_interval_seconds', float('nan')),
                           ('local_model', ''), ('local_model', 1), ('incoming_dir', '')]:
            with self.subTest(key=key, value=value):
                self.raw = {**original, key: value}
                self.write()
                with self.assertRaises(ValueError):
                    load_config(self.path)
        for raw in [{**original, 'typo': True}, {k: v for k, v in original.items() if k != 'output_dir'}, []]:
            self.raw = raw
            self.write()
            with self.assertRaises(ValueError):
                load_config(self.path)

    def test_rejects_overlapping_paths_and_files(self):
        for output in ['incoming', 'incoming/bangladesh/outputs', '.']:
            self.raw['output_dir'] = output
            self.write()
            with self.assertRaisesRegex(ValueError, 'overlap'):
                load_config(self.path)
        self.raw['output_dir'] = 'output'
        (self.root / 'output').write_text('not a directory')
        self.write()
        with self.assertRaisesRegex(ValueError, 'points to a file'):
            load_config(self.path)

    def test_attempt_snapshot_records_real_versions_and_unknown_model_digest(self):
        config = load_config(self.path)
        metadata = attempt_metadata(config)
        self.assertEqual(metadata['configuration'], config.to_dict())
        self.assertEqual(metadata['template_sha256'], hashlib.sha256((ROOT / 'templates/BD_template.xlsx').read_bytes()).hexdigest())
        self.assertEqual(metadata['rates_sha256'], hashlib.sha256((ROOT / 'valuation_rates.json').read_bytes()).hexdigest())
        self.assertEqual(len(metadata['application_sha256']), 64)
        self.assertIsNone(metadata['model_digest'])
        self.assertFalse(config.state_dir.exists())

    def test_initializer_only_creates_empty_state_without_starting_processing(self):
        result = subprocess.run([sys.executable, str(ROOT / 'init_pipeline.py'), '--config', str(self.path)],
                                capture_output=True, text=True, check=True, cwd=self.root)
        result = json.loads(result.stdout)
        self.assertFalse(result['processing_started'])
        self.assertEqual(sum(result['jobs'].values()), 0)
        self.assertTrue(Path(result['database']).is_file())
        for name in ['incoming/bangladesh', 'output/bangladesh','incoming/india','output/jordan']:
            self.assertTrue((self.root / name).is_dir(), name)
        self.assertFalse((self.root/'runtime/artifacts').exists())


class JobStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.database = self.root / 'state/jobs.sqlite3'
        self.store = JobStore(self.database)

    def enqueue(self, name='shipment.pdf', digest='a' * 64):
        return self.store.enqueue(self.root / name, digest, self.root / 'snapshots' / name)

    def test_idempotent_intake_and_changed_or_renamed_inputs(self):
        first = self.enqueue()
        self.assertEqual(self.enqueue(), first)
        self.assertEqual(len(self.store.events(first)), 1)
        self.assertNotEqual(self.enqueue(digest='b' * 64), first)
        self.assertNotEqual(self.enqueue(name='renamed.pdf'), first)
        self.assertEqual(self.store.counts()['queued'], 3)
        self.assertEqual(self.store.get_job(first)['snapshot_path'], str(self.root / 'snapshots/shipment.pdf'))

    def test_invalid_input_is_not_queued(self):
        for name, digest, snapshot in [('a.txt', 'a' * 64, 'a.txt'), ('a.pdf', 'not-a-hash', 'a.pdf'),
                                       ('a.pdf', 'a' * 64, 'changed.pdf')]:
            with self.subTest(name=name, digest=digest, snapshot=snapshot):
                with self.assertRaises(ValueError):
                    self.store.enqueue(self.root / name, digest, self.root / snapshot)
        self.assertEqual(sum(self.store.counts().values()), 0)

    def test_separate_connections_cannot_claim_duplicate_or_parallel_work(self):
        self.enqueue()
        self.enqueue(name='second.pdf')
        def claim(number):
            return JobStore(self.database).claim_next(f'worker-{number}', {'test': True})
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(claim, range(4)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)
        self.assertEqual(self.store.counts()['running'], 1)
        self.assertEqual(self.store.counts()['queued'], 1)

    def test_running_ownership_survives_a_new_process_and_requires_explicit_recovery(self):
        job = self.enqueue()
        attempt = self.store.claim_next('original-worker', {'model_digest': None})
        code = ("import json,sys;sys.path.insert(0,sys.argv[1]);"
                "from src.foc_extractor.job_store import JobStore;"
                "s=JobStore(sys.argv[2]);"
                "print(json.dumps({'counts':s.counts(),'claim':s.claim_next('other-worker',{})}))")
        result = subprocess.run([sys.executable, '-c', code, str(ROOT), str(self.database)],
                                check=True, capture_output=True, text=True)
        result = json.loads(result.stdout)
        self.assertEqual(result['counts']['running'], 1)
        self.assertIsNone(result['claim'])
        self.store.finish(attempt['id'], 'original-worker', 'interrupted', error='Worker death confirmed by supervisor')
        self.store.retry(job)
        next_attempt = JobStore(self.database).claim_next('replacement-worker', {'template': 'new'})
        self.assertNotEqual(next_attempt['id'], attempt['id'])
        self.assertEqual([a['state'] for a in self.store.attempts(job)], ['interrupted', 'running'])
        self.assertEqual(next_attempt['metadata'], {'template': 'new', 'region': 'BD'})
        with self.assertRaises(ValueError):
            self.store.heartbeat(attempt['id'], 'original-worker')

    def test_only_owner_can_update_and_completed_jobs_cannot_be_retried(self):
        job = self.enqueue()
        attempt = self.store.claim_next('owner', {})
        with self.assertRaises(ValueError):
            self.store.heartbeat(attempt['id'], 'stranger')
        with self.assertRaises(ValueError):
            self.store.finish(attempt['id'], 'stranger', 'failed', error='wrong owner')
        self.store.heartbeat(attempt['id'], 'owner')
        output = self.root / 'invoice.xlsx'
        output.write_bytes(b'test output')
        self.store.finish(attempt['id'], 'owner', 'completed', output_path=output,
                          issues=['Unsupported net weight remains empty'])
        self.assertEqual(self.store.get_job(job)['state'], 'completed')
        history = self.store.attempts(job)[0]
        self.assertEqual(history['issues'], ['Unsupported net weight remains empty'])
        self.assertIsNotNone(history['finished_at'])
        with self.assertRaises(ValueError):
            self.store.retry(job)
        with self.assertRaises(ValueError):
            self.store.finish(attempt['id'], 'owner', 'failed', error='late result')

    def test_invalid_results_do_not_complete_jobs(self):
        job = self.enqueue()
        attempt = self.store.claim_next('owner', {})
        for state, kwargs in [('completed', {}), ('completed', {'output_path': self.root / 'missing.xlsx'}),
                              ('failed', {}), ('interrupted', {}), ('queued', {})]:
            with self.subTest(state=state, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.store.finish(attempt['id'], 'owner', state, **kwargs)
        self.assertEqual(self.store.get_job(job)['state'], 'running')

    def test_failed_attempt_and_events_remain_after_retry_and_reopen(self):
        job = self.enqueue()
        metadata = {'configuration': {'local_model': None}, 'template_sha256': 'old'}
        attempt = self.store.claim_next('owner', metadata)
        metadata['template_sha256'] = 'changed after claim'
        self.store.finish(attempt['id'], 'owner', 'failed', error='Invalid PDF')
        store = JobStore(self.database)
        self.assertEqual(store.attempts(job)[0]['metadata']['template_sha256'], 'old')
        self.assertEqual(store.attempts(job)[0]['error'], 'Invalid PDF')
        store.retry(job)
        self.assertEqual([e['kind'] for e in store.events(job)], ['queued', 'started', 'failed', 'queued_again'])
        self.assertEqual(store.counts()['queued'], 1)
        self.assertEqual(set(store.counts()), set(STATES))

    def test_event_failure_rolls_back_job_and_attempt_together(self):
        job = self.enqueue()
        with patch.object(self.store, '_event', side_effect=OSError('Event storage failed')):
            with self.assertRaises(OSError):
                self.store.claim_next('worker', {})
        self.assertEqual(self.store.get_job(job)['state'], 'queued')
        self.assertEqual(self.store.attempts(job), [])
        attempt = self.store.claim_next('worker', {})
        with patch.object(self.store, '_event', side_effect=OSError('Event storage failed')):
            with self.assertRaises(OSError):
                self.store.finish(attempt['id'], 'worker', 'failed', error='test')
        self.assertEqual(self.store.get_job(job)['state'], 'running')
        self.assertEqual(self.store.attempts(job)[0]['state'], 'running')

    def test_unrelated_and_future_databases_are_not_modified(self):
        path = self.root / 'unrelated.sqlite3'
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE unrelated(value TEXT)')
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            JobStore(path)
        with closing(sqlite3.connect(path)) as db, db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall(), [('unrelated',)])
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute(f'PRAGMA user_version={SCHEMA_VERSION+1}')
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            JobStore(self.database)


if __name__ == '__main__':
    unittest.main()
