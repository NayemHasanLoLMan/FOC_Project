from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.parser import parse_result,_material_heading,_clean_material_description
from src.foc_extractor.ocr_engine import OCRResult,OCRTable,OCRTableCell,OCRWord
from src.foc_extractor.india import resolve_annotations
from src.foc_extractor.processing_evidence import observed


def document(rows):
    return OCRResult(pages=['PACKING LIST'],total_pages=1,tables=[OCRTable(
        [OCRTableCell(r,c,v,bbox=[c*250,r*70,(c+1)*250,(r+1)*70])
         for r,row in enumerate(rows) for c,v in enumerate(row) if v],len(rows),max(map(len,rows)),bbox=[0,0,1000,len(rows)*70])])


class DescriptionTests(unittest.TestCase):
    def test_fiber_modifiers_and_measurement_tolerance_preserve_material(self):
        for source,expected in [
            ('55% US Cotton 20% PCW Recycled Polyester 25% Polyester','55% US COTTON 20% PCW RECYCLED POLYESTER 25% POLYESTER WOVEN FABRICS'),
            ('65%GRS Polyester 35%Cotton','65% GRS POLYESTER 35% COTTON WOVEN FABRICS'),
            ('BULK YARDAGE CARGO PANT\n100% BCl Cotton Canvas (BW +/- 5%)','100% COTTON WOVEN FABRICS')]:
            self.assertEqual(_material_heading(source,'WOVEN'),expected)
        for source in ('55% COTTON 45% UNKNOWN','100% COTTON 5% UNKNOWN',
                       '65% GRS POLYESTER 30% COTTON','100% COTTON (5% UNKNOWN)'):
            self.assertIsNone(_material_heading(source,'WOVEN'))

    def test_style_metadata_does_not_reset_composition_but_new_product_does(self):
        ocr=document([['SENDER','PARTICULARS','QTY','WOVEN / KNIT'],
                      ['MILL','100% COTTON WOVEN CHAMBRAY','','WOVEN'],
                      ['','item: FBN0000','',''],['','style : AE Chambray shirts','',''],
                      ['','col. Rinsed','3 YDS',''],['','col. Blue','4 YDS',''],
                      ['OTHER','ZIPPER','2 PCS',''],['','COL. RED','1 PCS','']])
        data=parse_result(ocr,Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],
                         [('100% COTTON WOVEN FABRICS',7),('ZIPPER',2),('COL. RED',1)])

    def test_joined_die_and_singular_garment_cleanup_are_idempotent(self):
        for source,expected in [('RIVETDIE MOULD','DIE MOULD (RIVET)'),
            ("WOVEN\nWomen's Pant - 65% COTTON 30% POLYESTER 3% RAYON 2% SPANDEX, RIGHT STRETCH DENIM 92X65", 
             "WOMEN'S 65% COTTON 30% POLYESTER 3% RAYON 2% SPANDEX WOVEN PANT")]:
            self.assertEqual(_clean_material_description(source),expected)
            self.assertEqual(_clean_material_description(expected),expected)
        self.assertEqual(_clean_material_description('MIXED SNAP SHANK DIE MOULD'),'MIXED SNAP SHANK DIE MOULD')
        self.assertIn('UNKNOWN',_clean_material_description("WOVEN Women's Pant - 90% COTTON 10% UNKNOWN"))

    def test_header_and_quantity_notes_are_scoped_and_keep_annotation_refs(self):
        ocr=document([['SENDER','PARTICULARS FAB SMATOMES','QTY'],
                      ['ONE','BULK DYE LOT CUTTING','40 PCS'],
                      ['TWO','TRIM DEVELOPMENT',''],['','PIPING','TRIM CARDS'],
                      ['','PLASTIC BUTTON','2 PCS'],['THREE','ZIPPER','3 PCS']])
        data=parse_result(ocr,Path('anonymous.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [('FABRIC SAMPLES',40,'PCS'),('TRIM CARD',2,'PCS'),('ZIPPER',3,'PCS')])
        self.assertEqual(data.items[0].source_refs,['1:1:2','1:1:1'])
        self.assertEqual(data.items[1].source_refs,['1:1:5','1:1:4'])

    def test_unclear_header_weight_notes_use_bounded_reader_once_and_reject_guesses(self):
        for column,row in [(0,0),(2,1)]:
            with self.subTest(column=column,row=row):
                ocr=document([['PARTICULARS','QTY','WEIGHT'],['100% COTTON','2 PCS','']])
                cell=next((c for c in ocr.tables[0].cells if c.row_index==row and c.column_index==column),None)
                if cell is None:
                    cell=OCRTableCell(row,column,'',bbox=[500,70,750,140]);ocr.tables[0].cells.append(cell)
                cell.content+=' FAB SMATOMES'
                with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(1000,250))), \
                     patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':'FAB SWATCHES'},'test')) as reader:
                    refs=resolve_annotations(ocr,Path('anonymous.pdf'),'local')
                    self.assertTrue(refs)
                    self.assertFalse(resolve_annotations(ocr,Path('anonymous.pdf'),'local'))
                    reader.assert_called_once()
                data=parse_result(ocr,Path('anonymous.pdf'))
                self.assertEqual(data.items[0].description,'FABRIC SWATCHES')
                self.assertEqual((data.items[0].quantity,data.items[0].unit),(2,'PCS'))
        ocr=document([['PARTICULARS','QTY','WEIGHT'],['FAB SMATOMES','1','']])
        with patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(1000,250))), \
             patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':'invent 20 yds'},'test')):
            self.assertFalse(resolve_annotations(ocr,Path('anonymous.pdf'),'local'))
        data=parse_result(ocr,Path('anonymous.pdf'))
        self.assertEqual(data.items[0].quantity,1)
        self.assertIsNone(data.items[0].unit)

    def test_bd_pipeline_calls_annotation_reader_and_records_its_contribution(self):
        import tempfile
        from src.foc_extractor.pipeline import run
        ocr=document([['PARTICULARS FAB SMATOMES','QTY'],['DYE LOT CUTTING','2 PCS']])
        events=[]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pdf=root/'anonymous.pdf';pdf.write_bytes(b'ocr-boundary-test')
            with patch('src.foc_extractor.pipeline.analyze_pdf',return_value=ocr), \
                 patch('src.foc_extractor.local_vision.resolve_quantities'), \
                 patch('src.foc_extractor.packages.packing_packages',return_value={'total':None,'basis':'unavailable','reason':None,'entries':[]}), \
                 patch('src.foc_extractor.weights.packing_weight',return_value={'total_kg':None,'reason':None,'cells':[]}), \
                 patch('src.foc_extractor.ocr_engine._cached_page_image',return_value=Image.new('RGB',(1000,250))), \
                 patch('src.foc_extractor.local_vision.transcribe_cell',return_value=({'text':'FAB SWATCHES'},'test')):
                run(pdf,output_dir=root/'out',local_model='local',region='BD',observer=lambda e,**kw:events.append(e))
        evidence=next(e for e in events if e['kind']=='invoice_evidence')
        self.assertEqual(evidence['goods'][0]['description'],'FABRIC SWATCHES')
        self.assertIn({'field':'goods_description','source_ref':'1:1:1'},evidence['vision_contributions'])


if __name__=='__main__':unittest.main()
