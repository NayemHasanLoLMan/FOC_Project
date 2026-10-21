from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor import dashboard, queue_worker
from src.foc_extractor.dashboard import create_app, _health, _method, _user_summary
from src.foc_extractor.excel_writer import populate_template
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.models import FOCData, LineItem
from src.foc_extractor.pipeline_config import load_config, attempt_metadata
from src.foc_extractor.queue_worker import QueueWorker


class DashboardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        config = self.root/'pipeline_config.json'
        config.write_text((ROOT/'pipeline_config.json').read_text())
        self.config = load_config(config)
        self.store = JobStore(self.config.state_dir/'jobs.sqlite3')
        self.source = self.config.artifact_dir/'inputs/one/shipment.pdf'
        self.source.parent.mkdir(parents=True)
        with pymupdf.open() as pdf:
            pdf.new_page().insert_text((40,40),'SOURCE')
            pdf.save(self.source)
        self.job = self.store.enqueue(self.config.incoming_dir/self.source.name,
            hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source)
        self.app = create_app(self.config)
        self.client = self.app.test_client()

    def convert(self, source, *, template, output_dir, observer, **kwargs):
        observer({'kind':'field_source','field':'invoice_number','value':'S/TEST/26','method':'pdf'})
        observer({'kind':'field_source','field':'export_date','value':'2026-10-07','method':'packing_date'})
        observer({'kind':'invoice_evidence','vision_contributions':[],'unresolved_fields':['net_weight_kg']})
        data = FOCData(source_file=source.name, pages_total=1, pages_processed=1, invoice_number='S/TEST/26',
            export_date='2026-10-07', template_type='BD', items=[LineItem('<script>alert(1)</script>',2,'PCS')])
        path = output_dir/'shipment.xlsx'
        populate_template(template,path,data)
        (output_dir/'shipment.json').write_text(json.dumps(data.to_dict()))
        return path

    def complete(self):
        with patch.object(queue_worker,'run',side_effect=self.convert), QueueWorker(self.config,self.store) as worker:
            return worker.run_once()

    def test_pages_and_empty_and_queued_states_render_without_processing(self):
        before = self.store.path.read_bytes()
        with patch.object(queue_worker,'run') as convert:
            for route in ('/','/jobs','/jobs/1','/system','/api/status','/api/jobs','/api/jobs/1/status'):
                self.assertEqual(self.client.get(route).status_code,200,route)
        convert.assert_not_called()
        self.assertEqual(before,self.store.path.read_bytes())
        self.assertEqual(self.store.counts()['queued'],1)
        self.assertEqual(self.client.get('/api/jobs/999').status_code,404)

    def test_read_only_store_cannot_write_even_through_raw_connection(self):
        reader = self.app.extensions['dashboard_data'].store
        with self.assertRaises(ValueError): reader.retry(self.job)
        with reader._connection() as db:
            with self.assertRaises(sqlite3.OperationalError): db.execute("UPDATE jobs SET state='failed'")
        missing = self.root/'missing'/'jobs.sqlite3'
        with self.assertRaises(FileNotFoundError): JobStore(missing,read_only=True)
        self.assertFalse(missing.parent.exists())

    def test_file_downloads_match_versions_and_data_is_escaped(self):
        attempt = self.complete()
        path = Path(self.store.get_attempt(attempt)['output_path'])
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        invoice = self.client.get(f'/files/attempts/{attempt}/invoice')
        self.assertEqual(invoice.status_code,200)
        self.assertIn('attachment',invoice.headers['Content-Disposition'])
        self.assertEqual(hashlib.sha256(invoice.data).hexdigest(),before)
        self.assertEqual(self.client.get('/files/jobs/1/source').data,self.source.read_bytes())
        page = self.client.get('/jobs/1').get_data(as_text=True)
        self.assertNotIn('<script>alert(1)</script>',page)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',page)
        self.assertNotIn('missing:net_weight_kg',page)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),before)

    def test_plain_detail_hides_developer_records_and_preserves_image_links(self):
        attempt = self.complete()
        page = self.client.get('/jobs/1').get_data(as_text=True)
        main = page.split('<details class="panel technical-details"')[0]
        self.assertIn('The invoice was created and is ready to download.',main)
        self.assertIn('Net weight was left blank because no usable value was established.',main)
        self.assertNotIn('missing:net_weight_kg',main)
        self.assertNotIn('VL lookups',main)
        self.assertNotIn('Source references',main)
        self.assertNotIn('Technical details (optional)',page)
        self.assertNotIn('missing:net_weight_kg',page)
        self.assertNotIn('Stage timeline',page)
        self.assertNotIn('id="technical-details" open',page)
        self.assertIn(f'/files/attempts/{attempt}/invoice',page)

    def test_plain_summaries_do_not_claim_success_or_model_use_without_evidence(self):
        summary = _user_summary(None,'queued')
        self.assertIn('waiting',summary['result'])
        attempt = {'issues':[], 'metadata':{'processing':{'vision_attempts':1,'vision_contributions':[]}}}
        self.assertIn('not used',_user_summary(attempt,'completed')['how'])
        self.assertIn('Saving',_user_summary(attempt,'waiting_to_save')['result'])
        self.assertIn('could not finish',_user_summary(attempt,'failed')['result'])
        attempt['metadata']['processing']['vision_contributions'] = [{'field':'gross_weight_kg'}]
        self.assertIn('helped with gross weight',_user_summary(attempt,'completed')['how'])

    def test_display_names_hide_extension_and_show_recorded_processing_method(self):
        self.complete()
        for route in ('/', '/jobs', '/jobs/1', '/jobs/1/edit'):
            page = self.client.get(route).get_data(as_text=True)
            self.assertNotIn('shipment.pdf', page)
            self.assertIn('shipment', page)
        for route in ('/', '/jobs', '/jobs/1'):
            self.assertIn('Processing: OCR / source rules', self.client.get(route).get_data(as_text=True))
        self.assertEqual(self.client.get('/api/jobs/1').get_json()['job']['filename'], 'shipment.pdf')
        self.assertIn('shipment.pdf', self.client.get('/files/jobs/1/source').headers['Content-Disposition'])
        template = self.app.jinja_env.get_template('job_table.html')
        with self.app.test_request_context():
            page = template.render(listing={'jobs':[{'id':1,'filename':'BATCH.PDF','method':'Vision assisted',
                'state':'completed','attempt_id':1}], 'total':1,'page':1,'pages':1}, filters={})
        self.assertIn('>BATCH</a>', page)
        self.assertIn('Processing: Vision assisted', page)

    def test_reading_explanation_separates_acceptance_from_use_and_keeps_image_urls(self):
        attempt = self.store.claim_next('reader',attempt_metadata(self.config))
        context = {'call_id':'reading-one','field':'package_count','page':1,'original':'pk'}
        for event in [
            {'kind':'vision_request',**context},
            {'kind':'vision_response',**context,'answer':{'text':'1 PK'},'cached':True},
            {'kind':'vision_decision',**context,'candidate':'1 PK','accepted':True},
            {'kind':'invoice_evidence','vision_contributions':[],'unresolved_fields':[]}]:
            self.store.processing_event(attempt['id'],'reader',event)
        detail = self.app.extensions['dashboard_data'].detail(self.job)
        reading = detail['evidence'][0]
        self.assertEqual(reading['reading'],'1 PK')
        self.assertTrue(reading['saved'])
        self.assertIn('accepted, but did not produce',reading['outcome'])
        page = self.client.get('/jobs/1').get_data(as_text=True)
        self.assertIn('Image reader found:</strong> 1 PK',page)
        self.assertIn('/images/jobs/1/events/',page)
        self.assertIn('/images/jobs/1/pages/1?event=',page)
        self.assertIn('A saved reading of the same image was reused.',page)

    def test_filters_pagination_and_today_counts_distinguish_attempts(self):
        self.complete()
        for number in range(27):
            self.store.enqueue(self.config.incoming_dir/f'{number}.pdf',f'{number:064x}',self.config.artifact_dir/'inputs'/f'{number}.pdf')
        page = self.client.get('/api/jobs').get_json()
        self.assertEqual((page['total'],len(page['jobs']),page['pages']),(28,25,2))
        self.assertEqual(len(self.client.get('/api/jobs?page=2').get_json()['jobs']),3)
        for query in ('q=S%2FTEST','date=2026-10-07','status=completed','issues=yes'):
            self.assertEqual(self.client.get('/api/jobs?'+query).get_json()['total'],1,query)
        self.assertEqual(self.client.get('/api/jobs?issues=no').get_json()['total'],27)
        self.assertEqual(self.client.get('/api/jobs?q=%27%20OR%201%3D1--').get_json()['total'],0)
        status = self.client.get('/api/status').get_json()
        self.assertEqual((status['today']['received'],status['today']['completed'],status['attempts']),(28,1,1))
        self.assertEqual(status['completed_with_issues'],1)

    def test_invalid_filters_and_foreign_attempts_are_rejected(self):
        for query in ('status=madeup','issues=maybe','page=0','page=no','date=wrong'):
            self.assertEqual(self.client.get('/jobs?'+query).status_code,400,query)
        self.complete()
        self.assertEqual(self.client.get('/jobs/1?attempt=999').status_code,404)
        self.assertEqual(self.client.get('/files/attempts/999/invoice').status_code,404)

    def test_methods_do_not_equate_cache_reuse_or_unknown_history_with_ocr_only(self):
        self.assertEqual(_method({'metadata':{}}),'Not recorded')
        self.assertEqual(_method({'metadata':{'processing':{'vision_attempts':0,'vision_contributions':[{'field':'weight'}]}}}),'Vision assisted')
        self.assertIn('no final contribution',_method({'metadata':{'processing':{'vision_attempts':1,'vision_contributions':[]}}}))

    def test_stale_heartbeat_and_service_health_are_separate_from_web(self):
        old = (datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
        self.assertEqual(_health({'state':'running','heartbeat_at':old},30)['state'],'unknown')
        self.store.component('worker','worker',1,'running')
        with self.store._connection(write=True) as db: db.execute("UPDATE components SET heartbeat_at=?",(old,))
        status = self.client.get('/api/status').get_json()
        self.assertEqual((status['web'],status['worker']['state'],status['scanner']['state']),('available','unknown','unknown'))

    def test_ollama_is_bounded_cached_and_never_generates(self):
        response = unittest.mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'models':[{'name':self.config.local_model,'digest':'abc'}]}).encode()
        with patch.object(dashboard.urllib.request,'urlopen',return_value=response) as probe:
            self.assertEqual(self.client.get('/api/ollama').get_json()['state'],'available')
            self.client.get('/api/ollama')
        self.assertEqual(probe.call_count,1)
        self.assertEqual(probe.call_args.kwargs['timeout'],2)
        self.assertTrue(probe.call_args.args[0].endswith('/api/tags'))

    def test_output_tampering_and_outside_paths_are_not_served(self):
        attempt = self.complete()
        path = Path(self.store.get_attempt(attempt)['output_path'])
        path.write_bytes(b'tampered')
        self.assertEqual(self.client.get(f'/files/attempts/{attempt}/invoice').status_code,409)
        with self.store._connection(write=True) as db: db.execute('UPDATE attempts SET output_path=? WHERE id=?',(str(self.source),attempt))
        self.assertEqual(self.client.get(f'/files/attempts/{attempt}/invoice').status_code,409)
        self.source.write_bytes(b'changed')
        self.assertEqual(self.client.get('/files/jobs/1/source').status_code,409)
        self.assertEqual(self.client.get('/files?path=C:/Windows/win.ini').status_code,404)

    def test_unknown_and_corrupt_evidence_have_safe_errors(self):
        self.complete()
        self.assertEqual(self.client.get('/images/jobs/1/events/999').status_code,404)
        self.assertEqual(self.client.get('/images/jobs/1/pages/1').status_code,404)
        self.assertNotIn(str(self.root),self.client.get('/images/jobs/1/events/999').get_data(as_text=True))

    def test_local_only_and_mutations_are_rejected_with_security_headers(self):
        self.assertEqual(self.client.get('/',headers={'Host':'evil.example'}).status_code,400)
        self.assertEqual(self.client.get('/',headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.client.get('/',headers={'Sec-Fetch-Site':'cross-site'}).status_code,403)
        self.assertEqual(self.client.get('/',environ_overrides={'REMOTE_ADDR':'10.0.0.2'}).status_code,403)
        self.assertEqual(self.client.post('/api/jobs/1/status').status_code,405)
        headers = self.client.get('/').headers
        self.assertEqual(headers['X-Content-Type-Options'],'nosniff')
        self.assertIn("object-src 'none'",headers['Content-Security-Policy'])

    def test_preview_limit_does_not_block_status_requests(self):
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        def slow(*args,**kwargs):
            entered.set(); release.wait(5); return b'png'
        def preview():
            with self.app.test_client() as client: return client.get('/images/jobs/1/pages/1').status_code
        with patch.object(dashboard,'page_preview',side_effect=slow),ThreadPoolExecutor(max_workers=3) as pool:
            one = pool.submit(preview)
            self.assertTrue(entered.wait(2))
            two = pool.submit(preview)
            time.sleep(.05)
            started = time.monotonic()
            self.assertEqual(self.client.get('/api/status').status_code,200)
            self.assertLess(time.monotonic()-started,1)
            self.assertEqual(self.client.get('/images/jobs/1/pages/1').status_code,429)
            release.set()
            self.assertEqual((one.result(),two.result()),(200,200))

    def test_status_stays_responsive_during_real_worker_wait(self):
        entered = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        def busy(source,**kwargs):
            kwargs['observer']({'kind':'stage','stage':'weights','status':'started'})
            entered.set(); release.wait(5)
            return self.convert(source,**kwargs)
        def work():
            with QueueWorker(self.config,self.store) as worker: worker.run_once()
        with patch.object(queue_worker,'run',side_effect=busy),ThreadPoolExecutor(max_workers=1) as pool:
            worker = pool.submit(work)
            self.assertTrue(entered.wait(2))
            started = time.monotonic()
            status = self.client.get('/api/status').get_json()
            self.assertLess(time.monotonic()-started,1)
            self.assertEqual((status['worker']['state'],status['active']['stage']),('running','weights'))
            self.assertIsNotNone(status['active']['stage_seconds'])
            release.set(); worker.result()
        self.assertEqual(self.client.get('/api/status').get_json()['counts']['completed'],1)


if __name__=='__main__': unittest.main()
