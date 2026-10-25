from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor.jordan import apply_header, resolve_invoice_number, resolve_date
from src.foc_extractor.models import FOCData, LineItem
from src.foc_extractor.ocr_engine import OCRResult, OCRWord
from src.foc_extractor.parser import parse_result
from src.foc_extractor.processing_evidence import observed, emit, EvidenceWriteError
from src.foc_extractor.regions import select_region


class JordanHeaderTests(unittest.TestCase):
    def cover(self):
        return ('SHIPPER\nS/54321/27\nCONSIGNEE:\nUNSEEN COMPANY JORDAN\nNEW ROAD\n'
                'ZARQA, JORDAN\nCONTACT NAME: PERSON\nMOBILE: 0123\nNOTIFY PARTY:\nOTHER COMPANY\n'
                'DESTINATION AIRPORT / PLACE: AMMAN\nMARKS & NOS: No. and Kind of Packages\n'
                '4 PACKAGES APP. 99 KGS\nNEW1FOCTS\nJORDAN\nC/NO. J01-J04\nWAREHOUSE ADDRESS:\nOTHERFOC')

    def ocr(self, pages=None):
        pages=pages or [self.cover()]
        return OCRResult(content='\n'.join(pages), pages=pages, total_pages=len(pages))

    def parse(self, pages=None):
        ocr=self.ocr(pages); before=deepcopy(ocr)
        data=parse_result(ocr,Path('99S9999-D.pdf'),region='JORDAN')
        self.assertEqual(ocr,before)
        return data

    def test_source_headers_exclude_contacts_notify_warehouse_and_filename_defaults(self):
        data=self.parse()
        self.assertEqual(data.consignee,'UNSEEN COMPANY JORDAN')
        self.assertEqual(data.consignee_address,'NEW ROAD\nZARQA, JORDAN')
        self.assertEqual(data.invoice_number,'S/54321/27')
        self.assertEqual(data.shipping_marks,'NEW1FOCTS')
        self.assertEqual(data.carton_range,'J01-J04')
        self.assertEqual(data.destination_city,'AMMAN')
        self.assertEqual(data.destination_country,'Jordan')

    def test_missing_source_fields_do_not_use_company_directory_or_filename(self):
        data=self.parse(['SHIPPER\nEPIC DESIGNERS JORDAN'])
        for field in ('consignee','consignee_address','invoice_number','shipping_marks','destination_city','destination_country'):
            self.assertIsNone(getattr(data,field),field)

    def test_latest_packing_date_and_explicit_export_priority(self):
        pages=[self.cover(),'PACKING LIST\nDATE: 6-Oct-2026','PACKING LIST\nDATE: 7-Oct-2026\nORDER DATE: 1-Oct-2030']
        self.assertEqual(self.parse(pages).export_date,'2026-10-07')
        pages[0]+='\nEXPORT DATE: 5-Oct-2026'
        self.assertEqual(self.parse(pages).export_date,'2026-10-05')
        pages[0]=self.cover()+'\nEXPORT DATE: unreadable'
        self.assertIsNone(self.parse(pages).export_date)

    def test_cover_signature_date_is_not_a_packing_date_despite_document_checkboxes(self):
        pages=[self.cover()+'\nDocuments: PACKING LIST\nDATE: 1-Oct-2030',
               'PACKING LIST\nDATE: 6-Oct-2026']
        self.assertEqual(self.parse(pages).export_date,'2026-10-06')
        self.assertEqual(resolve_date(self.ocr(pages),Path('a.pdf'),None),'2026-10-06')

    def test_contact_country_does_not_replace_the_consignee_destination(self):
        cover=self.cover().replace('CONTACT NAME: PERSON','CONTACT NAME: INDIA OFFICE')
        self.assertEqual(self.parse([cover]).destination_country,'Jordan')

    def test_conflicting_packing_recipient_is_retained_and_does_not_reroute_or_remove_goods(self):
        pages=[self.cover(),'TO: OTHER COMPANY INDIA\nPACKING LIST\nDATE: 8-Oct-2026\nCOO: BANGLADESH']
        events=[]
        @observed
        def extract():
            with patch('src.foc_extractor.parser._extract_table_data',return_value=(
                    [LineItem('FABRIC',2,'PCS',source_page=2,source_refs=['2:1:2'])],[],{1},[])):
                return self.parse(pages)
        data=extract(observer=lambda event,**kwargs:events.append(event))
        self.assertEqual(select_region(data,'JORDAN',pages[0]),'JORDAN')
        self.assertEqual(data.items[0].source_page,2)
        evidence=next(e['evidence'] for e in events if e.get('field')=='page_identity')
        self.assertEqual(evidence['policy'],'include_all_pages_cover_destination')
        self.assertEqual(evidence['conflict_pages'],[2])
        self.assertTrue(all(page['included'] for page in evidence['pages']))
        self.assertEqual(evidence['pages'][1]['recipient_countries'],['India'])

    def test_item_origin_is_not_treated_as_a_recipient_destination(self):
        data=self.parse([self.cover(),'TO: NEW SAMPLE DEPARTMENT\nPACKING LIST\nCOO: INDIA'])
        self.assertEqual(data.destination_country,'Jordan')
        self.assertFalse(any('recipient names' in warning for warning in data.warnings))

    def test_cover_country_mismatch_remains_a_routing_error(self):
        cover=self.cover().replace('JORDAN','INDIA')
        data=self.parse([cover])
        with self.assertRaisesRegex(ValueError,'conflicts'):
            select_region(data,'JORDAN',cover)

    def test_repeated_inner_page_invoice_reference_cannot_replace_the_cover(self):
        ocr=self.ocr([self.cover(),'PACKING LIST\nS/999/28\nS/999/28'])
        self.assertEqual(resolve_invoice_number(ocr,Path('28S999.pdf'),None),'S/54321/27')
        ocr.pages[0]='SHIPPER\nCONSIGNEE:\nNEW CO JORDAN';ocr.content='\n'.join(ocr.pages)
        self.assertIsNone(resolve_invoice_number(ocr,Path('28S999.pdf'),None))

    def test_plausible_cover_ocr_reference_is_checked_against_bounded_handwriting(self):
        ocr=self.ocr(['SHIPPER\nS/1234/27'])
        ocr.words=[OCRWord('To The Agent',1,100,50,220,70),OCRWord('S/1234/27',.9,110,80,300,210),
                   OCRWord('LOGISTICS COMPANY',1,100,240,320,260),OCRWord('999999',1,110,270,300,290)]
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(500,500))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':'S/7234/27'},'test')) as model:
            self.assertEqual(resolve_invoice_number(ocr,Path('unrelated.pdf'),'model'),'S/7234/27')
            self.assertEqual(model.call_args.kwargs['context']['page'],1)
            self.assertGreaterEqual(model.call_args.kwargs['context']['bbox'][3],210)
            self.assertNotIn('999999',model.call_args.kwargs['context']['original'])
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(500,500))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=OSError('offline')):
            self.assertEqual(resolve_invoice_number(ocr,Path('unrelated.pdf'),'model'),'S/1234/27')

    def test_bad_labelled_date_uses_one_bounded_image_and_retains_evidence(self):
        ocr=self.ocr([self.cover(),'PACKING LIST\nDATE: 6-Uct-26'])
        ocr.words=[OCRWord('Date: 6-Uct-26',.7,100,50,280,75,1)]
        events=[]
        @observed
        def extract():return resolve_date(ocr,Path('unrelated.pdf'),'model')
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(500,500))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':'6-Oct-26'},'test')) as model:
            self.assertEqual(extract(observer=lambda event,**kwargs:events.append(event)),'2026-10-06')
        self.assertEqual(model.call_args.kwargs['context']['page'],2)
        self.assertTrue(any(e['kind']=='vision_decision' and e['accepted'] for e in events))

    def test_known_prefix_separator_repairs_preserve_variable_serial_and_year_digits(self):
        ocr=self.ocr(['SHIPPER'])
        ocr.words=[OCRWord('To The Agent',1,100,50,220,70),OCRWord('12345/27',.8,110,80,300,170)]
        for raw, expected in (('ST54321/27','S/54321/27'),('S543/27','S/543/27'),
                              ('SI00123/29','S/00123/29'),('S/15/173/126',None),('S/54X21/27',None)):
            with self.subTest(raw=raw), \
                 patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(500,500))), \
                 patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':raw},'test')):
                self.assertEqual(resolve_invoice_number(ocr,Path('unrelated.pdf'),'model'),expected)

    def test_date_reader_never_invents_a_year_or_uses_packing_fallback_for_bad_export(self):
        for response in ('6-Oct', '31-Feb-26', None):
            ocr=self.ocr(['EXPORT DATE: unreadable','PACKING LIST\nDATE: 7-Oct-2026'])
            ocr.words=[OCRWord('EXPORT DATE: unreadable',.7,100,50,280,75)]
            with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(500,500))), \
                 patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':response},'test')):
                self.assertIsNone(resolve_date(ocr,Path('unrelated.pdf'),'model'))

    def test_readable_dates_need_no_model_and_evidence_failures_are_not_swallowed(self):
        with patch('src.foc_extractor.local_vision.transcribe_cell') as model:
            self.assertEqual(resolve_date(self.ocr(['PACKING LIST\nDATE: 7-Oct-2026']),Path('a.pdf'),'model'),'2026-10-07')
            model.assert_not_called()
            self.assertEqual(resolve_date(self.ocr(['PACKING LIST\nDATE: 7-Oct-2026',
                                                   'PACKING LIST\nDATE: 7-Oct']),Path('a.pdf'),'model'),'2026-10-07')
            model.assert_not_called()
        @observed
        def extract():return resolve_date(self.ocr(['PACKING LIST\nDATE: 7-Oct-2026']),Path('a.pdf'),None)
        def failed(*args,**kwargs):raise OSError('evidence disk unavailable')
        with self.assertRaises(EvidenceWriteError):extract(observer=failed)

    def test_pipeline_counts_date_vision_only_when_the_final_field_is_usable(self):
        from src.foc_extractor.pipeline import run
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'unseen.pdf'
            with pymupdf.open() as pdf:pdf.new_page();pdf.save(source)
            for final_date in (None,'2026-10-06'):
                events=[]
                def read(*args,**kwargs):
                    emit('vision_decision',field='export_date',accepted=True,source_ref='1:header:export_date')
                    return final_date
                with patch('src.foc_extractor.pipeline.analyze_pdf',return_value=self.ocr()), \
                     patch('src.foc_extractor.jordan.resolve_date',side_effect=read):
                    run(source,region='JORDAN',output_dir=root/'out',local_model=None,
                        observer=lambda event,**kwargs:events.append(event))
                summary=next(event for event in events if event['kind']=='invoice_evidence')
                self.assertEqual({'field':'export_date'} in summary['vision_contributions'],final_date is not None)
