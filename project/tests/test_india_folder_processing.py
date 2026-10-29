"""Mixed-country routing uses the existing scanner, queue and recovery contracts."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from uuid import uuid4

import pymupdf

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor import development_reset, queue_worker, runtime_settings, system_runner
from src.foc_extractor.dashboard import create_app
from src.foc_extractor.excel_writer import populate_template
from src.foc_extractor.folder_intake import FolderScanner
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.models import FOCData,LineItem
from src.foc_extractor.pipeline_config import load_config,parse_config,initialize_folders


class IndiaFolderTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name).resolve()
        raw=json.loads((ROOT/'pipeline_config.json').read_text())
        raw.update(india_enabled=True,india_incoming_dir='incoming/india',india_output_dir='output/india')
        self.config=parse_config(raw,self.root);initialize_folders(self.config)
        self.store=JobStore(self.config.state_dir/'jobs.sqlite3')
        self.scanner=FolderScanner(self.config,self.store)
        self.locks=(threading.Lock(),threading.Lock())

    def source(self,region='BD',name='shipment.pdf'):
        path=self.config.inboxes()[region]/name
        with pymupdf.open() as doc:
            doc.new_page().insert_text((40,40),'PDF '+region);doc.save(path)
        return path

    def scan(self,when):
        with patch('src.foc_extractor.folder_intake.time.time',return_value=when):
            return self.scanner.scan_once()

    def accept(self):
        self.source();self.source('INDIA');self.scan(0)
        return self.scan(6)['accepted_job_ids']

    def convert(self,source,*,region,template,output_dir,**kwargs):
        self.assertEqual(template,ROOT/f'templates/{region}_template.xlsx')
        data=FOCData(source_file=source.name,template_type=region,pages_total=1,pages_processed=1,
                     items=[LineItem('FABRIC',10,'YDS',unit_price=.2,amount=2)],total_value=2)
        target=output_dir/'shipment.xlsx';populate_template(template,target,data)
        (output_dir/(source.stem+'.json')).write_text(json.dumps(data.to_dict()))
        return target

    def save(self,changes):
        def apply(updated):self.config=updated
        return runtime_settings.save_runtime_settings(self.config,self.store,self.locks,str(uuid4()),changes,apply)

    def test_default_stays_bd_only_and_invalid_regional_configuration_is_rejected(self):
        self.assertFalse(load_config().india_enabled)
        for changes in ({'india_enabled':'true'},{'india_incoming_dir':None},{'india_output_dir':None},
                        {'india_output_dir':str(self.config.incoming_dir)},
                        {'india_incoming_dir':str(self.config.artifact_dir/'inputs')},
                        {'india_output_dir':str(self.config.india_incoming_dir/'nested')}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                parse_config({**self.config.to_dict(),**changes},self.root)

    def test_same_basename_is_separate_deduplicated_and_jordan_is_not_scanned(self):
        jordan=self.config.incoming_dir.parent/'jordan/ignored.pdf'
        jordan.write_bytes(self.source().read_bytes());self.source('INDIA')
        self.assertEqual(self.scan(0)['accepted_job_ids'],[])
        result=self.scan(6);self.assertEqual(len(result['accepted_job_ids']),2)
        self.assertEqual(set(result['folders']),{'BD','INDIA'})
        jobs=[self.store.get_job(job) for job in result['accepted_job_ids']]
        self.assertEqual([job['region'] for job in jobs],['BD','INDIA'])
        self.assertNotEqual(jobs[0]['snapshot_path'],jobs[1]['snapshot_path'])
        self.assertEqual(self.scan(12)['accepted_job_ids'],[])
        self.assertEqual(FolderScanner(self.config,self.store).scan_once()['accepted_job_ids'],[])

    def test_disabled_india_retains_queued_jobs_and_does_not_accept_new_sources(self):
        self.accept();self.scanner.config=replace(self.config,india_enabled=False)
        self.source('INDIA','later.pdf');self.scan(12);self.scan(18)
        self.assertEqual(self.store.counts()['queued'],2)
        with patch.object(queue_worker,'run',side_effect=self.convert),queue_worker.QueueWorker(self.scanner.config,self.store) as worker:
            for _ in range(2):worker.run_once()
        self.assertEqual(self.store.counts()['completed'],2)
        self.assertEqual(len(list(self.config.india_output_dir.glob('*.xlsx'))),1)

    def test_unavailable_india_folder_does_not_block_bd(self):
        self.source();self.config.india_incoming_dir.rmdir()
        self.scan(0);result=self.scan(6)
        self.assertIn('INDIA:',result['folder_error'])
        self.assertEqual(len(result['accepted_job_ids']),1)
        self.assertEqual(self.store.get_job(result['accepted_job_ids'][0])['region'],'BD')

    def test_disabling_bangladesh_keeps_india_and_finishes_already_queued_jobs(self):
        self.accept()
        later=self.config.incoming_dir/'later.pdf';later.write_bytes((self.config.incoming_dir/'shipment.pdf').read_bytes())
        self.scanner.config=replace(self.config,bangladesh_enabled=False)
        self.scan(12);result=self.scan(18)
        self.assertEqual(set(result['folders']),{'INDIA'})
        self.assertEqual(self.store.counts()['queued'],2)
        with patch.object(queue_worker,'run',side_effect=self.convert),queue_worker.QueueWorker(self.scanner.config,self.store) as worker:
            worker.run_once();worker.run_once()
        self.assertEqual(self.store.counts()['completed'],2)
        self.scanner.config=self.config
        self.scan(24);self.assertEqual(len(self.scan(30)['accepted_job_ids']),1)

    def test_all_intake_disabled_is_healthy_and_jordan_requires_folders(self):
        self.scanner.config=replace(self.config,bangladesh_enabled=False,india_enabled=False)
        result=self.scanner.scan_once()
        self.assertEqual(result['folders'],{});self.assertEqual(result['accepted_job_ids'],[])
        self.assertIsNone(result['folder_error']);self.assertEqual(result['intake_counts'],{})
        for changes in ({'bangladesh_enabled':1},{'jordan_enabled':'false'},{'jordan_enabled':True}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                parse_config({**self.config.to_dict(),**changes},self.root)

    def test_publication_and_downloads_use_the_recorded_country_output(self):
        self.accept()
        with patch.object(queue_worker,'run',side_effect=self.convert),queue_worker.QueueWorker(self.config,self.store) as worker:
            ids=[worker.run_once(),worker.run_once()]
        client=create_app(self.config).test_client()
        for aid,region in zip(ids,('BD','INDIA')):
            attempt=self.store.get_attempt(aid)
            self.assertEqual(attempt['state'],'completed',attempt['error'])
            self.assertEqual(Path(attempt['output_path']).parent,self.config.output_for(region))
            self.assertEqual(attempt['metadata']['output_dir'],str(self.config.output_for(region)))
            self.assertEqual(client.get(f'/files/attempts/{aid}/invoice').status_code,200)
            self.assertEqual(client.get(f'/invoices/attempts/{aid}').status_code,200)

    def test_locked_india_restart_uses_original_output_without_ocr(self):
        self.source('INDIA');self.scan(0);self.scan(6)
        with patch.object(queue_worker,'run',side_effect=self.convert),queue_worker.QueueWorker(self.config,self.store) as worker:
            with patch.object(queue_worker,'_publish_copy',side_effect=PermissionError('locked')):
                aid=worker.run_once()
        self.assertEqual(self.store.get_attempt(aid)['state'],'waiting_to_save')
        changed=replace(self.config,india_output_dir=self.root/'another-india-output',india_enabled=False)
        with patch.object(queue_worker,'run') as convert,queue_worker.QueueWorker(changed,self.store) as worker:
            self.assertIsNone(worker.run_once())
        convert.assert_not_called()
        attempt=self.store.get_attempt(aid)
        self.assertEqual(attempt['state'],'completed',attempt['error'])
        self.assertEqual(Path(attempt['output_path']).parent,self.config.india_output_dir)
        self.assertFalse(changed.india_output_dir.exists())
        self.assertEqual(create_app(changed).test_client().get(f'/files/attempts/{aid}/invoice').status_code,200)

    def test_failed_india_retry_keeps_country_template_and_output(self):
        self.source('INDIA');self.scan(0);job=self.scan(6)['accepted_job_ids'][0]
        with patch.object(queue_worker,'run',side_effect=ValueError('unreadable')),queue_worker.QueueWorker(self.config,self.store) as worker:
            first=worker.run_once()
        self.store.retry(job)
        with patch.object(queue_worker,'run',side_effect=self.convert),queue_worker.QueueWorker(self.config,self.store) as worker:
            second=worker.run_once()
        self.assertEqual(self.store.get_attempt(first)['state'],'failed')
        attempt=self.store.get_attempt(second)
        self.assertEqual(attempt['state'],'completed',attempt['error'])
        self.assertEqual(attempt['metadata']['region'],'INDIA')
        self.assertEqual(Path(attempt['output_path']).parent,self.config.india_output_dir)

    def test_legacy_settings_preserve_india_and_new_settings_survive_restart(self):
        legacy={key:value for key,value in runtime_settings.editable_settings(self.config).items()
                if key in runtime_settings.LEGACY_SETTINGS_FIELDS}
        legacy['scan_interval_seconds']=3
        self.save(legacy)
        self.assertTrue(self.config.india_enabled)
        saved=runtime_settings.load_runtime_settings(self.config)
        self.assertEqual(saved,self.config)
        (self.config.state_dir/'settings.json').write_text(json.dumps(legacy))
        self.assertEqual(runtime_settings.load_runtime_settings(self.config),self.config)
        changes={**runtime_settings.editable_settings(self.config),'india_enabled':False,
                 'india_incoming_dir':str(self.root/'custom-india-in'),'india_output_dir':str(self.root/'custom-india-out')}
        self.save(changes)
        self.assertFalse(runtime_settings.load_runtime_settings(self.config).india_enabled)
        self.assertTrue(self.config.india_output_dir.is_dir())

    def test_settings_reject_unsafe_paths_country_reassignment_and_removal_with_history(self):
        self.accept();before=self.config
        for changes in ({'india_output_dir':str(ROOT/'templates')},
                        {'india_incoming_dir':'relative'},
                        {'india_incoming_dir':str(self.config.incoming_dir),'incoming_dir':str(self.root/'new-bd')},
                        {'india_enabled':False,'india_incoming_dir':None,'india_output_dir':None}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                self.save({**runtime_settings.editable_settings(self.config),**changes})
            self.assertEqual(self.config,before)

    def test_status_counts_both_inboxes_and_system_exposes_india_controls(self):
        self.source();self.source('INDIA');self.scan(0)
        client=create_app(self.config,update_settings=lambda *args:None).test_client()
        self.assertEqual(client.get('/api/status').get_json()['intake_counts']['waiting_for_file'],2)
        system=client.get('/api/system').get_json()
        self.assertTrue(system['settings']['india_enabled'])
        self.assertEqual(len(system['folders']),6)
        html=client.get('/system').get_data(as_text=True)
        self.assertIn('name="india_enabled"',html);self.assertIn('data-intake-control="jordan"',html)

    def test_clear_archives_both_outputs_and_rediscovery_preserves_country(self):
        self.accept()
        with patch.object(queue_worker,'run',side_effect=self.convert),queue_worker.QueueWorker(self.config,self.store) as worker:
            worker.run_once();worker.run_once()
        outputs={region:(self.config.output_for(region)/'shipment.xlsx').read_bytes() for region in ('BD','INDIA')}
        with patch.object(development_reset,'ROOT',self.root):
            result=development_reset.clear_workspace(self.config,self.store,self.locks,str(uuid4()))
        archive=self.root/result['archive']
        self.assertEqual((archive/'output/shipment.xlsx').read_bytes(),outputs['BD'])
        self.assertEqual((archive/'output-india/shipment.xlsx').read_bytes(),outputs['INDIA'])
        self.assertEqual(self.store.counts()['completed'],0)
        self.scan(100);accepted=self.scan(106)['accepted_job_ids']
        self.assertEqual([self.store.get_job(job)['region'] for job in accepted],['BD','INDIA'])
        self.assertEqual(self.scan(112)['accepted_job_ids'],[])

    def test_india_archive_failure_rolls_back_both_outputs_and_database(self):
        self.accept();(self.config.output_dir/'old.xlsx').write_bytes(b'BD')
        (self.config.india_output_dir/'old.xlsx').write_bytes(b'INDIA')
        rename=Path.rename
        def fail(path,target):
            if path==self.config.india_output_dir:raise PermissionError('India folder locked')
            return rename(path,target)
        with patch.object(development_reset,'ROOT',self.root),patch.object(Path,'rename',fail),self.assertRaises(PermissionError):
            development_reset.clear_workspace(self.config,self.store,self.locks,str(uuid4()))
        self.assertEqual((self.config.output_dir/'old.xlsx').read_bytes(),b'BD')
        self.assertEqual((self.config.india_output_dir/'old.xlsx').read_bytes(),b'INDIA')
        self.assertEqual(self.store.counts()['queued'],2)
        self.assertTrue(self.config.artifact_dir.is_dir())

    def test_development_redirects_india_paths_and_rejects_production_paths(self):
        with patch.object(development_reset,'DEVELOPMENT_ROOT',self.root/'dev'):
            dev=development_reset.development_config(self.config)
            self.assertEqual(dev.india_incoming_dir,self.root/'dev/incoming/india')
            development_reset.validate_development(dev)
            with self.assertRaises(ValueError):
                development_reset.validate_development(replace(dev,india_output_dir=self.config.india_output_dir))

    def test_two_external_output_archives_keep_separate_recovery_records(self):
        import os
        for folder in (self.config.output_dir,self.config.india_output_dir):
            (folder/'old.xlsx').write_bytes(str(folder).encode())
        original=Path.stat
        def separate_volume(path,*args,**kwargs):
            result=original(path,*args,**kwargs)
            if path in (self.config.output_dir,self.config.india_output_dir):
                values=list(result);values[2]=result.st_dev+1
                return os.stat_result(values)
            return result
        with patch.object(development_reset,'ROOT',self.root),patch.object(Path,'stat',separate_volume):
            result=development_reset.clear_workspace(self.config,self.store,self.locks,str(uuid4()))
        archive=self.root/result['archive']
        for name,folder in [('external-output.json',self.config.output_dir),('external-output-india.json',self.config.india_output_dir)]:
            record=json.loads((archive/name).read_text())
            self.assertEqual(record['original'],str(folder))
            self.assertEqual((Path(record['archived'])/'old.xlsx').read_bytes(),str(folder).encode())

    def test_india_manual_edit_keeps_regional_output_and_original_download(self):
        self.source('INDIA');self.scan(0);job=self.scan(6)['accepted_job_ids'][0]
        with patch.object(queue_worker,'run',side_effect=self.convert),queue_worker.QueueWorker(self.config,self.store) as worker:
            old=worker.run_once()
        previous=Path(self.store.get_attempt(old)['output_path']).read_bytes()
        client=create_app(self.config).test_client()
        token=client.get('/api/controls').get_json()['csrf_token']
        response=client.post(f'/api/jobs/{job}/edit',json={'request_id':str(uuid4()),'attempt_id':old,'changes':{'consignee':'EDITED FACTORY'}},
                             headers={'Origin':'http://localhost','X-CSRF-Token':token})
        self.assertEqual(response.status_code,200,response.data)
        with patch.object(queue_worker,'run') as convert,queue_worker.QueueWorker(self.config,self.store) as worker:
            new=worker.run_once()
        convert.assert_not_called()
        attempt=self.store.get_attempt(new)
        self.assertEqual(attempt['state'],'completed',attempt['error'])
        self.assertEqual(Path(attempt['output_path']).parent,self.config.india_output_dir)
        self.assertEqual(client.get(f'/files/attempts/{old}/invoice').data,previous)
        self.assertNotEqual(self.store.get_attempt(old)['output_path'],attempt['output_path'])

    def test_single_launcher_processes_both_countries_and_restarts_without_duplicates(self):
        self.config=replace(self.config,scan_interval_seconds=.03)
        self.source();self.source('INDIA');errors=[]
        def launch(stop):
            try:system_runner.run_system(self.config,port=0,stop=stop)
            except BaseException as exc:errors.append(exc)
        with patch.object(queue_worker,'run',side_effect=self.convert) as convert:
            for _ in range(2):
                stop=threading.Event();thread=threading.Thread(target=launch,args=(stop,));thread.start()
                try:
                    deadline=time.monotonic()+10
                    while self.store.counts()['completed']!=2 and time.monotonic()<deadline and thread.is_alive():time.sleep(.02)
                    self.assertEqual(self.store.counts()['completed'],2)
                    time.sleep(.1)
                finally:
                    stop.set();thread.join(10)
                self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(convert.call_count,2)
        self.assertEqual(sum(self.store.counts().values()),2)


if __name__=='__main__':unittest.main()
