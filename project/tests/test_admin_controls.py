from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import test_dashboard as fixtures
from src.foc_extractor import queue_worker
from src.foc_extractor.job_store import JobStore, SCHEMA_VERSION
from src.foc_extractor.pipeline_config import attempt_metadata
from src.foc_extractor.queue_worker import QueueWorker


class AdminControlTests(unittest.TestCase):
    def setUp(self):
        fixtures.DashboardTests.setUp(self)
        self.token = self.client.get('/api/controls').get_json()['csrf_token']
        self.headers = {'Origin':'http://localhost','X-CSRF-Token':self.token}

    convert = fixtures.DashboardTests.convert
    complete = fixtures.DashboardTests.complete

    def command(self, action, *, job=None, attempt=None, request_id=None):
        return self.store.admin_command(request_id or str(uuid4()), action, job_id=job, attempt_id=attempt)

    def failed_attempt(self):
        attempt = self.store.claim_next('test', attempt_metadata(self.config))
        self.store.finish(attempt['id'],'test','failed',error='Test failure')
        return attempt['id']

    def test_pause_is_persistent_and_prevents_new_claims(self):
        request_id = str(uuid4())
        first = self.command('pause',request_id=request_id)
        self.assertEqual(first,self.command('pause',request_id=request_id))
        reopened = JobStore(self.store.path)
        self.assertTrue(reopened.queue_control()['paused'])
        self.assertIsNone(reopened.claim_next('worker',{}))
        self.assertEqual(self.store.attempts(self.job),[])
        with self.store._connection() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM admin_commands').fetchone()[0],1)
        self.command('resume')
        self.assertIsNotNone(reopened.claim_next('worker',{}))

    def test_pause_inside_conversion_allows_current_invoice_to_finish(self):
        def convert(*args,**kwargs):
            self.command('pause')
            return self.convert(*args,**kwargs)
        with patch.object(queue_worker,'run',side_effect=convert), QueueWorker(self.config,self.store) as worker:
            attempt = worker.run_once()
            self.assertIsNone(worker.run_once())
        self.assertEqual(self.store.get_attempt(attempt)['state'],'completed')
        self.assertTrue(self.store.queue_control()['paused'])

    def test_concurrent_retries_and_old_request_replay_cannot_duplicate_work(self):
        attempt = self.failed_attempt()
        request_id = str(uuid4())
        def retry(number):
            return self.command('retry',job=self.job,attempt=attempt,request_id=request_id)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(retry,range(8)))
        self.assertTrue(all(r==results[0] for r in results))
        self.assertEqual(len(self.store.attempts(self.job)),1)
        next_attempt = self.store.claim_next('new',{})
        self.store.finish(next_attempt['id'],'new','failed',error='Second failure')
        self.assertEqual(retry(0),results[0])
        self.assertEqual(self.store.get_job(self.job)['state'],'failed')
        with self.assertRaises(ValueError):
            self.command('retry',job=self.job,attempt=attempt)

    def test_reprocess_keeps_old_invoice_download_and_creates_version(self):
        old = self.complete()
        path = Path(self.store.get_attempt(old)['output_path'])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        response = self.client.post(f'/api/jobs/{self.job}/reprocess',headers=self.headers,
            json={'request_id':str(uuid4()),'attempt_id':old})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.client.get(f'/files/attempts/{old}/invoice').status_code,200)
        new = self.complete()
        self.assertNotEqual(old,new)
        self.assertNotEqual(str(path),self.store.get_attempt(new)['output_path'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)

    def test_save_retry_while_paused_reuses_prepared_invoice_without_ocr(self):
        with patch.object(queue_worker,'run',side_effect=self.convert) as converter, QueueWorker(self.config,self.store) as worker:
            with patch.object(queue_worker,'_publish_copy',side_effect=PermissionError('Locked')):
                attempt = worker.run_once()
            self.assertEqual(self.store.get_job(self.job)['state'],'waiting_to_save')
            self.command('pause')
            request_id = str(uuid4())
            accepted = self.command('retry_save',job=self.job,attempt=attempt,request_id=request_id)
            self.assertIsNone(worker.run_once())
            self.assertEqual(converter.call_count,1)
        self.assertEqual(self.store.get_job(self.job)['state'],'completed')
        self.assertEqual(len(self.store.attempts(self.job)),1)
        self.assertEqual(accepted,self.command('retry_save',job=self.job,attempt=attempt,request_id=request_id))

    def test_commands_require_csrf_origin_json_and_valid_fields(self):
        payload = {'request_id':str(uuid4())}
        for headers in ({},{'Origin':'http://localhost'},{'Origin':'https://evil.example','X-CSRF-Token':self.token},
                        {**self.headers,'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.client.post('/api/queue/pause',json=payload,headers=headers).status_code,403)
        self.assertEqual(self.client.post('/api/queue/pause',data='{}',headers=self.headers).status_code,415)
        for body in ({},[],{'request_id':'bad'},{**payload,'extra':True}):
            self.assertEqual(self.client.post('/api/queue/pause',json=body,headers=self.headers).status_code,400)
        self.assertFalse(self.store.queue_control()['paused'])
        self.assertEqual(self.client.get('/api/queue/pause').status_code,405)
        self.assertEqual(self.client.post('/api/queue/pause',json=payload,headers=self.headers).status_code,200)
        self.assertEqual(self.client.post('/api/queue/resume',json=payload,headers=self.headers).status_code,409)

    def test_only_latest_eligible_attempt_can_be_retried(self):
        attempt = self.failed_attempt()
        for number in (attempt+1,True,'1',-1):
            response = self.client.post(f'/api/jobs/{self.job}/retry',headers=self.headers,
                json={'request_id':str(uuid4()),'attempt_id':number})
            self.assertEqual(response.status_code,409 if number==attempt+1 else 400)
        self.assertEqual(self.client.post('/api/jobs/999/retry',headers=self.headers,
            json={'request_id':str(uuid4()),'attempt_id':attempt}).status_code,404)

    def test_get_controls_does_not_write_and_old_token_fails_after_restart(self):
        before = self.store.path.read_bytes()
        self.assertEqual(self.client.get('/api/controls').status_code,200)
        self.assertEqual(before,self.store.path.read_bytes())
        from src.foc_extractor.dashboard import create_app
        restarted = create_app(self.config).test_client()
        self.assertEqual(restarted.post('/api/queue/pause',headers=self.headers,
            json={'request_id':str(uuid4())}).status_code,403)

    def test_schema_three_migration_preserves_jobs_and_attempts(self):
        attempt = self.failed_attempt()
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute('DROP TABLE admin_commands')
            db.execute('DROP TABLE queue_control')
            db.execute('ALTER TABLE jobs DROP COLUMN manual_edit_json')
            db.execute('PRAGMA user_version=3')
        with self.assertRaises(ValueError):
            JobStore(self.store.path,read_only=True)
        migrated = JobStore(self.store.path)
        self.assertEqual(migrated.get_attempt(attempt)['state'],'failed')
        self.assertFalse(migrated.queue_control()['paused'])
        with migrated._connection() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)

    def test_retry_audit_failure_rolls_back_job_and_idempotency_record(self):
        attempt = self.failed_attempt()
        request_id = str(uuid4())
        with patch.object(self.store,'_event',side_effect=OSError('Audit write failed')):
            with self.assertRaises(OSError):
                self.command('retry',job=self.job,attempt=attempt,request_id=request_id)
        self.assertEqual(self.store.get_job(self.job)['state'],'failed')
        with self.store._connection() as db:
            self.assertIsNone(db.execute('SELECT 1 FROM admin_commands WHERE request_id=?',(request_id,)).fetchone())


if __name__=='__main__':unittest.main()
