from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.parser import parse_result
from src.foc_extractor.india import resolve_invoice_number
from src.foc_extractor.ocr_engine import OCRResult,OCRWord,OCRTable,OCRTableCell
from src.foc_extractor.processing_evidence import observed


class BangladeshHeaderTests(unittest.TestCase):
    def parse(self,text,**kwargs):
        return parse_result(OCRResult(content=text,pages=[text],**kwargs),Path('99S9999-D.pdf'),region='BD')

    def test_packing_recipient_and_category_remain_literal_without_directory_facts(self):
        for recipient in ('GTL-FABRIC','CIPL-GMT','EGMCL 2 FOC','UNSEEN FACTORY'):
            data=self.parse('To: '+recipient+'\nPACKING LIST\nPEARL BUTTONS')
            self.assertEqual(data.consignee,recipient)
            self.assertIsNone(data.consignee_address)
            self.assertEqual(data.shipping_marks,{'GTL-FABRIC':'GTL-FABRIC','CIPL-GMT':'CIPL-GMT',
                                                'EGMCL 2 FOC':'EGMCL 2-FOC'}.get(recipient))

    def test_source_party_address_and_bin_exclude_other_parties_and_contacts(self):
        text=('SHIPPER\nCONSIGNEE:\nUNSEEN FACTORY\nNEW ROAD\nBANGLADESH. ATTN: PERSON\n'
              '(BIN:123456789-0123)\nNOTIFY PARTY:\nOTHER FACTORY\nOTHER ROAD\nBIN:000000000-0000')
        data=self.parse(text)
        self.assertEqual(data.consignee,'UNSEEN FACTORY')
        self.assertEqual(data.consignee_address,'NEW ROAD\nBANGLADESH.\n(BIN:123456789-0123)')
        self.assertEqual(data.destination_country,'Bangladesh')
        self.assertIsNone(data.destination_city)

    def test_labelled_table_party_is_read_without_company_lookup(self):
        table=OCRTable([OCRTableCell(0,0,'Consignee: NEW FACTORY\nROAD 123\nBIN: 987654321-1234'),
                        OCRTableCell(0,1,'AGENT\nNOT OUR ROAD')],1,2)
        data=self.parse('SHIPPER',tables=[table])
        self.assertEqual(data.consignee,'NEW FACTORY')
        self.assertEqual(data.consignee_address,'ROAD 123\nBIN: 987654321-1234')

    def test_cover_marks_survive_adjacent_package_currency_and_goods_text(self):
        for line in ('GTL-FOC 4 PACKAGE(S) ONLY app. 83 KGS','EGMCL-FOC 15 PACKAGES EST. 261 KGS',
                     'CIPL-FOC PACKAGE(S) ONLY EST. 71 KGS'):
            data=self.parse('SHIPPER\nMarks & Nos: No. and Kind of Packages, Weight & Description of Goods\n'
                            +line+'\nDHAKA, BD USD\nC/NO. A01-A04\nFABRICS')
            self.assertEqual(data.shipping_marks,line.split()[0])

    def test_marks_do_not_come_from_enclosures_or_currency(self):
        text='SHIPPER\nMarks & Nos: No. and Kind of Packages\nUSD\nC/NO. A01-A04'
        ocr=OCRResult(content=text+'\nTo: OTHER-FOC',pages=[text,'To: OTHER-FOC\nPACKING LIST'])
        data=parse_result(ocr,Path('99S9999-D.pdf'),region='BD')
        self.assertIsNone(data.shipping_marks)
        self.assertIsNone(data.consignee)

    def test_source_tin_and_cover_note_retained_without_template_defaults(self):
        data=self.parse('To: NEW FACTORY\nPACKING LIST\nTIN # 123-456-78901\n'
                        'Import open cover note # ABC/123/2026 (OPEN) Dated 03-JUL-2026')
        self.assertEqual(data.tin_number,'123-456-78901')
        self.assertIn('ABC/123/2026',data.import_cover_note)
        missing=self.parse('To: GREEN TEXTILE LIMITED\nPACKING LIST')
        self.assertIsNone(missing.tin_number)
        self.assertIsNone(missing.import_cover_note)

    def test_partial_packing_reference_at_title_height_is_bounded_and_verified(self):
        ocr=OCRResult(content='To: NEW-FOC\nPACKING LIST\n9/6742/2',pages=['PACKING LIST'],
            words=[OCRWord('PACKING LIST',1,300,100,500,130),
                   OCRWord('9/6742/2',.5,800,110,1000,170),
                   OCRWord('PARTICULARS',1,300,210,500,230)])
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(1200,800))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':'S/6742/29'},'test')) as read:
            value=resolve_invoice_number(ocr,Path('renamed.pdf'),'test',verify_handwriting=True)
        self.assertEqual(value,'S/6742/29')
        self.assertEqual(read.call_args.kwargs['context']['source_ref'],'1:header:invoice_number')
        self.assertNotIn('PARTICULARS',read.call_args.kwargs['context']['original'])

    def test_disagreeing_models_need_a_matching_original_pixel_read(self):
        ocr=OCRResult(content='S/742/29',pages=['SHIPPER'],
            words=[OCRWord('To The Agent',1,100,50,220,70),OCRWord('S/742/29',.7,110,80,300,180)])
        image=Image.new('RGB',(500,500),'white')
        from PIL import ImageDraw
        ImageDraw.Draw(image).rectangle((120,90,290,170),fill='blue')
        events=[]
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=image), \
             patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[
                 ({'text':'S/16742/29'},'primary'),({'text':'S/6742/29'},'fallback'),
                 ({'text':'S/6742/29'},'fallback')]) as read:
            value=observed(resolve_invoice_number)(ocr,Path('99S9999-D.pdf'),'primary',
                verify_handwriting=True,corroborate=True,observer=lambda e,**kw:events.append(e))
        self.assertEqual(value,'S/6742/29')
        self.assertEqual([e['accepted'] for e in events if e['kind']=='vision_decision'],[False,False,True])
        self.assertEqual([call.kwargs['context']['preprocessing']['blue_ink'] for call in read.call_args_list],
                         [True,True,False])

    def test_disagreement_does_not_publish_an_uncorroborated_model_correction(self):
        ocr=OCRResult(content='S/742/29',pages=['SHIPPER'],
            words=[OCRWord('To The Agent',1,100,50,220,70),OCRWord('S/742/29',.7,110,80,300,180)])
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(500,500))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[
                 ({'text':'S/16742/29'},'primary'),({'text':'S/6742/29'},'fallback')]):
            self.assertEqual(resolve_invoice_number(ocr,Path('99S9999-D.pdf'),'primary',
                             verify_handwriting=True,corroborate=True),'S/742/29')

    def test_directory_evidence_is_never_emitted_for_missing_fields(self):
        events=[]
        observed(self.parse)('To: EGMCL-FOC\nPACKING LIST',observer=lambda e,**kw:events.append(e))
        self.assertFalse(any(e.get('method')=='company_directory' for e in events))


if __name__=='__main__':unittest.main()
