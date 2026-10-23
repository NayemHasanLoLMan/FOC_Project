"""Regional detail presentation must preserve invoice facts and original image review."""
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from flask import render_template
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import test_india_edits as fixtures
from src.foc_extractor import queue_worker
from src.foc_extractor.dashboard import _public,_user_summary
from src.foc_extractor.excel_writer import populate_template
from src.foc_extractor.queue_worker import QueueWorker


class IndiaDetailTests(unittest.TestCase):
    setUp=fixtures.IndiaEditTests.setUp
    submit=fixtures.IndiaEditTests.submit
    process_edit=fixtures.IndiaEditTests.process_edit
    rows=fixtures.IndiaEditTests.rows

    def complete(self):
        image=io.BytesIO();Image.new('RGB',(80,40),'white').save(image,format='PNG');self.png=image.getvalue()
        def convert(source,*,template,output_dir,observer,**kwargs):
            observer({'kind':'ocr_document','document':{'pages':['SOURCE'],'page_transforms':[{'rotation':0,'skew':0}],'dpi':72}})
            observer({'kind':'vision_request','call_id':'address','field':'consignee_address','page':1,'bbox':[10,10,50,40]},png=self.png)
            observer({'kind':'vision_response','call_id':'address','field':'consignee_address','page':1,'cached':True,'answer':{'text':'ORIGINAL ROAD'}})
            observer({'kind':'vision_decision','call_id':'address','field':'consignee_address','page':1,'accepted':False})
            observer({'kind':'invoice_evidence','vision_contributions':[],'unresolved_fields':['net_weight_kg']})
            target=output_dir/'india.xlsx';populate_template(template,target,self.original)
            (output_dir/'india.json').write_text(json.dumps(self.original.to_dict()))
            return target
        with patch.object(queue_worker,'run',side_effect=convert),QueueWorker(self.config,self.store) as worker:
            attempt=worker.run_once()
        self.assertEqual(self.store.get_attempt(attempt)['state'],'completed',self.store.get_attempt(attempt)['error'])
        return attempt

    def test_india_details_show_invoice_headers_hs_and_money_without_bd_or_net_fields(self):
        self.original.port_of_discharge='SOURCE PORT';self.original.shipment_terms='FOB';self.original.net_weight_kg=3.5
        self.original.tin_number='UNPRINTED TIN';self.original.import_cover_note='UNPRINTED NOTE'
        self.complete();page=self.client.get('/jobs/1').get_data(as_text=True)
        for label,value in [('Address / IEC / PAN / GST','ORIGINAL ROAD'),('Destination country','India'),
                            ('Destination city','NEW CITY, INDIA'),('Carton references','T01-T02'),
                            ('Port of discharge','SOURCE PORT'),('Shipment terms','FOB')]:
            self.assertIn(f'<dt>{label}</dt>',page);self.assertIn(value,page)
        for value in ('<th>HS code</th>','00123456','Total (USD)','Unit value (USD)','Item value (USD)','use cents'):
            self.assertIn(value,page)
        for value in ('Address / BIN','Net weight','<dt>TIN</dt>','UNPRINTED TIN','UNPRINTED NOTE'):
            self.assertNotIn(value,page)
        self.assertEqual(self.client.get('/api/jobs/1').get_json()['data']['net_weight_kg'],3.5)

    def test_blank_zero_and_escaped_source_values_stay_distinct(self):
        self.original.package_count=0;self.original.gross_weight_kg=0;self.original.total_value=0
        self.original.carton_range=None;self.original.destination_city=None
        self.original.items[0].hs_code='<b>0001</b>';self.original.items[0].description='<script>bad</script>'
        self.original.items[1].hs_code=None;self.complete()
        page=self.client.get('/jobs/1').get_data(as_text=True)
        for label in ('Port of discharge','Shipment terms','Carton references','Destination city'):
            self.assertIn(f'<dt>{label}</dt><dd>—</dd>',page)
        self.assertIn('<dt>Packages</dt><dd>0</dd>',page);self.assertIn('<dt>Total (USD)</dt><dd>0</dd>',page)
        self.assertIn('&lt;b&gt;0001&lt;/b&gt;',page);self.assertIn('&lt;script&gt;bad&lt;/script&gt;',page)
        self.assertNotIn('<script>bad</script>',page)

    def test_currency_labels_follow_saved_india_data_instead_of_fixed_usd(self):
        self.complete();app=self.client.application
        view=app.extensions['dashboard_data'].detail(1)
        # EUR cannot be published by the current writer; this isolates display of a retained currency.
        for currency in ('USD','EUR'):
            view['data']['currency']=currency
            with app.test_request_context('/jobs/1'):
                page=render_template('detail.html',**_public(view))
            for label in ('Total','Unit value','Item value'):self.assertIn(f'{label} ({currency})',page)
            if currency=='EUR':self.assertNotIn('(USD)',page)

    def test_old_and_new_versions_show_their_own_values_and_keep_original_images(self):
        old=self.complete();rows=self.rows();rows[0]['hs_code']='00000001'
        response=self.submit(old,{'items':rows,'port_of_discharge':'USER PORT','shipment_terms':'CPT'})
        self.assertEqual(response.status_code,200);new=self.process_edit()
        current=self.client.get('/jobs/1').get_data(as_text=True)
        previous=self.client.get(f'/jobs/1?attempt={old}').get_data(as_text=True)
        self.assertIn('USER PORT',current);self.assertIn('00000001',current)
        self.assertNotIn('USER PORT',previous);self.assertIn('00123456',previous)
        self.assertIn('Original reading:',current);self.assertIn('Image readings',current)
        self.assertIn('Consignee address / IEC / PAN / GST',current)
        event=next(e for e in self.store.events(1) if e['details'].get('kind')=='vision_request')
        self.assertEqual(self.client.get(f'/images/jobs/1/events/{event["id"]}').data,self.png)
        self.assertEqual(self.client.get(f'/images/jobs/1/pages/1?event={event["id"]}').status_code,200)
        for attempt in (old,new):self.assertEqual(self.client.get(f'/files/attempts/{attempt}/invoice').status_code,200)

    def test_irrelevant_net_weight_notes_are_hidden_only_for_india(self):
        attempt={'metadata':{'region':'INDIA'},'issues':['missing:net_weight_kg','missing:consignee_address','missing:goods:1:hs_code']}
        summary=_user_summary(attempt,'completed')
        self.assertEqual(len(summary['notes']),2);self.assertIn('IEC / PAN / GST',summary['notes'][0]);self.assertIn('HS code',summary['notes'][1])
        attempt['metadata']['manual_edit']={'base_attempt_id':1}
        self.assertFalse(any('Net weight' in note for note in _user_summary(attempt,'completed')['notes']))
        attempt['metadata']={}
        self.assertTrue(any('Net weight' in note for note in _user_summary(attempt,'completed')['notes']))
        self.assertTrue(any('address / BIN' in note for note in _user_summary(attempt,'completed')['notes']))

    def test_queued_and_unavailable_data_remain_safe_and_read_only(self):
        before=self.store.path.read_bytes()
        self.assertEqual(self.client.get('/jobs/1').status_code,200);self.assertEqual(self.store.path.read_bytes(),before)
        attempt=self.complete();record=self.store.get_attempt(attempt);invoice=Path(record['output_path']);original=invoice.read_bytes()
        for url in ('/jobs/1','/api/jobs/1',f'/invoices/attempts/{attempt}'):
            self.assertEqual(self.client.get(url).status_code,200)
        self.assertEqual(invoice.read_bytes(),original)
        receipt=Path(record['receipt_path']);ready=json.loads(receipt.read_text());data=receipt.parent/ready['data_name']
        data.write_text('tampered')
        page=self.client.get('/jobs/1').get_data(as_text=True)
        self.assertIn('could not be opened or verified',page);self.assertNotIn('<th>HS code</th>',page)
