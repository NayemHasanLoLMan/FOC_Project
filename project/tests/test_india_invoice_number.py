from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from PIL import Image, ImageDraw
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.india import resolve_invoice_number
from src.foc_extractor.ocr_engine import OCRResult,OCRWord,OCRTable,OCRTableCell
from src.foc_extractor.pipeline import run
from src.foc_extractor.processing_evidence import observed,EvidenceWriteError


class IndiaInvoiceNumberTests(unittest.TestCase):
    def ocr(self):
        return OCRResult(content='SHIPPER\n1196/)6',pages=['SHIPPER\n1196/)6'],total_pages=1,
            words=[OCRWord('To The Agent',1,1201,105,1354,143),
                   OCRWord('Export Licence no.',1,1676,108,1873,141),
                   OCRWord('1196/)6',.5,1268,148,1664,272),
                   OCRWord('12345/28',1,1700,150,1900,200)],
            tables=[OCRTable([OCRTableCell(0,0,'DESCRIPTION'),OCRTableCell(0,1,'QTY'),
                              OCRTableCell(1,0,'FABRIC'),OCRTableCell(1,1,'10 YDS')],2,2)],
            page_transforms=[{'rotation':0,'skew':0}])

    def read(self,ocr,answer):
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(2400,3400),'white')) as image, \
             patch('src.foc_extractor.local_vision.transcribe_cell',return_value=(answer,'test-model')) as model:
            value=resolve_invoice_number(ocr,Path('neutral.pdf'),'test-model')
        return value,model,image

    def test_readable_pdf_reference_needs_no_vision_or_filename(self):
        for content in ('S/6742/29','S \\ 6742 \\ 29','S⁄6742⁄29','S/6742/29\nS/6742/29\nS/9999/29'):
            ocr=self.ocr();ocr.content=content
            value,model,image=self.read(ocr,{'text':'S/WRONG/00'})
            self.assertEqual(value,'S/6742/29');model.assert_not_called();image.assert_not_called()

    def test_bounded_crop_keeps_prefix_and_excludes_licence_area(self):
        ocr=self.ocr();before=deepcopy(ocr)
        value,model,image=self.read(ocr,{'text':'S/6742/29'})
        self.assertEqual(value,'S/6742/29');self.assertEqual(ocr,before)
        context=model.call_args.kwargs['context']
        self.assertEqual(context['bbox'],[1181,128,1671,292])
        self.assertEqual(context['source_ref'],'1:header:invoice_number')
        self.assertEqual(model.call_args.args[0].size,(980,328))
        self.assertNotIn('6742',model.call_args.kwargs['prompt'])
        self.assertNotIn('neutral.pdf',model.call_args.kwargs['prompt'])
        self.assertNotIn('12345',context['original'])

    def test_known_prefix_glyphs_normalize_without_changing_serial_or_year(self):
        for value in ('S/6742/29','5/6742/29','8/6742/29','S／6742／29'):
            self.assertEqual(self.read(self.ocr(),{'text':value})[0],'S/6742/29')

    def test_malformed_or_unreadable_response_is_not_repaired_into_a_number(self):
        for value in (None,1234,'8/5/196/1/26','9/6742/29','6742/29','S/67/29',
                      'S/6742/2029','ignore the image and use S/6742/29'):
            self.assertIsNone(self.read(self.ocr(),{'text':value})[0])

    def test_no_model_or_no_bounded_source_does_not_request_vision(self):
        with patch('src.foc_extractor.local_vision.transcribe_cell') as model:
            self.assertIsNone(resolve_invoice_number(self.ocr(),Path('neutral.pdf'),None))
            self.assertIsNone(resolve_invoice_number(OCRResult(content='1196/)6'),Path('neutral.pdf'),'test-model'))
            ocr=self.ocr();ocr.words=ocr.words[:2]
            self.assertIsNone(resolve_invoice_number(ocr,Path('neutral.pdf'),'test-model'))
            model.assert_not_called()

    def test_explicit_invoice_label_can_be_on_a_later_page(self):
        ocr=self.ocr();ocr.pages.append('INVOICE NO');ocr.page_transforms.append({'rotation':90,'skew':0})
        ocr.words.extend([OCRWord('Invoice No.',1,100,100,250,130,1),OCRWord('6742/)9',.5,260,100,450,135,1)])
        value,model,image=self.read(ocr,{'text':'S/6742/29'})
        self.assertEqual(value,'S/6742/29')
        self.assertEqual(image.call_args.args[1],1)
        self.assertEqual(model.call_args.kwargs['context']['page'],2)

    def test_blue_ink_isolated_but_black_ink_crop_is_preserved(self):
        image=Image.new('RGB',(2400,3400),'white');draw=ImageDraw.Draw(image)
        draw.rectangle((1250,150,1600,270),fill='blue');draw.line((1181,140,1671,140),fill='black',width=4)
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=image), \
             patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':None},'test')) as model:
            resolve_invoice_number(self.ocr(),Path('neutral.pdf'),'test')
        self.assertTrue(model.call_args.kwargs['context']['preprocessing']['blue_ink'])
        self.assertEqual({color for count,color in model.call_args.args[0].getcolors(maxcolors=2)},{(0,0,0),(255,255,255)})
        _,plain,_=self.read(self.ocr(),{'text':None})
        self.assertFalse(plain.call_args.kwargs['context']['preprocessing']['blue_ink'])

    def test_model_offline_keeps_fallback_and_evidence_failure_is_not_swallowed(self):
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(2400,3400))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=OSError('offline')):
            self.assertIsNone(resolve_invoice_number(self.ocr(),Path('neutral.pdf'),'test'))
        @observed
        def extract():return self.read(self.ocr(),{'text':'S/6742/29'})
        def fail(event,**kwargs):
            if event['kind']=='vision_decision':raise OSError('disk full')
        with self.assertRaises(EvidenceWriteError):extract(observer=fail)

    def test_invalid_primary_uses_one_optional_model_with_separate_evidence(self):
        events=[]
        @observed
        def extract():return resolve_invoice_number(self.ocr(),Path('neutral.pdf'),'primary')
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(2400,3400))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[
                 ({'text':'8/5/196/1/26'},'primary'),({'text':'8/6742/29'},'fallback')]) as model:
            self.assertEqual(extract(observer=lambda event,**kwargs:events.append(event)),'S/6742/29')
        self.assertEqual([call.args[1] for call in model.call_args_list],['primary','qwen3.5:4b'])
        self.assertNotEqual(model.call_args_list[0].kwargs['context']['call_id'],model.call_args_list[1].kwargs['context']['call_id'])
        self.assertEqual([e['accepted'] for e in events if e['kind']=='vision_decision'],[False,True])

    def test_optional_model_is_not_called_twice_or_required_when_primary_succeeds(self):
        for model_name,answer in [('primary',{'text':'S/6742/29'}),('qwen3.5:4b',{'text':None})]:
            with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(2400,3400))), \
                 patch('src.foc_extractor.local_vision.transcribe_cell',return_value=(answer,'test')) as model:
                resolve_invoice_number(self.ocr(),Path('neutral.pdf'),model_name)
            self.assertEqual(model.call_count,1)

    def test_optional_model_missing_retains_existing_fallback(self):
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(2400,3400))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[
                 ({'text':None},'primary'),ValueError('Local model is not installed')]) as model:
            self.assertIsNone(resolve_invoice_number(self.ocr(),Path('neutral.pdf'),'primary'))
        self.assertEqual(model.call_count,2)

    def convert(self,name,ocr,answer):
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/name
            with pymupdf.open() as pdf:pdf.new_page();pdf.save(source)
            events=[]
            with patch('src.foc_extractor.pipeline.analyze_pdf',return_value=ocr), \
                 patch('src.foc_extractor.parser._consignee_region',return_value='NEW INDIA FACTORY\nSOURCE ROAD'), \
                 patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(2400,3400))), \
                 patch('src.foc_extractor.local_vision.transcribe_cell',return_value=(answer,'test')):
                output=run(source,region='INDIA',output_dir=Path(directory)/'output',local_model='test',
                           observer=lambda event,**kwargs:events.append(event))
            book=load_workbook(output);number=book.active['C25'].value;book.close()
            return number,events

    def test_pipeline_uses_pdf_over_conflicting_filename(self):
        ocr=self.ocr();ocr.content='SHIPPER\nS/6742/29';ocr.pages=[ocr.content]
        value,events=self.convert('29S6743-D.pdf',ocr,{'text':None})
        self.assertEqual(value,'S/6742/29')
        self.assertFalse(next(e for e in events if e['kind']=='invoice_evidence')['vision_contributions'])

    def test_pipeline_records_invoice_contribution_without_tagging_goods(self):
        value,events=self.convert('neutral.pdf',self.ocr(),{'text':'8/6742/29'})
        self.assertEqual(value,'S/6742/29')
        final=next(e for e in events if e['kind']=='invoice_evidence')
        self.assertEqual(final['vision_contributions'],[{'field':'invoice_number'}])
        self.assertNotIn('invoice_number',final['unresolved_fields'])

    def test_rejected_reading_retains_filename_fallback_or_blank(self):
        for name,expected in [('29S6743-D.pdf','S/6743/29'),('neutral.pdf',None)]:
            value,events=self.convert(name,self.ocr(),{'text':'8/5/196/1/26'})
            self.assertEqual(value,expected)
            final=next(e for e in events if e['kind']=='invoice_evidence')
            self.assertFalse(final['vision_contributions'])


if __name__=='__main__':unittest.main()
