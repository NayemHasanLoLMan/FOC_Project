import hashlib
import json
import re
from pathlib import Path
import sys
import threading
import unittest
from dataclasses import replace
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import test_dashboard as fixtures
from src.foc_extractor import runtime_settings as settings, local_vision, queue_worker
from src.foc_extractor.dashboard import create_app
from src.foc_extractor.pipeline_config import load_config
from src.foc_extractor.queue_worker import QueueWorker


class RuntimeSettingsTests(unittest.TestCase):
    convert=fixtures.DashboardTests.convert
    complete=fixtures.DashboardTests.complete

    def setUp(self):
        fixtures.DashboardTests.setUp(self)
        self.locks=(threading.Lock(),threading.Lock())
        def apply(config):
            self.config=config
            self.app.extensions['dashboard_data'].config=config
        self.app=create_app(self.config,update_settings=lambda rid,changes:
            settings.save_runtime_settings(self.config,self.store,self.locks,rid,changes,apply))
        self.client=self.app.test_client()
        self.headers={'Origin':'http://localhost','X-CSRF-Token':self.client.get('/api/controls').get_json()['csrf_token']}

    def save(self,changes=None,rid=None):
        return self.client.post('/api/settings',json={'request_id':rid or str(uuid4()),'changes':changes or settings.editable_settings(self.config)},headers=self.headers)

    def test_saves_all_settings_persists_and_preserves_historical_downloads(self):
        attempt=self.complete();old=self.client.get(f'/files/attempts/{attempt}/invoice').data
        original=self.config
        changes={**settings.editable_settings(self.config),'local_model':'another:latest','scan_interval_seconds':2,
            'vision_output_tokens':6000,'vision_context_tokens':16000,'vision_timeout_seconds':9000,
            'incoming_dir':str(self.root/'new-input'),'output_dir':str(self.root/'new-output')}
        rid=str(uuid4());response=self.save(changes,rid)
        self.assertEqual(response.status_code,200,response.data)
        self.assertEqual(settings.editable_settings(settings.load_runtime_settings(original)),changes)
        self.assertEqual(self.client.get('/api/system').get_json()['settings'],changes)
        self.assertEqual(self.client.get(f'/files/attempts/{attempt}/invoice').data,old)
        self.assertTrue(self.config.incoming_dir.is_dir());self.assertTrue(self.config.output_dir.is_dir())
        self.assertIn('settings-editor',self.client.get('/system').get_data(as_text=True))
        newer={**changes,'scan_interval_seconds':3};self.assertEqual(self.save(newer).status_code,200)
        self.assertEqual(self.save(changes,rid).get_json(),response.get_json())
        self.assertEqual(self.config.scan_interval_seconds,3)

    def test_invalid_busy_and_unprotected_requests_leave_settings_unchanged(self):
        before=self.config
        for key,value in [('vision_output_tokens',0),('vision_context_tokens',True),('vision_timeout_seconds',1.2),
                          ('vision_output_tokens',9000),('scan_interval_seconds',0),('scan_interval_seconds',1e100),('local_model',''),
                          ('incoming_dir','relative'),('output_dir',str(self.config.artifact_dir)),
                          ('output_dir',str(ROOT/'templates')),('output_dir',str(self.root))]:
            with self.subTest(key=key,value=value):
                self.assertEqual(self.save({**settings.editable_settings(before),key:value}).status_code,409)
                self.assertEqual(self.config,before)
        self.locks[1].acquire()
        try:self.assertEqual(self.save().status_code,409)
        finally:self.locks[1].release()
        self.assertEqual(self.client.post('/api/settings',json={}).status_code,403)
        self.assertFalse((before.state_dir/'settings.json').exists())
        standalone=create_app(before).test_client()
        token=standalone.get('/api/controls').get_json()['csrf_token']
        self.assertEqual(standalone.post('/api/settings',json={'request_id':str(uuid4()),'changes':settings.editable_settings(before)},
            headers={'Origin':'http://localhost','X-CSRF-Token':token}).status_code,403)

    def test_worker_uses_saved_limits_and_output_for_next_job(self):
        changes={**settings.editable_settings(self.config),'output_dir':str(self.root/'new-output'),
                 'vision_output_tokens':1024,'vision_context_tokens':2048,'vision_timeout_seconds':99}
        self.assertEqual(self.save(changes).status_code,200)
        def convert(*args,**kwargs):
            self.assertEqual(local_vision._limits.get(),(1024,2048,99))
            return self.convert(*args,**kwargs)
        with patch.object(queue_worker,'run',side_effect=convert),QueueWorker(self.config,self.store) as worker:
            attempt=worker.run_once()
        record=self.store.get_attempt(attempt)
        self.assertEqual(record['state'],'completed',record['error'])
        self.assertEqual(Path(record['output_path']).parent,self.config.output_dir)
        self.assertEqual(record['metadata']['configuration']['vision_timeout_seconds'],99)
        self.assertEqual(local_vision._limits.get(),(4096,8192,7200))

    def test_failed_settings_write_keeps_current_config_and_request_retryable(self):
        with patch('src.foc_extractor.queue_worker._write_json',side_effect=OSError('Disk unavailable')):
            self.assertEqual(self.save().status_code,503)
        self.assertFalse((self.config.state_dir/'settings.json').exists())
        with self.store._connection() as db:self.assertEqual(db.execute("select count(*) from admin_commands where action='settings'").fetchone()[0],0)

    def test_config_defaults_and_changed_vision_settings_partition_cache(self):
        config=load_config()
        self.assertEqual((config.vision_output_tokens,config.vision_context_tokens,config.vision_timeout_seconds),(4096,8192,7200))
        self.assertEqual(local_vision.vision_cache_settings(local_vision.DEFAULT_MODEL),{})
        with local_vision.vision_limits(replace(config,vision_output_tokens=1024)):
            self.assertIn('vision_limits',local_vision.vision_cache_settings(local_vision.DEFAULT_MODEL))
            with patch.object(local_vision.urllib.request,'urlopen') as open_url:
                open_url.return_value.__enter__.return_value.read.return_value=b'{}'
                local_vision._request('tags')
                self.assertEqual(open_url.call_args.kwargs['timeout'],7200)
        with local_vision.vision_limits(replace(config,vision_timeout_seconds=17)):
            with patch.object(local_vision.urllib.request,'urlopen') as open_url:
                open_url.return_value.__enter__.return_value.read.return_value=b'{}'
                local_vision._request('tags')
                self.assertEqual(open_url.call_args.kwargs['timeout'],17)

    def test_shared_folders_create_country_children_and_preserve_old_download(self):
        attempt=self.complete();old=self.client.get(f'/files/attempts/{attempt}/invoice').data
        incoming=self.root/'shared-input';output=self.root/'shared-output'
        changes={**settings.editable_settings(self.config),'incoming_dir':str(incoming/'bangladesh'),
                 'india_incoming_dir':str(incoming/'india'),'output_dir':str(output/'bangladesh'),
                 'india_output_dir':str(output/'india'),'india_enabled':True}
        self.assertEqual(self.save(changes).status_code,200)
        self.assertEqual(settings.shared_folders(self.config),{'incoming':incoming,'output':output})
        for parent in (incoming,output):
            for country in ('bangladesh','india','jordan'):self.assertTrue((parent/country).is_dir())
        self.assertEqual(self.client.get(f'/files/attempts/{attempt}/invoice').data,old)
        html=self.client.get('/system').get_data(as_text=True)
        self.assertEqual(html.count('data-folder-kind='),2)
        self.assertNotIn('Folders &amp; disk space',html)
        self.assertNotIn(str(incoming),re.sub(r'<[^>]*>','',html))
        self.assertIn('Jordan intake is disabled',html)

    def test_existing_separate_paths_are_not_misrepresented_as_a_shared_root(self):
        custom=replace(self.config,incoming_dir=self.root/'input/bangladesh',india_incoming_dir=self.root/'other/india',
                       india_output_dir=self.root/'other-output/india')
        self.assertIsNone(settings.shared_folders(custom)['incoming'])
        self.assertIsNone(settings.shared_folders(custom)['output'])
        shared=replace(custom,india_incoming_dir=self.root/'input/india')
        self.assertEqual(settings.shared_folders(shared)['incoming'],self.root/'input')

    def test_country_controls_persist_and_legacy_requests_preserve_their_state(self):
        original=self.config
        changes={**settings.editable_settings(original),'bangladesh_enabled':False}
        self.assertEqual(self.save(changes).status_code,200)
        self.assertFalse(settings.load_runtime_settings(original).bangladesh_enabled)
        legacy={key:value for key,value in changes.items() if key not in ('bangladesh_enabled','jordan_enabled')}
        self.assertEqual(self.save(legacy).status_code,200)
        self.assertFalse(self.config.bangladesh_enabled)
        self.assertEqual(self.save({**settings.editable_settings(self.config),'jordan_enabled':True}).status_code,409)
        html=self.client.get('/system').get_data(as_text=True)
        for country in ('bangladesh','india','jordan'):
            self.assertIn('name="'+country+'_enabled"',html)
            self.assertIn('data-intake-status="'+country+'"',html)
        self.assertRegex(html,r'id="jordan-intake"[^>]* disabled')

    def test_folder_browser_requires_protection_and_does_not_save_settings(self):
        chosen=self.root/'chosen';chosen.mkdir()
        for payload in ({'kind':'incoming'},{'kind':'output','path':str(chosen)}):
            response=self.client.post('/api/folders/browse',json=payload,headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertTrue(Path(response.get_json()['path']).is_absolute())
        for payload in ({},{'kind':'bad'},{'kind':'incoming','extra':'arbitrary'},{'kind':'incoming','path':True}):
            self.assertEqual(self.client.post('/api/folders/browse',json=payload,headers=self.headers).status_code,400)
        self.assertEqual(self.client.post('/api/folders/browse',json={'kind':'incoming'}).status_code,403)
        standalone=create_app(self.config).test_client()
        headers={'Origin':'http://localhost','X-CSRF-Token':standalone.get('/api/controls').get_json()['csrf_token']}
        self.assertEqual(standalone.post('/api/folders/browse',json={'kind':'incoming'},headers=headers).status_code,403)
        self.assertFalse((self.config.state_dir/'settings.json').exists())

    def test_browser_lists_sorted_directories_without_files_or_hidden_folders(self):
        for name in ('b','A','.hidden','linked'):(self.root/name).mkdir()
        (self.root/'shipment.pdf').write_bytes(b'private file')
        with patch.object(Path,'is_junction',autospec=True,side_effect=lambda path:path.name=='linked'):
            result=settings.folder_contents(self.root)
        names=[item['name'] for item in result['directories']]
        self.assertNotIn('shipment.pdf',names);self.assertNotIn('.hidden',names);self.assertNotIn('linked',names)
        self.assertEqual(names,sorted(names,key=str.casefold))
        self.assertEqual(result['parent'],str(self.root.parent))
        self.assertTrue(result['locations'])

    def test_browser_refuses_relative_paths_files_and_redirected_paths(self):
        file=self.root/'not-a-directory';file.write_bytes(b'do not serve')
        for path in ('relative',str(file),str(self.root/'missing')):
            self.assertEqual(self.client.post('/api/folders/browse',json={'kind':'incoming','path':path},headers=self.headers).status_code,409)
        with patch.object(Path,'is_junction',return_value=True):
            self.assertEqual(self.client.post('/api/folders/browse',json={'kind':'incoming','path':str(self.root)},headers=self.headers).status_code,409)


if __name__=='__main__':unittest.main()
