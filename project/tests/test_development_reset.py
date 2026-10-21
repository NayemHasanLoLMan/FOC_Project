import hashlib
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from uuid import uuid4

import pymupdf
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import test_dashboard as fixtures
from src.foc_extractor import development_reset as reset, queue_worker
from src.foc_extractor.dashboard import create_app
from src.foc_extractor.folder_intake import FolderScanner
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.pipeline_config import load_config
from src.foc_extractor.queue_worker import QueueWorker


class DevelopmentResetTests(unittest.TestCase):
    convert=fixtures.DashboardTests.convert

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve()/'workspace'
        patcher=patch.object(reset,'DEVELOPMENT_ROOT',self.root);patcher.start();self.addCleanup(patcher.stop)
        self.config=reset.development_config(load_config())
        self.config.incoming_dir.mkdir(parents=True)
        self.source=self.config.incoming_dir/'shipment.pdf'
        with pymupdf.open() as pdf:pdf.new_page().insert_text((40,40),'TEST PDF');pdf.save(self.source)
        self.original=self.source.read_bytes()
        self.store=JobStore(self.config.state_dir/'jobs.sqlite3');self.scanner=FolderScanner(self.config,self.store)
        self.scan(0);self.scan(6)
        with patch.object(queue_worker,'run',side_effect=self.convert),QueueWorker(self.config,self.store) as worker:self.attempt=worker.run_once()
        self.output=Path(self.store.get_attempt(self.attempt)['output_path'])
        self.locks=(threading.Lock(),threading.Lock())
        self.client=create_app(self.config,development_mode=True,development_reset=lambda rid:reset.clear_development(self.config,self.store,self.locks,rid)).test_client()
        self.headers={'Origin':'http://localhost','X-CSRF-Token':self.client.get('/api/controls').get_json()['csrf_token']}

    def scan(self,when):
        with patch('src.foc_extractor.folder_intake.time.time',return_value=when):return self.scanner.scan_once()

    def clear(self,rid=None):
        return self.client.post('/api/development/reset',json={'request_id':rid or str(uuid4())},headers=self.headers)

    def test_clear_archives_and_recreates_invoice_from_unchanged_input_once(self):
        rid=str(uuid4());digest=hashlib.sha256(self.output.read_bytes()).hexdigest()
        self.assertIn('>Clear data</button>',self.client.get('/system').get_data(as_text=True))
        response=self.clear(rid);self.assertEqual(response.status_code,200,response.data)
        result=response.get_json();archive=self.root/result['archive']
        self.assertEqual(result['cleared_jobs'],1)
        self.assertTrue((archive/'jobs.sqlite3').is_file())
        self.assertEqual(hashlib.sha256((archive/'output'/self.output.name).read_bytes()).hexdigest(),digest)
        self.assertTrue((archive/'artifacts').is_dir());self.assertFalse(self.output.exists())
        self.assertEqual(self.source.read_bytes(),self.original)
        self.assertEqual(sum(self.store.counts().values()),0)
        self.scan(100);self.assertEqual(sum(self.store.counts().values()),0)
        self.scan(106)
        self.assertEqual(self.store.counts()['queued'],1)
        self.assertEqual(self.clear(rid).get_json(),result)
        self.assertEqual(self.store.counts()['queued'],1)
        with patch.object(queue_worker,'run',side_effect=self.convert),QueueWorker(self.config,self.store) as worker:
            attempt=worker.run_once()
            self.assertIsNone(worker.run_once())
        self.assertGreater(attempt,self.attempt)
        self.assertTrue(Path(self.store.get_attempt(attempt)['output_path']).is_file())
        self.scan(200);self.scan(206)
        self.assertEqual(self.store.counts()['completed'],1)
        self.assertEqual(sum(self.store.counts().values()),1)
        self.assertEqual(self.source.read_bytes(),self.original)

    def test_clear_resumes_a_paused_queue(self):
        with self.store._connection(write=True) as db:db.execute('UPDATE queue_control SET paused=1 WHERE id=1')
        self.assertEqual(self.clear().status_code,200)
        self.assertFalse(self.store.queue_control()['paused'])

    def test_scanner_recovers_intakes_left_by_previous_clear_implementation(self):
        with self.store._connection(write=True) as db:
            db.execute('UPDATE intake_files SET job_id=NULL')
            for table in ('events','attempts','jobs'):db.execute('DELETE FROM '+table)
        self.scan(100);self.assertEqual(sum(self.store.counts().values()),0)
        self.scan(106);self.assertEqual(self.store.counts()['queued'],1)
        self.scan(200);self.assertEqual(self.store.counts()['queued'],1)

    def test_busy_worker_and_invalid_request_do_not_clear_any_data(self):
        self.locks[1].acquire()
        try:self.assertEqual(self.clear().status_code,409)
        finally:self.locks[1].release()
        self.assertEqual(self.client.post('/api/development/reset',json={}).status_code,403)
        self.assertEqual(self.client.post('/api/development/reset',json={'request_id':'bad'},headers=self.headers).status_code,400)
        self.assertTrue(self.output.is_file());self.assertEqual(self.store.counts()['completed'],1)

    def test_rename_failure_restores_files_and_database(self):
        rename=Path.rename
        def fail_output(path,target):
            if path==self.config.output_dir:raise PermissionError('Excel has locked this folder')
            return rename(path,target)
        with patch.object(Path,'rename',fail_output):response=self.clear()
        self.assertEqual(response.status_code,503)
        self.assertTrue(self.output.exists());self.assertTrue(self.config.artifact_dir.exists())
        self.assertEqual(self.store.counts()['completed'],1)

    def test_output_on_another_volume_is_archived_beside_that_output_folder(self):
        import os
        import json
        original=Path.stat
        def separate_volume(path,*args,**kwargs):
            result=original(path,*args,**kwargs)
            if path==self.config.output_dir:
                values=list(result);values[2]=result.st_dev+1
                return os.stat_result(values)
            return result
        with patch.object(Path,'stat',separate_volume):response=self.clear()
        self.assertEqual(response.status_code,200,response.data)
        archive=self.root/response.get_json()['archive']
        location=json.loads((archive/'external-output.json').read_text())
        target=Path(location['archived'])
        self.assertTrue(target.is_relative_to(self.config.output_dir.parent/'.foc-cleared'))
        self.assertTrue((target/self.output.name).is_file())
        self.assertEqual(list(self.config.output_dir.iterdir()),[])
        self.assertTrue(self.source.is_file())

    def test_production_paths_cannot_be_used_for_development_reset(self):
        with patch.object(Path,'rename') as move:
            with self.assertRaises(ValueError):reset.clear_development(load_config(),self.store,self.locks,str(uuid4()))
        move.assert_not_called();self.assertTrue(self.output.exists())

    def test_redirected_archive_is_rejected_before_moving_files(self):
        resolve=Path.resolve
        def outside(path,*args,**kwargs):
            if self.root/'cleared' in path.parents:return self.root.parent/'outside'/path.name
            return resolve(path,*args,**kwargs)
        with patch.object(Path,'resolve',outside),patch.object(Path,'rename') as move:
            with self.assertRaisesRegex(ValueError,'archive escapes'):
                reset.clear_development(self.config,self.store,self.locks,str(uuid4()))
        move.assert_not_called();self.assertTrue(self.output.exists())


