"""Business-data checks for the approved regional factory master."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FactoryProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = json.loads((ROOT/'factory_profiles.json').read_text(encoding='utf-8'))
        cls.factories = cls.master['factories']

    def test_approved_master_has_eight_profiles_and_source_provenance(self):
        self.assertEqual(self.master['schema_version'],1)
        self.assertEqual(self.master['status'],'approved')
        self.assertEqual(self.master['defaults_regions'],['BD','INDIA','JORDAN'])
        self.assertEqual(set(self.factories),{'EGMCL','EG2','GTL','CIPL','PGCL','JORDAN','INDIA','ROSE'})
        self.assertRegex(self.master['source']['sha256'],r'^[0-9a-f]{64}$')
        self.assertEqual(self.master['source']['sheet'],'Sheet1')
        for code,profile in self.factories.items():
            region = code if code in ('INDIA','JORDAN') else 'BD'
            self.assertEqual(profile['region'],region)
            if code=='ROSE':self.assertNotIn('destination_country',profile)
            else:self.assertEqual(profile['destination_country'],'BANGLADESH' if region=='BD' else region)
            self.assertTrue(profile['consignee'].strip())
            self.assertTrue(profile['consignee_address'].strip())
            self.assertNotIn('shipping_marks',profile)

    def test_rose_has_only_the_user_approved_display_defaults(self):
        rose=self.factories['ROSE']
        self.assertEqual(rose['consignee'],'THE ROSE DRESSES LTD')
        self.assertEqual(rose['consignee_address'],'DIAKHALI, YEARPUR\nJAMGORA,ASHULIA, SAVAR,\nDHAKA-1349, Bangladesh\nBIN: 000517241-0403')
        self.assertEqual(rose['remarks'],'MOULD\nFOR 100% EXPORT ORIENTED GARMENTS INDUSTRY.\nFree of cost,Shipment under export sales contract# ROSE-00251 Dated:24-Jun-26')
        self.assertEqual(rose['source']['kind'],'user_instruction')
        self.assertIsNone(rose['source_row'])
        for field in ('tin_number','import_cover_note','shipment_text','destination_country'):
            self.assertNotIn(field,rose)

    def test_optional_fields_are_omitted_instead_of_literal_no_need(self):
        self.assertNotIn('no need',json.dumps(self.factories).lower())
        self.assertEqual({k for k,v in self.factories.items() if v.get('import_cover_note')},{'EGMCL','EG2'})
        self.assertEqual({k for k,v in self.factories.items() if v.get('tin_number')},{'EGMCL','EG2','CIPL'})
        self.assertIsNone(self.factories['JORDAN']['shipment_text'])
        self.assertEqual(self.factories['JORDAN']['origin_country'],'CHINA')
        self.assertTrue(all(v.get('origin_country') is None for k,v in self.factories.items() if k!='JORDAN'))

    def test_confirmed_factory_policies_are_recorded(self):
        self.assertEqual(self.master['policies'],{
            'matched_factory_details':'use_master_instead_of_pdf',
            'shipment_text':'use_master_when_factory_matches',
            'jordan_origin':'always_china','no_need':'omit'})

    def test_identifiers_remain_text_and_match_the_new_master(self):
        self.assertEqual(self.factories['EG2']['tin_number'],'211-201-7957/Coy-20')
        self.assertEqual(self.factories['EGMCL']['tin_number'],'472-620-435136')
        self.assertIn('BIN:000830659-1302',self.factories['GTL']['consignee_address'])
        self.assertIn('000322109-1402',self.factories['EGMCL']['consignee_address'])
        self.assertIn('000320579-0403',self.factories['EG2']['consignee_address'])
        self.assertIn('AAJCT7390N',self.factories['INDIA']['consignee_address'])
        self.assertIn('21AAJCT7390N1ZS',self.factories['INDIA']['consignee_address'])


if __name__ == '__main__':unittest.main()
