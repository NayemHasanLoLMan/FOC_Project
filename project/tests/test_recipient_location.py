import sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.parser import parse_result
from src.foc_extractor.ocr_engine import OCRResult,OCRTable,OCRTableCell


class RecipientLocationTests(unittest.TestCase):
    def data(self,recipients,*,label='RECIPIENT / DEPT #',page=0,header=True,to='UNFAMILIAR FACTORY',region='BD'):
        cells=[OCRTableCell(0,c,text,page=page) for c,text in enumerate(
            [label,'BUYER NAME','PARTICULARS','QTY'] if header else ['OTHER','BUYER NAME','PARTICULARS','QTY'])]
        for row,recipient in enumerate(recipients,1):
            cells.extend(OCRTableCell(row,c,text,page=page) for c,text in enumerate(
                [recipient,'BUYER ROAD, BANGLADESH','FABRIC','5 YDS']))
        return parse_result(OCRResult(content=f'To: {to}\nPACKING LIST',
               tables=[OCRTable(cells,len(recipients)+1,4,page=page)]),Path('anonymous.pdf'),region=region)

    def test_recipient_location_uses_label_not_column_position_and_preserves_partial_text(self):
        for label in ('RECIPIENT / DEPT #','RECEIPIENT / DEPT #'):
            data=self.data(['ATTN# SOMEONE / ANOTHER\nSavar,\nDHAKA, BANGLADESH'],label=label)
            self.assertEqual(data.consignee,'UNFAMILIAR FACTORY')
            self.assertEqual(data.consignee_address,'Savar,\nDHAKA, BANGLADESH')
            self.assertEqual(data.destination_country,'Bangladesh')
            self.assertIsNone(data.destination_city)
            self.assertIsNone(data.shipping_marks)
            self.assertNotIn('BUYER ROAD',data.consignee_address)
            self.assertEqual(data.items[0].quantity,5)

    def test_contact_only_and_company_names_do_not_become_an_address(self):
        for value in ('Jalal / Toriqul','MERCHANDISING TEAM\nATTN: Someone\nDirect: +8801712345678',
                      'person@example.test','ATTN: Bangladesh Team','Bangladesh Garments Company Ltd'):
            data=self.data([value])
            self.assertIsNone(data.consignee_address,value)
            self.assertIsNone(data.destination_country,value)

    def test_readable_street_without_country_does_not_invent_country(self):
        data=self.data(['UNFAMILIAR FACTORY\n12 NEW ROAD\nTel: +8801712345678\nperson@example.test'])
        self.assertEqual(data.consignee_address,'12 NEW ROAD')
        self.assertIsNone(data.destination_country)

    def test_labelled_consignee_block_wins_even_if_recipient_differs(self):
        with patch('src.foc_extractor.parser._consignee_region',return_value='SOURCE FACTORY\nEXPLICIT STREET'):
            data=self.data(['OTHER ROAD, BANGLADESH'])
        self.assertEqual(data.consignee,'SOURCE FACTORY')
        self.assertEqual(data.consignee_address,'EXPLICIT STREET')
        self.assertIsNone(data.destination_country)

    def test_duplicate_addresses_collapse_but_conflicting_locations_stay_blank(self):
        self.assertEqual(self.data(['FIRST ROAD, BANGLADESH','first road, bangladesh']).consignee_address,
                         'FIRST ROAD, BANGLADESH')
        data=self.data(['FIRST ROAD, BANGLADESH','OTHER ROAD, BANGLADESH'])
        self.assertIsNone(data.consignee_address)
        self.assertIsNone(data.destination_country)

    def test_other_pages_or_unlabelled_columns_cannot_supply_recipient_address(self):
        for options in ({'page':1},{'header':False}):
            data=self.data(['FIRST ROAD, BANGLADESH'],**options)
            self.assertIsNone(data.consignee_address)
            self.assertIsNone(data.destination_country)

    def test_source_identifiers_are_retained_but_no_bin_is_added(self):
        data=self.data(['NEW ROAD, BANGLADESH\nBIN: 001234567-0123'])
        self.assertIn('BIN: 001234567-0123',data.consignee_address)
        self.assertNotIn('BIN',self.data(['NEW ROAD, BANGLADESH']).consignee_address)

    def test_india_and_jordan_do_not_use_bangladesh_recipient_fallback(self):
        with patch('src.foc_extractor.parser._packing_recipient_address',side_effect=AssertionError('wrong region')):
            for region in ('INDIA','JORDAN'):self.data(['NEW ROAD, BANGLADESH'],region=region)


if __name__=='__main__':unittest.main()