class MainWorkspaceResetTests(DevelopmentResetTests):
    def setUp(self):
        super().setUp()
        # Simulate the main layout entirely inside the temporary fixture, never the real workspace.
        from dataclasses import replace
        patcher=patch.object(reset,'ROOT',self.root);patcher.start();self.addCleanup(patcher.stop)
        self.config=replace(self.config,state_dir=self.root/'runtime/state',artifact_dir=self.root/'runtime/artifacts')
        self.config.state_dir.parent.mkdir(parents=True)
        self.store.path.parent.rename(self.config.state_dir)
        old_artifacts=self.root/'artifacts'
        old_artifacts.rename(self.config.artifact_dir)
        self.store=JobStore(self.config.state_dir/'jobs.sqlite3')
        self.scanner=FolderScanner(self.config,self.store)
        self.client=create_app(self.config,development_reset=lambda rid:reset.clear_workspace(self.config,self.store,self.locks,rid)).test_client()
        self.headers={'Origin':'http://localhost','X-CSRF-Token':self.client.get('/api/controls').get_json()['csrf_token']}

    def test_main_page_offers_clear_without_development_banner(self):
        html=self.client.get('/system').get_data(as_text=True)
        self.assertIn('>Clear data</button>',html)
        self.assertNotIn('Test data is separate from production',html)

    def test_redirected_archive_is_rejected_before_moving_files(self):
        resolve=Path.resolve
        def outside(path,*args,**kwargs):
            if self.root/'runtime/cleared' in path.parents:return self.root.parent/'outside'/path.name
            return resolve(path,*args,**kwargs)
        with patch.object(Path,'resolve',outside),patch.object(Path,'rename') as move:
            with self.assertRaisesRegex(ValueError,'archive escapes'):
                reset.clear_workspace(self.config,self.store,self.locks,str(uuid4()))
        move.assert_not_called();self.assertTrue(self.output.exists())


if __name__=='__main__':unittest.main()
