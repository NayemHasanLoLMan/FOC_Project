import hashlib
import io
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import test_dashboard as fixtures
from src.foc_extractor.invoice_preview import invoice_sheet


class InvoiceToolsTests(unittest.TestCase):
    setUp=fixtures.DashboardTests.setUp
    convert=fixtures.DashboardTests.convert
    complete=fixtures.DashboardTests.complete

    def test_download_uses_canonical_name_without_touching_versioned_file(self):
        self.config.output_dir.mkdir(parents=True)
        occupied=self.config.output_dir/'shipment.xlsx';occupied.write_bytes(b'previous version')
        attempt=self.complete();path=Path(self.store.get_attempt(attempt)['output_path'])
        self.assertIn('__job-',path.name)
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        response=self.client.get(f'/files/attempts/{attempt}/invoice')
        self.assertEqual(response.status_code,200)
        self.assertIn('filename=shipment.xlsx',response.headers['Content-Disposition'])
        self.assertNotIn('__job-',response.headers['Content-Disposition'])
        self.assertEqual(hashlib.sha256(response.data).hexdigest(),digest)
        self.assertEqual(occupied.read_bytes(),b'previous version')

    def test_preview_is_local_escaped_and_preserves_workbook(self):
        attempt=self.complete();path=Path(self.store.get_attempt(attempt)['output_path']);before=path.read_bytes()
        response=self.client.get(f'/invoices/attempts/{attempt}')
        self.assertEqual(response.status_code,200,response.data)
        html=response.get_data(as_text=True)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;',html)
        self.assertNotIn('<script>alert(1)</script>',html)
        self.assertIn('colspan=',html);self.assertIn('S/TEST/26',html)
        self.assertIn("'nonce-",response.headers['Content-Security-Policy'])
        self.assertNotIn('unsafe-inline',response.headers['Content-Security-Policy'])
        self.assertIn('Preview Excel',self.client.get('/jobs/1').get_data(as_text=True))
        self.assertEqual(path.read_bytes(),before)
        path.write_bytes(b'changed')
        self.assertEqual(self.client.get(f'/invoices/attempts/{attempt}').status_code,409)

    def test_preview_keeps_red_rich_text_and_does_not_evaluate_formulas(self):
        from openpyxl import Workbook
        from openpyxl.cell.rich_text import CellRichText,TextBlock
        from openpyxl.cell.text import InlineFont
        book=Workbook();sheet=book.active;sheet.print_area='A1:B2'
        sheet['A1']=CellRichText(['C/NO. ',TextBlock(InlineFont(color='FF0000'),'E01-E14')])
        sheet.merge_cells('A1:B1');sheet['B2']='=1+1'
        buffer=io.BytesIO();book.save(buffer);book.close()
        view=invoice_sheet(buffer.getvalue());cells=view['rows'][0]['cells']
        self.assertEqual(cells[0]['colspan'],2)
        self.assertEqual(cells[0]['parts'][1]['text'],'E01-E14')
        self.assertIn('color:#FF0000',view['styles'][cells[0]['parts'][1]['class']])
        self.assertEqual(view['rows'][1]['cells'][1]['parts'][0]['text'],'')

    def test_standalone_dashboard_without_coordinator_cannot_clear_data(self):
        self.assertNotIn('>Clear data</button>',self.client.get('/system').get_data(as_text=True))
        token=self.client.get('/api/controls').get_json()['csrf_token']
        response=self.client.post('/api/development/reset',json={'request_id':'00000000-0000-4000-8000-000000000001'},
            headers={'Origin':'http://localhost','X-CSRF-Token':token})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.store.counts()['queued'],1)


if __name__=='__main__':unittest.main()
