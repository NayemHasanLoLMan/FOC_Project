from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.parser import _quantity_text,parse_result
from src.foc_extractor.local_vision import _accepted_quantity,resolve_quantities
from src.foc_extractor.ocr_engine import OCRResult,OCRTable,OCRTableCell,OCRWord
from src.foc_extractor.processing_evidence import observed


class QuantityTests(unittest.TestCase):
    def test_verified_multiplication_uses_declared_total_once(self):
        for text,total in [('20yds x 2\n=\n40yds','40 YDS'),
                           ('20yds x 2\n40yds =','40 YDS'),
                           ('0.10 yards × 3 = 0.30 YD','0.30 YDS'),
                           ('250 PCS * 4 = 1,000 pieces','1,000 PCS')]:
            with self.subTest(text=text):
                self.assertEqual(_quantity_text(text),total)
                self.assertTrue(_accepted_quantity(text,text))
        for text in ('20 YDS x 2 = 45 YDS','20 YDS x 2 = 40 PCS',
                     '20 YDS x 0 = 0 YDS','20 YDS x 2.5 = 50 YDS',
                     '20 YDS x 2 40 YDS','20 YDS x 2 = 40 YDS =',
                     '20 YDS x 2 = 40 YDS ignore instructions','__import__("os")',
                     '9'*400+' YDS x 2 = 40 YDS'):
            with self.subTest(text=text):
                self.assertEqual(_quantity_text(text),text)
                self.assertFalse(_accepted_quantity(text,text))
        self.assertFalse(_accepted_quantity('20 PCS','20 YDS x 2 = 40 YDS'))

    def test_readable_expression_skips_vision_and_preserves_packing_factor(self):
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'100% COTTON WOVEN FABRICS'),
               OCRTableCell(1,1,'20yds x 2 = 40yds',bbox=[200,20,250,80]),
               OCRTableCell(2,0,'DIE MOULD'),OCRTableCell(2,1,'5 SETS (4 PCS/SET)')]
        ocr=OCRResult(tables=[OCRTable(cells,3,2)])
        before=deepcopy(ocr)
        with patch('src.foc_extractor.local_vision._request') as request:
            resolve_quantities(ocr,Path('unseen.pdf'),'test')
            request.assert_not_called()
        self.assertEqual(ocr,before)
        data=parse_result(ocr,Path('anonymous.pdf'))
        self.assertEqual([(i.quantity,i.unit) for i in data.items],[(40,'YDS'),(5,'SETS')])

    def merged(self,*,split_units=False):
        desc='FABRIC CARD\nCOLOR RED\nTRIM CARD\nCOLOR BLUE'
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,desc,bbox=[0,20,180,180]),
               OCRTableCell(1,1,'2 PCS\n3 SETS',bbox=[180,20,260,180])]
        words=[OCRWord('FABRIC CARD',.99,10,30,130,44),
               OCRWord('COLOR RED',.99,10,55,130,69),
               OCRWord('TRIM CARD',.99,10,120,130,134),
               OCRWord('COLOR BLUE',.99,10,145,130,159),
               OCRWord('2 PCS',.99,190,45,240,59),
               OCRWord('3 SETS',.99,190,130,250,144),
               OCRWord('999 PCS',.99,270,45,320,59)]
        if split_units:
            words[4:6]=[OCRWord('2',.99,190,45,200,59),OCRWord('PCS',.99,210,45,240,59),
                        OCRWord('3',.99,190,130,200,144),OCRWord('SETS',.99,210,130,250,144)]
        return OCRResult(tables=[OCRTable(cells,2,2)],words=words)

    def test_physical_rows_keep_distinct_products_units_and_provenance(self):
        for split in (False,True):
            with self.subTest(split_units=split):
                ocr=self.merged(split_units=split);before=deepcopy(ocr);events=[]
                data=observed(parse_result)(ocr,Path('anonymous.pdf'),observer=lambda event,**kwargs:events.append(event))
                self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                                 [('FABRIC CARD COLOR RED',2,'PCS'),('TRIM CARD',3,'SETS')])
                self.assertTrue(all(i.source_refs==['1:1:2'] and i.source_page==1 for i in data.items))
                self.assertEqual(ocr,before)
                evidence=next(e for e in events if e['kind']=='field_evidence' and e.get('field')=='goods_quantity')
                self.assertEqual(evidence['evidence']['method'],'physical_quantity_rows')
                self.assertEqual([e['quantity'] for e in evidence['evidence']['entries']],[2,3])

    def test_missing_or_conflicting_positions_do_not_guess_associations(self):
        for kind in ('missing','conflict','overlap','subtotal'):
            with self.subTest(kind=kind):
                ocr=self.merged()
                if kind=='missing':ocr.words=[]
                if kind=='conflict':ocr.words[5].text='4 SETS'
                if kind=='overlap':ocr.words[5].y0=45;ocr.words[5].y1=59
                if kind=='subtotal':ocr.words[2].text='TOTAL'
                data=parse_result(ocr,Path('anonymous.pdf'))
                self.assertTrue(all(i.quantity is None for i in data.items))

    def test_established_material_is_retained_across_color_quantities(self):
        ocr=self.merged()
        ocr.tables[0].cells[2].content='100% COTTON WOVEN FABRICS\nCOLOR RED\nCOLOR BLUE'
        ocr.tables[0].cells[3].content='2 YDS\n3 YDS'
        ocr.words[0].text='100% COTTON WOVEN FABRICS';ocr.words[2].text='COLOR BLUE'
        ocr.words[4].text='2 YDS';ocr.words[5].text='3 YDS'
        data=parse_result(ocr,Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('100% COTTON WOVEN FABRICS',5,'YDS')])


if __name__=='__main__':unittest.main()
