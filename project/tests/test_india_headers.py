"""India label/layout tolerance, with unrelated neighbouring fields excluded."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.ocr_engine import OCRResult,OCRTable,OCRTableCell
from src.foc_extractor.parser import parse_result
from src.foc_extractor.processing_evidence import observed


class IndiaHeaderTests(unittest.TestCase):
    def parse(self,text='',tables=None,pages=None):
        pages=pages or [text]
        ocr=OCRResult(content='\n'.join(pages),pages=pages,tables=tables or [])
        before=deepcopy(ocr)
        with patch('src.foc_extractor.parser._consignee_region',return_value='UNSEEN FACTORY\nNEW ROAD'):
            data=parse_result(ocr,Path('anonymous.pdf'),region='INDIA')
        self.assertEqual(ocr,before)
        return data

    def test_packing_dates_accept_same_or_adjacent_line_and_optional_separator(self):
        for value in ('DATE: 13-Oct-2026','Date 13-Oct-2026','Packing Date\n10/13/2026',
                      'Date = Oct. 13, 2026','DATE\n\n2026-10-13'):
            with self.subTest(value=value):
                self.assertEqual(self.parse('PACKING LIST\n'+value).export_date,'2026-10-13')

    def test_latest_packing_date_ignores_unrelated_dates_and_non_packing_pages(self):
        pages=['SHIPMENT COVER\nDate: 2028-01-01',
               'PACKING LIST\nORDER DATE: 2029-01-01\nEXPIRY DATE: 2030-01-01\nDATE\n13-Oct-2026',
               'PACKING LIST\nDate 12-Oct-2026\nDelivery Date: 2031-01-01']
        self.assertEqual(self.parse(pages=pages).export_date,'2026-10-13')

    def test_export_date_priority_for_equivalent_label_layouts(self):
        for label in ('DATE OF EXPORTATION','Export Date','ON / ABT.'):
            for separator in (': ',' ','\n'):
                with self.subTest(label=label,separator=separator):
                    self.assertEqual(self.parse(pages=[label+separator+'12-Oct-2026',
                                                      'PACKING LIST\nDate\n13-Oct-2026']).export_date,'2026-10-12')

    def test_invalid_ambiguous_or_conflicting_export_dates_do_not_use_packing_fallback(self):
        for value in ('10/09/2026','31-Feb-2026','unreadable',
                      '\nConsignee: OTHER\n12-Oct-2026',
                      '12-Oct-2026\nEXPORT DATE: 14-Oct-2026',
                      '12-Oct-2026\nEXPORT DATE: unreadable'):
            with self.subTest(value=value):
                self.assertIsNone(self.parse(pages=['EXPORT DATE: '+value,'PACKING LIST\nDATE: 13-Oct-2026']).export_date)

    def test_date_does_not_absorb_a_different_same_line_field(self):
        self.assertEqual(self.parse('EXPORT DATE: 12-Oct-2026 ORDER DATE: 20-Oct-2026').export_date,'2026-10-12')
        self.assertIsNone(self.parse('PACKING LIST\nDATE:\nORDER DATE: 20-Oct-2026').export_date)

    def test_shipping_marks_same_and_adjacent_line(self):
        for value in ('Marks & Nos: NEW-FOC','Marks and No. = NEW-FOC',
                      'SHIPPING MARKS NEW-FOC','Shipping Marks\nNEW-FOC',
                      'Marks & Nos\nNEW-FOC 9 Packages EST. 20 KGS.'):
            with self.subTest(value=value):
                self.assertEqual(self.parse(value).shipping_marks,'NEW-FOC')

    def test_combined_cover_headings_still_use_the_immediate_value_line(self):
        text=('Destination Airport Airline Counter Signature JGL-57106\n(CHENNAI,INDIA\nYes No\n'
              'Marks & Nos: No. and Kind of Packages, Weight & Description of Goods\n'
              'TGPLFOCTS 7 Packages EST. 106 KGS.\nCHENNAI, INDIA\nC/NO. T01 - T07')
        data=self.parse(text)
        self.assertEqual(data.shipping_marks,'TGPLFOCTS')
        self.assertEqual(data.destination_city,'CHENNAI, INDIA')

    def test_marks_do_not_take_cartons_packages_notes_or_other_pages(self):
        for value in ('C/NO. T01 - T07','7 Packages','GROSS WEIGHT: 20 KG',
                      'CONSIGNEE: OTHER FOC','WAREHOUSE ADDRESS: OTHER FOC',
                      'DESCRIPTION OF GOODS: FABRIC','FREIGHT PREPAID','CHENNAI, INDIA'):
            with self.subTest(value=value):
                self.assertIsNone(self.parse(pages=['SHIPPING MARKS:\n'+value,'SHIPPING MARKS: OTHER-FOC']).shipping_marks)

    def test_conflicting_marks_and_destinations_remain_blank(self):
        data=self.parse('SHIPPING MARKS: FIRST-FOC\nSHIPPING MARKS: SECOND-FOC\n'
                        'DESTINATION AIRPORT: CHENNAI, INDIA\nDESTINATION AIRPORT: MUMBAI, INDIA')
        self.assertIsNone(data.shipping_marks);self.assertIsNone(data.destination_city)

    def test_destination_same_and_adjacent_line_with_punctuation_variants(self):
        for value in ('DESTINATION AIRPORT: MUMBAI, INDIA','Destination Airport (MUMBAI,INDIA)',
                      'Destination Airport\nMUMBAI INDIA','Destination Airport =\nMUMBAI, INDIA'):
            with self.subTest(value=value):
                data=self.parse(value)
                self.assertEqual(data.destination_city,'MUMBAI, INDIA')
                self.assertEqual(data.destination_country,'India')
                self.assertIsNone(data.port_of_discharge)

    def test_destination_does_not_take_an_address_or_an_unlabelled_city(self):
        for value in ('WAREHOUSE: MUMBAI, INDIA','CONSIGNEE: MUMBAI, INDIA',
                      'COUNTRY OF ORIGIN: MUMBAI, INDIA','BOOKING NO: 123\nMUMBAI, INDIA',
                      'HONG KONG','DESCRIPTION OF GOODS: MUMBAI, INDIA'):
            with self.subTest(value=value):
                self.assertIsNone(self.parse('DESTINATION AIRPORT\n'+value).destination_city)
        self.assertIsNone(self.parse('CONSIGNEE\nMUMBAI, INDIA').destination_city)

    def test_table_adjacent_cells_supply_labels_missing_from_page_text(self):
        for horizontal in (True,False):
            with self.subTest(horizontal=horizontal):
                cells=[]
                for index,(label,value) in enumerate((('Export Date','12-Oct-2026'),
                                                    ('Shipping Marks','NEW-FOC'),
                                                    ('Destination Airport','MUMBAI,INDIA'))):
                    cells.extend([OCRTableCell(index*2,0,label),
                                  OCRTableCell(index*2 if horizontal else index*2+1,1 if horizontal else 0,value)])
                data=self.parse(tables=[OCRTable(cells,6,2)])
                self.assertEqual(data.export_date,'2026-10-12')
                self.assertEqual(data.shipping_marks,'NEW-FOC');self.assertEqual(data.destination_city,'MUMBAI, INDIA')

    def test_table_packing_date_and_evidence_keep_source_location(self):
        events=[]
        @observed
        def extract():
            return self.parse('PACKING LIST',tables=[OCRTable([
                OCRTableCell(0,0,'Packing Date'),OCRTableCell(0,1,'10/13/2026')],1,2)])
        data=extract(observer=lambda event,**kwargs:events.append(event))
        self.assertEqual(data.export_date,'2026-10-13')
        evidence=[e['evidence'] for e in events if e.get('field')=='export_date' and e.get('kind')=='field_evidence']
        self.assertTrue(any('adjacent table' in entry['location'] for e in evidence for entry in e['entries']))

    def test_unreadable_export_label_in_table_blocks_packing_fallback(self):
        for value in ('','unreadable','10/09/2026'):
            with self.subTest(value=value):
                data=self.parse('PACKING LIST\nDATE: 13-Oct-2026',tables=[OCRTable([
                    OCRTableCell(0,0,'EXPORT DATE'),OCRTableCell(0,1,value)],1,2)])
                self.assertIsNone(data.export_date)

    def test_wrapped_unreadable_export_label_does_not_allow_packing_fallback(self):
        self.assertIsNone(self.parse(pages=['DATE OF\nEXPORTATION: unreadable',
                                           'PACKING LIST\nDATE: 13-Oct-2026']).export_date)

    def test_wrapped_label_preserves_valid_export_date_and_cover_fields(self):
        data=self.parse('DATE OF\nEXPORTATION: 12-Oct-2026\nSHIPPING\nMARKS: NEW-FOC\n'
                        'DESTINATION\nAIRPORT: MUMBAI, INDIA')
        self.assertEqual(data.export_date,'2026-10-12')
        self.assertEqual(data.shipping_marks,'NEW-FOC');self.assertEqual(data.destination_city,'MUMBAI, INDIA')

    def test_wrapped_table_label_accepts_its_adjacent_cell(self):
        data=self.parse(tables=[OCRTable([OCRTableCell(0,0,'DATE OF\nEXPORTATION'),
                                         OCRTableCell(0,1,'12-Oct-2026')],1,2)])
        self.assertEqual(data.export_date,'2026-10-12')


if __name__=='__main__':unittest.main()
