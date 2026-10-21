from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import test_dashboard as fixtures
from src.foc_extractor import queue_worker
from src.foc_extractor.invoice_edits import validate_changes, edited_data
from src.foc_extractor.job_store import JobStore,SCHEMA_VERSION
from src.foc_extractor.queue_worker import QueueWorker


class InvoiceEditTests(unittest.TestCase):
    def setUp(self):
        fixtures.DashboardTests.setUp(self)
        self.headers={'Origin':'http://localhost','X-CSRF-Token':self.client.get('/api/controls').get_json()['csrf_token']}

    convert=fixtures.DashboardTests.convert
    complete=fixtures.DashboardTests.complete

    def submit(self,attempt,changes,request_id=None):
        return self.client.post(f'/api/jobs/{self.job}/edit',headers=self.headers,
            json={'request_id':request_id or str(uuid4()),'attempt_id':attempt,'changes':changes})

    def process_edit(self):
        with patch.object(queue_worker,'run') as converter,QueueWorker(self.config,self.store) as worker:
            attempt=worker.run_once()
        converter.assert_not_called()
        self.assertEqual(self.store.get_attempt(attempt)['state'],'completed',self.store.get_attempt(attempt)['error'])
        return attempt

    def test_edit_adds_missing_information_and_preserves_old_invoice_without_ocr(self):
        old=self.complete();path=Path(self.store.get_attempt(old)['output_path']);digest=hashlib.sha256(path.read_bytes()).hexdigest()
        receipt=Path(self.store.get_attempt(old)['receipt_path']);original_receipt=receipt.read_bytes()
        response=self.submit(old,{'tin_number':'123-4567','import_cover_note':'User supplied reference','consignee':'Changed consignee'})
        self.assertEqual(response.status_code,200,response.data)
        new=self.process_edit()
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
        self.assertEqual(receipt.read_bytes(),original_receipt)
        self.assertNotEqual(str(path),self.store.get_attempt(new)['output_path'])
        detail=self.client.get(f'/api/jobs/{self.job}').get_json()
        self.assertEqual(detail['data']['tin_number'],'123-4567')
        self.assertEqual(detail['data']['consignee'],'Changed consignee')
        self.assertEqual(detail['method'],'Manually edited')
        self.assertEqual(detail['attempt']['metadata']['manual_edit']['base_attempt_id'],old)
        self.assertEqual(self.client.get(f'/files/attempts/{old}/invoice').status_code,200)
        self.assertEqual(self.client.get(f'/files/attempts/{new}/invoice').status_code,200)

    def test_replays_and_stale_versions_cannot_create_duplicate_work(self):
        old=self.complete();request_id=str(uuid4());changes={'tin_number':'123-4567'}
        first=self.submit(old,changes,request_id)
        self.assertEqual(first.status_code,200)
        new=self.process_edit()
        self.assertEqual(self.submit(old,changes,request_id).get_json(),first.get_json())
        self.assertEqual(self.submit(old,changes).status_code,409)
        self.assertEqual(self.submit(old,{'tin_number':'999-9999'},request_id).status_code,409)
        self.assertEqual(len(self.store.attempts(self.job)),2)
        self.assertEqual(self.store.get_attempt(new)['state'],'completed')

    def test_invalid_values_and_protected_fields_never_queue_an_edit(self):
        old=self.complete()
        for changes in [{'source_file':'other.pdf'},{'gross_weight_kg':-1},{'total_value':'NaN'},
                        {'package_count':1.5},{'export_date':'2026-02-30'},{'net_weight_kg':2},
                        {'items':[{'description':'Bad'}]},{'consignee':'x'*2001},{}]:
            with self.subTest(changes=repr(changes)[:80]):
                self.assertEqual(self.submit(old,changes).status_code,400)
        self.assertEqual(self.store.get_job(self.job)['state'],'completed')
        self.assertEqual(len(self.store.attempts(self.job)),1)
        self.assertEqual(self.client.post(f'/api/jobs/{self.job}/edit',json={}).status_code,403)

    def test_goods_decimal_math_blank_values_and_source_attribution(self):
        original={'source_file':'new.pdf','template_type':'BD','total_value':80,
                  'items':[{'description':'FABRIC','quantity':2,'unit':'YDS','unit_price':1,'source_refs':['page:1:row:1'],'source_page':1}]}
        row={'source_index':0,'description':'MANUAL FABRIC','quantity':'3','unit':'YDS','unit_price':'0.335'}
        data=edited_data(original,{'items':[row]})
        self.assertEqual((data.items[0].amount,data.total_value),(1.01,1))
        self.assertEqual(data.items[0].source_refs,[])
        self.assertIsNone(data.items[0].source_page)
        self.assertEqual(original['items'][0]['description'],'FABRIC')
        self.assertEqual(edited_data(original,{'items':[row],'total_value':9}).total_value,9)
        row['unit_price']=''
        data=edited_data(original,{'items':[row]})
        self.assertIsNone(data.items[0].amount);self.assertIsNone(data.total_value)
        with self.assertRaises(ValueError):edited_data(original,{'items':[{**row,'source_index':10}]})

    def test_locked_save_retries_prepared_edit_without_creating_another_attempt(self):
        old=self.complete();self.assertEqual(self.submit(old,{'tin_number':'123-4567'}).status_code,200)
        with patch.object(queue_worker,'run') as converter,QueueWorker(self.config,self.store) as worker:
            with patch.object(queue_worker,'_publish_copy',side_effect=PermissionError('Locked')):
                new=worker.run_once()
            self.assertEqual(self.store.get_attempt(new)['state'],'waiting_to_save')
            worker.run_once()
            self.assertEqual(self.store.get_attempt(new)['state'],'completed')
        converter.assert_not_called();self.assertEqual(len(self.store.attempts(self.job)),2)

    def test_restart_recovers_an_interrupted_manual_edit_without_ocr(self):
        old=self.complete();self.assertEqual(self.submit(old,{'tin_number':'123-4567'}).status_code,200)
        with QueueWorker(self.config,self.store) as worker:
            from src.foc_extractor.pipeline_config import attempt_metadata
            metadata=attempt_metadata(self.config);metadata['worker_lock']=str(worker.lock_path)
            interrupted=self.store.claim_next(worker.owner,metadata)
        new=self.process_edit()
        self.assertEqual(self.store.get_attempt(interrupted['id'])['state'],'interrupted')
        self.assertEqual(self.store.get_attempt(new)['metadata']['manual_edit']['base_attempt_id'],old)

    def test_schema_four_migration_keeps_existing_invoices(self):
        old=self.complete()
        with closing(sqlite3.connect(self.store.path)) as db,db:
            db.execute('ALTER TABLE jobs DROP COLUMN manual_edit_json');db.execute('PRAGMA user_version=4')
        migrated=JobStore(self.store.path)
        self.assertEqual(migrated.get_attempt(old)['state'],'completed')
        with migrated._connection() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],SCHEMA_VERSION)

    def test_original_image_readings_remain_available_after_two_edits(self):
        def convert(source,**kwargs):
            for event in [
                {'kind':'vision_request','call_id':'read1','field':'package_count','page':1,'original':'pk'},
                {'kind':'vision_response','call_id':'read1','field':'package_count','page':1,'cached':True,'answer':{'text':'1 PK'}},
                {'kind':'vision_decision','call_id':'read1','field':'package_count','page':1,'accepted':True,'candidate':'1 PK'}]:kwargs['observer'](event)
            return self.convert(source,**kwargs)
        with patch.object(queue_worker,'run',side_effect=convert),QueueWorker(self.config,self.store) as worker:old=worker.run_once()
        self.assertEqual(self.submit(old,{'tin_number':'123-4567'}).status_code,200);first=self.process_edit()
        self.assertEqual(self.submit(first,{'tin_number':'234-5678'}).status_code,200);self.process_edit()
        detail=self.client.get(f'/api/jobs/{self.job}').get_json()
        self.assertEqual(len(detail['evidence']),1)
        self.assertEqual(detail['evidence'][0]['reading'],'1 PK')
        self.assertTrue(detail['evidence'][0]['outcome'].startswith('Original reading:'))
        page=self.client.get(f'/jobs/{self.job}').get_data(as_text=True)
        self.assertIn('/images/jobs/1/events/',page)
        self.assertNotIn('Technical details for this reading',page)

    def test_editor_links_and_simplified_jobs_render_and_raw_records_stay_offscreen(self):
        self.assertEqual(self.client.get(f'/jobs/{self.job}/edit').status_code,409)
        self.complete()
        page=self.client.get(f'/jobs/{self.job}/edit').get_data(as_text=True)
        self.assertIn('Save new invoice version',page);self.assertIn('Import cover note',page)
        self.assertIn('TIN',page)
        self.assertNotIn('<script>alert(1)</script>',page)
        listing=self.client.get('/jobs').get_data(as_text=True)
        self.assertIn('>View</a>',listing);self.assertIn('>Edit</a>',listing);self.assertIn('>Download</a>',listing)
        self.assertNotIn('<th>Processing method</th>',listing)

    def test_changed_and_added_goods_are_written_with_calculated_amounts(self):
        old=self.complete()
        rows=[{'source_index':0,'description':'=1+1','quantity':'3','unit':'PCS','unit_price':'0.335'},
              {'source_index':None,'description':'ADDED FABRIC','quantity':'2','unit':'YDS','unit_price':'1.25'}]
        response=self.submit(old,{'items':rows,'tin_number':''})
        self.assertEqual(response.status_code,200,response.data)
        new=self.process_edit();detail=self.client.get(f'/api/jobs/{self.job}').get_json()
        self.assertEqual([i['amount'] for i in detail['data']['items']],[1.01,2.5])
        self.assertEqual(detail['data']['total_value'],4)
        import openpyxl
        book=openpyxl.load_workbook(self.store.get_attempt(new)['output_path'])
        self.assertEqual(book.active['B33'].value,'=1+1');self.assertEqual(book.active['B33'].data_type,'s');book.close()

    def test_failed_edit_transaction_keeps_previous_job_and_pending_data(self):
        old=self.complete()
        with patch.object(self.store,'_event',side_effect=OSError('Audit failed')):
            with self.assertRaises(OSError):
                self.store.admin_command(str(uuid4()),'edit',job_id=self.job,attempt_id=old,changes={'tin_number':'123-4567'})
        self.assertEqual(self.store.get_job(self.job)['state'],'completed')
        self.assertIsNone(self.store.get_job(self.job)['manual_edit_json'])


if __name__=='__main__':unittest.main()
