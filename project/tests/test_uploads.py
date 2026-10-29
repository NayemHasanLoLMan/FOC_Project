"""Web uploads use normal validated country intake and never overwrite PDFs."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from werkzeug.datastructures import MultiDict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.dashboard import create_app
from src.foc_extractor.folder_intake import FolderScanner
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.pipeline_config import PipelineConfig,initialize_folders


class UploadTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name).resolve()
        self.config=PipelineConfig(self.root/'incoming/bangladesh',self.root/'output/bangladesh',
            self.root/'state',self.root/'artifacts',5,None,india_enabled=True,jordan_enabled=True,
            india_incoming_dir=self.root/'incoming/india',india_output_dir=self.root/'output/india',
            jordan_incoming_dir=self.root/'incoming/jordan',jordan_output_dir=self.root/'output/jordan')
        initialize_folders(self.config);self.store=JobStore(self.config.state_dir/'jobs.sqlite3')
        self.app=create_app(self.config);self.client=self.app.test_client()
        self.headers={'Origin':'http://localhost','X-CSRF-Token':self.client.get('/api/controls').get_json()['csrf_token']}
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40,40),'UPLOAD PROBE');self.pdf=pdf.tobytes()

    def post(self,region='BD',name='new.pdf',content=None,client=None,headers=None):
        return (client or self.client).post('/api/uploads',headers=self.headers if headers is None else headers,
            data={'region':region,'file':(io.BytesIO(self.pdf if content is None else content),name)},content_type='multipart/form-data')

    def assert_empty(self):
        self.assertFalse(any((self.root/'incoming').rglob('*.*')))
        self.assertEqual(self.store.counts()['queued'],0)

    def test_three_countries_join_existing_scanner_queue_without_models(self):
        with patch('src.foc_extractor.queue_worker.run') as converter:
            for region,folder in self.config.inboxes().items():
                response=self.post(region,name=region+'.PDF')
                self.assertEqual(response.status_code,201,response.data)
                result=response.get_json();self.assertEqual(result['status'],'waiting_for_intake')
                self.assertEqual((folder/(region+'.PDF')).read_bytes(),self.pdf)
                self.assertIn('region='+region,result['jobs_url'])
            self.assertEqual(self.store.counts()['queued'],0)
            scanner=FolderScanner(self.config,self.store)
            with patch('src.foc_extractor.folder_intake.time.time',return_value=0):scanner.scan_once()
            with patch('src.foc_extractor.folder_intake.time.time',return_value=6):result=scanner.scan_once()
            self.assertEqual(len(result['accepted_job_ids']),3,result)
            self.assertEqual({self.store.get_job(i)['region'] for i in result['accepted_job_ids']},{'BD','INDIA','JORDAN'})
            converter.assert_not_called()

    def test_duplicate_and_concurrent_uploads_do_not_overwrite(self):
        first=self.post();self.assertEqual(first.status_code,201)
        second=self.post(content=self.pdf+b'\n')
        self.assertEqual(second.status_code,409)
        self.assertEqual((self.config.incoming_dir/'new.pdf').read_bytes(),self.pdf)
        def send(_):
            with self.app.test_client() as client:return self.post(name='race.pdf',client=client).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(send,range(2)))
        self.assertEqual(sorted(codes),[201,409])
        self.assertEqual(sorted(p.name for p in self.config.incoming_dir.iterdir()),['new.pdf','race.pdf'])

    def test_invalid_pdf_names_and_passwords_leave_no_files(self):
        for name in ('../outside.pdf','C:\\outside.pdf','CON.pdf','notes.txt','file.pdf:stream.pdf','x'*201+'.pdf'):
            response=self.post(name=name);self.assertEqual(response.status_code,400,(name,response.data));self.assert_empty()
        for content in (b'',b'not a pdf %%EOF',self.pdf[:-30]):
            self.assertEqual(self.post(content=content).status_code,400);self.assert_empty()
        with pymupdf.open() as pdf:
            pdf.new_page();encrypted=pdf.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256,owner_pw='owner',user_pw='secret')
        self.assertEqual(self.post(content=encrypted).status_code,400);self.assert_empty()

    def test_valid_unicode_filename_is_preserved(self):
        response=self.post(name='বাংলা invoice.pdf');self.assertEqual(response.status_code,201,response.data)
        self.assertEqual((self.config.incoming_dir/'বাংলা invoice.pdf').read_bytes(),self.pdf)

    def test_country_and_form_validation_and_disabled_intake(self):
        self.assertEqual(self.post('OTHER').status_code,400);self.assert_empty()
        self.app.extensions['dashboard_data'].config=replace(self.config,india_enabled=False)
        self.assertEqual(self.post('INDIA').status_code,409);self.assert_empty()
        self.assertIn('India — intake disabled',self.client.get('/upload').get_data(as_text=True))
        for data in ({'file':(io.BytesIO(self.pdf),'a.pdf')},{'region':'BD'},
                     MultiDict([('region','BD'),('region','INDIA'),('file',(io.BytesIO(self.pdf),'a.pdf'))]),
                     MultiDict([('region','BD'),('file',(io.BytesIO(self.pdf),'a.pdf')),('file',(io.BytesIO(self.pdf),'b.pdf'))])):
            self.assertEqual(self.client.post('/api/uploads',headers=self.headers,data=data,content_type='multipart/form-data').status_code,400)
            self.assert_empty()

    def test_size_limits_csrf_localhost_and_existing_json_guards(self):
        with patch('src.foc_extractor.uploads.MAX_UPLOAD_BYTES',len(self.pdf)-1):
            self.assertEqual(self.post().status_code,413);self.assert_empty()
        with patch('src.foc_extractor.dashboard.MAX_UPLOAD_BYTES',1024):
            self.assertEqual(self.post(content=b'x'*(2*1024*1024)).status_code,413);self.assert_empty()
        self.assertEqual(self.post(headers={'Origin':'http://localhost'}).status_code,403);self.assert_empty()
        self.assertEqual(self.post(headers={**self.headers,'Origin':'http://evil.example'}).status_code,403);self.assert_empty()
        response=self.client.post('/api/uploads',headers=self.headers,data={'region':'BD'},environ_overrides={'REMOTE_ADDR':'10.0.0.8'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.client.post('/api/uploads',headers=self.headers,json={'region':'BD'}).status_code,415)
        self.assertEqual(self.client.post('/api/queue/pause',headers=self.headers,data={'test':'x'},content_type='multipart/form-data').status_code,415)
        self.assertEqual(self.client.post('/api/queue/pause',headers={**self.headers,'Content-Type':'application/json'},data=b'x'*65537).status_code,413)

    def test_paused_queue_dynamic_folder_and_storage_failure(self):
        self.store.admin_command('00000000-0000-4000-8000-000000000003','pause')
        folder=self.root/'selected/bangladesh'
        self.app.extensions['dashboard_data'].config=replace(self.config,incoming_dir=folder)
        self.assertEqual(self.post().status_code,201)
        self.assertTrue((folder/'new.pdf').is_file());self.assertTrue(self.store.queue_control()['paused'])
        self.assertFalse(any(self.config.incoming_dir.iterdir()))
        with patch('src.foc_extractor.uploads._validate_pdf',side_effect=OSError('unavailable')):
            self.assertEqual(self.post(name='error.pdf').status_code,503)
        self.assertEqual([p.name for p in folder.iterdir()],['new.pdf'])

    def test_upload_links_and_country_choice_are_visible(self):
        for route in ('/','/jobs'):
            self.assertIn('href="/upload"',self.client.get(route).get_data(as_text=True))
        response=self.client.get('/upload');self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        for text in ('Choose a country','Bangladesh','India','Jordan','type="file"','100 MB'):
            self.assertIn(text,html)
        self.assertIn('PDF uploaded.',self.client.get('/jobs?uploaded=1').get_data(as_text=True))


if __name__=='__main__':unittest.main()
