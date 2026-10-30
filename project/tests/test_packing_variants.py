"""Punctuation and shared-weight declarations are source variants, not shipment overrides."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.factory_profiles import identify_factory
from src.foc_extractor.ocr_engine import OCRResult,OCRTable,OCRTableCell,OCRWord
from src.foc_extractor.parser import _quantity_text,_extract_shipping_marks,QTY_UNIT,parse_result
from src.foc_extractor.local_vision import _accepted_quantity
from src.foc_extractor.weights import _weight_regions,_shared_weight


class PackingVariantTests(unittest.TestCase):
    def test_split_fabric_rows_use_each_composition_and_keep_quantities(self):
        descriptions=['WM OVERALL MILL REF A 100% BCI COTTON TWILL / SHRINKAGE: 3% X3% COLOR KHAKI',
                      'WM SHORT MILL REF B 98% COTTON 2% SPANDEX POPLIN / SHRINKAGE:\n3% X3% COLOR BLUE']
        rows=[['WOVEN / KNIT','PARTICULARS','QTY'],
              ['WOVEN','\n'.join(descriptions),'25 YDS\n50 YDS']]
        cells=[OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)]
        data=parse_result(OCRResult(tables=[OCRTable(cells,2,3)]),Path('unseen.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('100% COTTON WOVEN FABRICS',25,'YDS'),
                          ('98% COTTON 2% SPANDEX WOVEN FABRICS',50,'YDS')])

    def test_dotted_foc_keeps_exact_factory_and_shipping_mark(self):
        for name,expected in [('PGCL - F.O.C. (#5)','PGCL'),('CIPL F.O.C. (#12)','CIPL'),
                              ('NEW PGCL - F.O.C. (#5)',None),('EGMCL UNIT 3 F.O.C.',None)]:
            text='To: '+name+'\nPACKING LIST'
            self.assertEqual(identify_factory(OCRResult(content=text,pages=[text]),'BD',name)['factory_id'],expected)
        self.assertEqual(_extract_shipping_marks('PGCL - F.O.C. (#5)'),'PGCL-FOC')

    def test_middle_dot_before_unit_does_not_change_digits(self):
        for text,qty in [('3·PCS',3),('2.5·YDS',2.5),('12 · SETS',12)]:
            self.assertEqual(float(QTY_UNIT.fullmatch(_quantity_text(text))['qty']),qty)
            self.assertTrue(_accepted_quantity(text,text))
        for text in ['3·5PCS','3·PCS5','3·PCS 5','3·PCS YDS']:
            self.assertFalse(_accepted_quantity(text,text))

    def table(self):
        cells=[OCRTableCell(0,n,label,bbox=[n*100,0,(n+1)*100,40]) for n,label in enumerate(
            ['DESCRIPTION','QTY','NET WEIGHT / Kgs','GROSS WEIGHT / Kgs'])]
        cells += [OCRTableCell(1,0,'BUTTON',bbox=[0,40,100,160]),
                  OCRTableCell(1,1,'3 PCS',bbox=[100,40,200,160]),
                  OCRTableCell(1,2,'2 KG',bbox=[200,40,300,160])]
        return OCRTable(cells,2,4,bbox=[0,0,400,160])

    def test_explicit_gross_header_beats_net_column_unit_score(self):
        table=self.table()
        with patch('src.foc_extractor.weights._packing_column_regions',return_value=[]) as regions:
            _weight_regions(Image.new('RGB',(450,200),'white'),table)
        self.assertEqual(regions.call_args.args[1],[300,40,400,160])

    def test_shared_weight_needs_readable_ocr_and_explicit_vision_grouping(self):
        table=self.table();image=Image.new('RGB',(450,200),'white')
        ocr=OCRResult(words=[OCRWord('0.3 KGS',x0=320,y0=60,x1=390,y1=80)])
        cells=[{'bbox':[300,40,400,100]},{'bbox':[300,100,400,160]}]
        for check,expected in [({'text':'SHARED'},.3),({'text':None},None),({'text':'3'},None)]:
            with patch('src.foc_extractor.local_vision.transcribe_cell',return_value=(check,'reader')) as read:
                result=_shared_weight(image,table,ocr,cells,'qwen3-vl:latest',None)
                self.assertEqual(result['weight_kg'] if result else None,expected)
                self.assertEqual(read.call_count,1)
                self.assertEqual(result['weight_kg'] if result else None,expected)
        ocr.words.append(OCRWord('2 KG',x0=320,y0=110,x1=390,y1=130))
        with patch('src.foc_extractor.local_vision.transcribe_cell') as read:
            self.assertIsNone(_shared_weight(image,table,ocr,cells,'qwen3-vl:latest',None))
            read.assert_not_called()


if __name__=='__main__':unittest.main()
