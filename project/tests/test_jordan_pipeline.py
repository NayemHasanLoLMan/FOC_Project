"""Jordan activation uses the existing scanner, converter, publication and edit flow."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor.dashboard import create_app
from src.foc_extractor.folder_intake import FolderScanner
from src.foc_extractor.invoice_edits import edited_data, validate_changes
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell
from src.foc_extractor.pipeline_config import initialize_folders, load_config
from src.foc_extractor.queue_worker import QueueWorker
from src.foc_extractor.runtime_settings import editable_settings, settings_config, save_runtime_settings


class JordanPipelineTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        config_path = self.root/'pipeline_config.json'
        config_path.write_bytes((ROOT/'pipeline_config.json').read_bytes())
        base = load_config(config_path)
        self.config = settings_config(base, {
            **editable_settings(base), 'local_model':None, 'bangladesh_enabled':False,
            'jordan_enabled':True, 'jordan_incoming_dir':str(self.root/'incoming/jordan'),
            'jordan_output_dir':str(self.root/'output/jordan')})
        initialize_folders(self.config)
        self.store = JobStore(self.config.state_dir/'jobs.sqlite3')

    def test_jordan_source_to_invoice_preview_edit_and_country_output(self):
        cover = ('SHIPPER\nS/9001/26\nCONSIGNEE:\nNEW JORDAN CUSTOMER\nNEW ROAD\nAMMAN, JORDAN\n'
                 'DESTINATION AIRPORT / PLACE: AMMAN\nMARKS & NOS: No. and Kind of Packages\n'
                 '1 PACKAGE APP. 2 KGS\nNEWFOC\nJORDAN\nC/NO. J01\nWAREHOUSE ADDRESS:')
        packing = 'PACKING LIST\nDATE: 20-Oct-2026\nCARE LABEL 10 PCS 2 KG CHINA'
        source = self.config.jordan_incoming_dir/'unseen-D.pdf'
        with pymupdf.open() as pdf:
            for text in (cover,packing):pdf.new_page().insert_text((40,40),text)
            pdf.save(source)
        original = source.read_bytes()
        scanner = FolderScanner(self.config,self.store)
        with patch('src.foc_extractor.folder_intake.time.time',return_value=0):scanner.scan_once()
        with patch('src.foc_extractor.folder_intake.time.time',return_value=6):
            jobs = scanner.scan_once()['accepted_job_ids']
        self.assertEqual(len(jobs),1)
        job_id = jobs[0]
        self.assertEqual(self.store.get_job(job_id)['region'],'JORDAN')
        rows = [['PARTICULARS','QTY','WEIGHT / KGS','COO'],['CARE LABEL','10 PCS','2 KG','CHINA']]
        cells = [OCRTableCell(r,c,text,page=1,bbox=[c*150,r*60,c*150+150,r*60+60])
                 for r,row in enumerate(rows) for c,text in enumerate(row)]
        ocr = OCRResult(content=cover+'\n'+packing,pages=[cover,packing],total_pages=2,
                        backend='test',tables=[OCRTable(cells,2,4,page=1,bbox=[0,0,600,120])])
        with patch('src.foc_extractor.pipeline.analyze_pdf',return_value=ocr), QueueWorker(self.config,self.store) as worker:
            attempt_id = worker.run_once()
        attempt = self.store.get_attempt(attempt_id)
        self.assertEqual(attempt['state'],'completed',attempt['error'])
        self.assertEqual(Path(attempt['output_path']).parent,self.config.jordan_output_dir)
        receipt = Path(attempt['receipt_path'])
        ready = json.loads(receipt.read_text(encoding='utf-8'))
        data = json.loads((receipt.parent/ready['data_name']).read_text(encoding='utf-8'))
        self.assertEqual((data['invoice_number'],data['package_count'],data['gross_weight_kg']),('S/9001/26',1,2))
        self.assertEqual(data['items'][0]['origin_country'],'CHINA')
        self.assertEqual(data['total_value'],1)
        client = create_app(self.config).test_client()
        for route in (f'/jobs/{job_id}',f'/jobs/{job_id}/edit',f'/invoices/attempts/{attempt_id}',
                      f'/files/attempts/{attempt_id}/invoice', '/api/jobs?region=JORDAN'):
            self.assertEqual(client.get(route).status_code,200,route)
        changes = validate_changes({'items':[{'source_index':0,'description':data['items'][0]['description'],
            'quantity':10,'unit':'PCS','unit_price':0.001,'origin_country':'Vietnam','weight_kg':0.75}]},'JORDAN')
        updated = edited_data(data,changes)
        self.assertEqual((updated.total_value,updated.items[0].origin_country,updated.items[0].weight_kg),(0.01,'Vietnam',0.75))
        self.store.admin_command(str(uuid4()),'edit',job_id=job_id,attempt_id=attempt_id,changes=changes)
        with QueueWorker(self.config,self.store) as worker:edited_id = worker.run_once()
        self.assertEqual(self.store.get_attempt(edited_id)['state'],'completed')
        self.assertEqual(self.store.get_attempt(edited_id)['output_path'],attempt['output_path'])
        self.assertEqual(len(list(self.config.jordan_output_dir.glob('*.xlsx'))),1)
        self.assertEqual(client.get(f'/invoices/attempts/{edited_id}').status_code,200)
        self.assertEqual(source.read_bytes(),original)
        self.assertEqual(self.store.get_attempt(attempt_id)['state'],'completed')

    def test_settings_save_persists_three_country_paths_and_enables_jordan_control(self):
        import threading
        from src.foc_extractor.runtime_settings import load_runtime_settings
        result = save_runtime_settings(self.config,self.store,(threading.Lock(),threading.Lock()),
            str(uuid4()),editable_settings(self.config),lambda updated:None)
        self.assertTrue(result['settings']['jordan_enabled'])
        reloaded = load_runtime_settings(self.config)
        self.assertEqual(reloaded.inboxes(),{'JORDAN':self.config.jordan_incoming_dir})
        self.assertEqual(reloaded.output_for('JORDAN'),self.config.jordan_output_dir)
        html = create_app(reloaded,update_settings=lambda *args:None).test_client().get('/system').get_data(as_text=True)
        self.assertRegex(html,r'id="jordan-intake"[^>]*data-current="true"')
        self.assertNotRegex(html,r'id="jordan-intake"[^>]* disabled')


if __name__ == '__main__':unittest.main()
