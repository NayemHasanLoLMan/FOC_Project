"""Factory matching must not change shipment data or use unrelated party mentions."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor import factory_profiles, pipeline
from src.foc_extractor.factory_profiles import identify_factory
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell, OCRWord
from src.foc_extractor.processing_evidence import observed


class FactoryIdentificationTests(unittest.TestCase):
    def identify(self,text,region='BD',later='',consignee=None):
        ocr = OCRResult(content=text+'\n'+later,pages=[text,later] if later else [text])
        before = deepcopy(ocr)
        result = identify_factory(ocr,region,consignee)
        self.assertEqual(ocr,before)
        return result

    def test_eight_profiles_and_legal_name_variants(self):
        for text,region,code in [
            ('TO: THE ROSE DRESSES LTD','BD','ROSE'),('TO: ROSE DRESSES LIMITED','BD','ROSE'),
            ('TO: EGMCL-FOC','BD','EGMCL'),('TO: EG2','BD','EG2'),
            ('TO: GTL-FOC','BD','GTL'),('CONSIGNEE: COSMOPOLITAN INDUSTRIES (PVT.) LTD.','BD','CIPL'),
            ('Consignee:\nPEARL GARMENTS COMPANY LTD.','BD','PGCL'),
            ('TO: TGPL-FOC','INDIA','INDIA'),('TO: EJU1FOCTS','JORDAN','JORDAN'),
            ('CONSIGNEE: TRIMETRO GARMENTS INDIA PRIVATE LIMITED','INDIA','INDIA'),
            ('CONSIGNEE: EPIC DESIGNERS LTD.','JORDAN','JORDAN'),('EG2\nPACKING LIST','BD','EG2')]:
            with self.subTest(text=text):
                result = self.identify(text,region)
                self.assertEqual((result['factory_id'],result['status']),(code,'matched'))

    def test_unit_two_refines_generic_family_without_guessing_other_units(self):
        for name in ('EGMCL2-FOC','EGMCL UNIT-2 FOC',
                     'EPIC GARMENTS MANUFACTURING CO.LTD.,(UNIT-2)',
                     'EPIC GARMENTS MANUFACTURING CO. LTD.\nUNIT 2',
                     'EPIC GARMENTS MANUFACTURING CO. LTD.\nUNIT2', 'EGMCL UNIT 02'):
            with self.subTest(name=name):
                self.assertEqual(self.identify('CONSIGNEE:\n'+name,consignee='EGMCL')['factory_id'],'EG2')
        for name in ('EGMCL UNIT 3','EPIC GARMENTS MANUFACTURING CO LTD UNIT 99'):
            self.assertEqual(self.identify('TO: '+name)['status'],'ambiguous')
        self.assertEqual(self.identify('TO: EGMCL UNIT 1\nCONSIGNEE: EGMCL UNIT 2')['status'],'ambiguous')
        self.assertEqual(self.identify('CONSIGNEE:\nEGMCL UNIT 1\nUNIT 2')['status'],'ambiguous')

    def test_sender_buyer_notify_and_later_packing_pages_cannot_reroute(self):
        text = 'TO: PGCL-FABRIC\nPACKING LIST\nSENDER: EGMCL UNIT 2\nBUYER: GTL\nRECIPIENT: CIPL'
        result = self.identify(text,later='TO: EGMCL UNIT 2\nPACKING LIST')
        self.assertEqual(result['factory_id'],'PGCL')
        cover = 'SHIPPER\nCIPL\nCONSIGNEE:\nGREEN TEXTILE LIMITED\nNOTIFY PARTY:\nPEARL GARMENTS CO LTD'
        self.assertEqual(self.identify(cover)['factory_id'],'GTL')

    def test_conflicting_countries_and_factories_remain_unresolved(self):
        for text,region,status in [('TO: CIPL\nCONSIGNEE: PGCL','BD','ambiguous'),
                                   ('TO: TGPL','BD','country_conflict'),
                                   ('CONSIGNEE: PEARL GARMENTS CO LTD','INDIA','country_conflict')]:
            with self.subTest(text=text):
                result = self.identify(text,region)
                self.assertIsNone(result['factory_id']);self.assertEqual(result['status'],status)

    def test_unknown_factory_country_only_and_substrings_do_not_match(self):
        for text,region in [('TO: THE UNLISTED DRESSES LTD','BD'),('TO: NEW PGCL SUPPLIER','BD'),
                            ('DESTINATION COUNTRY: JORDAN','JORDAN'),('TO: INDIA','INDIA'),
                            ('PACKING LIST\nBUYER: CIPL','BD')]:
            self.assertEqual(self.identify(text,region)['status'],'unknown')

    def test_forwarder_boilerplate_does_not_hide_real_consignee(self):
        result = self.identify('SHIPPER\nCONSIGNEE JANCO GLOBAL LOGISTICS LTD.\n'
                              'COSMOPOLITAN INDUSTRIES (PVT.) LIMITED (hereinafter referred to as "the company")\n'
                              'ADDRESS\nNOTIFY PARTY\nPGCL')
        self.assertEqual(result['factory_id'],'CIPL')

    def test_match_is_audited_with_master_checksum(self):
        events = []
        @observed
        def identify():return self.identify('TO: PGCL-FOC')
        result = identify(observer=lambda event,**kwargs:events.append(event))
        event = next(e for e in events if e['kind']=='factory_identification')
        self.assertEqual(event['factory_id'],'PGCL')
        self.assertEqual(result['profile_sha256'],hashlib.sha256(factory_profiles.MASTER_FILE.read_bytes()).hexdigest())
        self.assertTrue(event['evidence'])

    def test_address_only_matches_eight_profiles_in_the_recipient_block(self):
        addresses = [
            ('DIAKHALI, YEARPUR\nJAMGORA, ASHULIA, SAVAR','BD','ROSE'),
            ('Adamjee EPZ.\nSiddhirganj PS : Narayanganj-1431','BD','EGMCL'),
            ('SFB NO.08\nDEPZ EXTENSION AREA,\nGONOK BARI, SAVAR','BD','EG2'),
            ('NIJHURI, BARAID, 2 NO MEDUARI\nBHALUKA, MYMENSINGH','BD','GTL'),
            ('Khejur-Bagan, Bara Ashulia\nSavar PS; Dhaka-1341','BD','CIPL'),
            ('Polashbari, Nabinagar, Savar','BD','PGCL'),
            ('MOTA VILLAGE,KALIBETI MOUZA\nREVENUE PLOT NO 282,JANKIA,KHORDA ODISHA','INDIA','INDIA'),
            ('AD DULAYL INDUSTRIAL PARK\nLANE NO 1201\nAD DULAYL BASIN 5, ZARQA, JORDAN','JORDAN','JORDAN')]
        for address,region,code in addresses:
            with self.subTest(code=code):
                result = self.identify('CONSIGNEE:\n[unreadable name]\n'+address,region)
                self.assertEqual((result['factory_id'],result['status']),(code,'matched'))
                evidence = next(e for e in result['evidence'] if e.get('method')=='address')
                self.assertGreaterEqual(len(evidence['matched_clues']),2)
        self.assertEqual(self.identify('Polashbari, Nabinagar\nPACKING LIST')['factory_id'],'PGCL')

    def test_address_clues_must_be_complete_and_belong_to_one_recipient(self):
        for text in ('TO: THE UNLISTED DRESSES LTD\nSavar, Dhaka, Bangladesh',
                     'TO: unreadable\nAdamjee EPZ',
                     'TO: unreadable\nAD DULAYL\nPACKING LIST',
                     'TO: unreadable\nPolashbari\nTO: unreadable\nNabinagar',
                     'TO: unreadable\nPolashbari\nNOTIFY PARTY\nNabinagar',
                     'TO: unreadable\nPolashbariOTHER, Nabinagar',
                     'TO: unreadable\nBIN : 000817323-0112'):
            with self.subTest(text=text):
                self.assertEqual(self.identify(text)['status'],'unknown')
        self.assertEqual(self.identify('TO: unreadable\nPolashbari',later='TO: Nabinagar')['status'],'unknown')

    def test_address_cannot_reroute_explicit_factory_or_country(self):
        cases = [
            ('TO: PGCL\nKhejur Bagan, Bara Ashulia','BD','ambiguous'),
            ('TO: EGMCL UNIT 1\nDEPZ EXTENSION AREA, GONOK BARI','BD','ambiguous'),
            ('TO: EGMCL UNIT 2\nAdamjee EPZ, Siddhirganj','BD','ambiguous'),
            ('TO: EGMCL UNIT 3\nAdamjee EPZ, Siddhirganj','BD','ambiguous'),
            ('TO: unreadable\nAdamjee EPZ, Siddhirganj\nPolashbari, Nabinagar','BD','ambiguous'),
            ('TO: unreadable\nAD DULAYL, ZARQA','BD','country_conflict')]
        for text,region,status in cases:
            with self.subTest(text=text):
                result = self.identify(text,region)
                self.assertIsNone(result['factory_id']);self.assertEqual(result['status'],status)
        self.assertEqual(self.identify('TO: EGMCL\nDEPZ EXTENSION AREA, GONOK BARI')['factory_id'],'EG2')

    def test_shipper_agent_buyer_and_later_page_addresses_cannot_supply_factory(self):
        for text in ('SHIPPER\nPolashbari, Nabinagar\nCONSIGNEE:\nUnreadable\nNOTIFY PARTY',
                     'TO: unreadable\nPACKING LIST\nBUYER: Polashbari, Nabinagar',
                     'TO: unreadable\nBUYER: Polashbari, Nabinagar',
                     'TO: unreadable\nNOTIFY PARTY: Polashbari, Nabinagar'):
            with self.subTest(text=text):self.assertEqual(self.identify(text)['status'],'unknown')
        self.assertEqual(self.identify('TO: unreadable',later='TO: Polashbari, Nabinagar')['status'],'unknown')
        ocr = OCRResult(content='CONSIGNEE\nUnreadable Polashbari, Nabinagar\nNOTIFY PARTY',words=[
            OCRWord('CONSIGNEE',1,10,10,95,25), OCRWord('Unreadable',1,10,30,95,45),
            OCRWord('Polashbari, Nabinagar',1,650,30,1000,45), OCRWord('NOTIFY PARTY',1,10,100,95,115)])
        self.assertEqual(identify_factory(ocr,'BD')['status'],'unknown')

    def test_address_matching_ignores_obsolete_tax_identifier(self):
        result = self.identify('CONSIGNEE:\nUnreadable\nNIJHURI, BARAID\nBHALUKA\nBIN 000830659-0104')
        self.assertEqual(result['factory_id'],'GTL')

    def test_invalid_address_rules_are_rejected(self):
        master = json.loads(factory_profiles.MASTER_FILE.read_text(encoding='utf-8'))
        for clues in ('POLASHBARI',[],['POLASHBARI'],['POLASHBARI','POLASHBARI'],
                      ['POLASHBARI','OTHER SITE'],['POLASHBARI',None]):
            changed = deepcopy(master);changed['factories']['PGCL']['address_match'] = clues
            with self.subTest(clues=clues),patch.object(Path,'read_bytes',return_value=json.dumps(changed).encode()):
                with self.assertRaises(ValueError):self.identify('TO: PGCL')

    def test_unapproved_or_invalid_master_is_rejected(self):
        master = json.loads(factory_profiles.MASTER_FILE.read_text(encoding='utf-8'))
        for changes in ({'status':'draft'},{'schema_version':99}):
            with patch.object(Path,'read_bytes',return_value=json.dumps({**master,**changes}).encode()):
                with self.assertRaises(ValueError):self.identify('TO: PGCL')

    def test_pipeline_applies_bd_profile_and_preserves_original_header_evidence(self):
        text = 'TO: PGCL-FOC\nDATE: 20-Oct-2026\nPACKING LIST S/9001/26\n100% COTTON 10 YDS'
        rows = [['PARTICULARS','QTY'],['100% COTTON','10 YDS']]
        ocr = OCRResult(content=text,pages=[text],total_pages=1,backend='test',tables=[
            OCRTable([OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)],2,2)])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);source = root/'renamed-shipment.pdf'
            with pymupdf.open() as pdf:pdf.new_page().insert_text((40,40),text);pdf.save(source)
            events = []
            with patch.object(pipeline,'analyze_pdf',return_value=ocr):
                pipeline.run(source,region='BD',output_dir=root/'out',local_model=None,save_json=True,
                             observer=lambda event,**kwargs:events.append(event))
            saved = json.loads((root/'out/renamed-shipment.json').read_text(encoding='utf-8'))
            profile = json.loads(factory_profiles.MASTER_FILE.read_text(encoding='utf-8'))['factories']['PGCL']
            for field in ('consignee','consignee_address','destination_country','tin_number','import_cover_note','shipment_text','remarks'):
                self.assertEqual(saved[field],profile[field])
            source = next(e for e in events if e.get('method')=='approved_factory_master' and e.get('field')=='consignee')
            self.assertEqual(source['original_value'],'PGCL-FOC')
            self.assertEqual(source['factory_id'],'PGCL')
            match = next(e for e in events if e['kind']=='factory_identification')
            self.assertEqual(match['factory_id'],'PGCL')


if __name__ == '__main__':unittest.main()
