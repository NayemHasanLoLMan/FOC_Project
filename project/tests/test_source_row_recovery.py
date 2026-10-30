"""Readable source rows must survive grid splits, annotations and summaries."""
from pathlib import Path
import sys,unittest,tempfile
from unittest.mock import MagicMock,patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.ocr_engine import OCRResult,OCRTable,OCRTableCell,OCRWord,_reread_paddle_quantities
from src.foc_extractor.parser import parse_result,_table_fields
from src.foc_extractor.goods_grouping import summarize_goods
from src.foc_extractor.packages import _read_count
from src.foc_extractor.valuation import apply_valuation
from src.foc_extractor.models import FOCData,LineItem
from src.foc_extractor.weights import _weight_regions,packing_weight

class SourceRowRecoveryTests(unittest.TestCase):
    def test_decimal_disagreement_requires_an_independent_matching_reread(self):
        cells=[OCRTableCell(0,0,'PARTICULARS',bbox=[0,0,100,40]),
               OCRTableCell(0,1,'QTY',bbox=[100,0,200,40]),
               OCRTableCell(0,2,'WEIGHT / Kgs',bbox=[200,0,300,40]),
               OCRTableCell(1,1,'20 PCS',bbox=[100,40,200,150]),
               OCRTableCell(1,2,'0.5 KGS',bbox=[200,40,300,150])]
        ocr=OCRResult(pages=['PACKING LIST'],total_pages=1,tables=[OCRTable(cells,2,3,bbox=[0,0,300,150])],
                      words=[OCRWord('0.5 KGS',.99,215,65,285,100)])
        image=Image.new('RGB',(300,150),'white')
        for retry,expected in [('0.5 KGS',.5),('05 KGS',None)]:
            reader=MagicMock();reader.predict.side_effect=[
                [{'rec_texts':['05 KGS'],'rec_scores':[.99]}],[{'rec_texts':[retry],'rec_scores':[.99]}]]
            with tempfile.TemporaryDirectory() as directory:
                pdf=Path(directory)/'unseen.pdf';pdf.write_bytes(b'source')
                with patch('src.foc_extractor.weights._cached_page_image',return_value=image), \
                     patch('src.foc_extractor.weights._paddle_readers',return_value=(reader,None)), \
                     patch('src.foc_extractor.weights._packing_column_regions',return_value=[[200,40,300,150]]):
                    self.assertEqual(packing_weight(ocr,pdf)['total_kg'],expected)

    def ocr(self,rows):
        cells=[OCRTableCell(r,c,text) for r,row in enumerate(rows) for c,text in enumerate(row)]
        return OCRResult(tables=[OCRTable(cells,len(rows),len(rows[0]))])

    def test_sample_quantities_keep_their_units_and_all_counts(self):
        ocr=self.ocr([['PARTICULARS','QTY'],['BULK FABRIC SWATCHES\nStyle A\nStyle B\nStyle C','3 SETS\n1 SET\n1 SET']])
        data=parse_result(ocr,Path('unseen.pdf'))
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],[('FABRIC SWATCHES',5,'SETS')])

    def test_garment_blend_continuation_carries_quantity_and_source_condition(self):
        ocr=self.ocr([['PARTICULARS','QTY'],['NON-MUTILATED',''],
             ['Womens 75% Polyester 20% Rayon',''],['5% Elastane Woven Pant','4 PCS'],
             ['Womens 75% Polyester 20% Rayon',''],['5% Elastane Woven Top','2 PCS']])
        data=parse_result(ocr,Path('unseen.pdf'));summarize_goods(data,ocr)
        self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],
                         [("WOMEN'S 75% POLYESTER 20% RAYON 5% ELASTANE WOVEN (NON-MUTILATED)",6,'PCS')])
        self.assertEqual(len(data.items[0].source_refs),4)

    def test_shorts_and_leg_panels_do_not_become_fabric(self):
        ocr=self.ocr([['PARTICULARS','QTY'],['Girls 100% Cotton Denim Shorts (Half Leg Panel)','4 PCS'],
                       ['Girls 100% Cotton Woven Denim Shorts','2 PCS']])
        data=parse_result(ocr,Path('unseen.pdf'))
        self.assertTrue(all('SHORTS' in i.description for i in data.items))
        self.assertTrue(all('FABRICS' not in i.description for i in data.items))

    def test_missing_quantity_cell_is_read_without_inventing_a_unit(self):
        cells=[OCRTableCell(0,0,'PARTICULARS',bbox=[0,0,100,40]),
               OCRTableCell(0,1,'QTY',bbox=[100,0,160,40]),
               OCRTableCell(1,0,'100% Cotton Knit',bbox=[0,40,100,100])]
        for texts,scores,expected in [(['1'],[.99],1),([] ,[],0),(['1'],[.4],0),(['1 PCS'],[.4],0),(['0'],[.99],0)]:
            table=OCRTable(list(cells),2,2,bbox=[0,0,160,100]);reader=MagicMock()
            reader.predict.return_value=[{'rec_texts':texts,'rec_scores':scores}]
            _reread_paddle_quantities(Image.new('RGB',(160,100),'white'),[table],reader)
            recovered=[c for c in table.cells if c.row_index==1 and c.column_index==1]
            self.assertEqual(len(recovered),expected)
            if recovered:self.assertEqual(recovered[0].content,'1')

    def test_joined_package_header_does_not_select_gross_weight(self):
        table=self.ocr([['PARTICULARS','QTY','NET WEIGHT / Kgs','GROSS WEIGHT / No of package / Kgs','rolls'],
                        ['TRIM CARD','1 SET','0.05 KGS','0.05 KGS','1 PACKAGE']]).tables[0]
        fields,_=_table_fields(table)
        self.assertEqual((fields['weight'],fields['packages']),(3,4))

    def test_labelled_package_number_can_coexist_with_annotation(self):
        self.assertEqual(_read_count('FAB SMMOMES\n1',labelled=True),1)
        for text in ['FAB SMMOMES\n1','0.05 KGS','A1\n1','1\n2']:
            self.assertIsNone(_read_count(text))
        for text in ['0.05 KGS','A1\n1','1\n2']:
            self.assertIsNone(_read_count(text,labelled=True))

    def test_singleton_summary_and_approved_unitless_sample_price(self):
        data=FOCData(source_file='unseen.pdf',template_type='BD',items=[LineItem('INTERLINING #ABC',20,'YDS'),
            LineItem('FABRIC SAMPLES',2,None),LineItem('BUTTON',3,'G'),LineItem('27L SHANK',1,'G')])
        summarize_goods(data);apply_valuation(data)
        self.assertEqual(data.items[0].description,'INTERLINING')
        self.assertIsNone(data.items[1].unit)
        self.assertEqual((data.items[1].unit_price,data.items[1].amount),(.1,.2))
        self.assertEqual(data.items[2].unit,'GROSS')
        self.assertEqual((data.items[3].description,data.items[3].unit),('SHANK','GROSS'))

    def test_phantom_weight_gap_does_not_clip_leading_zero(self):
        cells=[OCRTableCell(0,0,'PARTICULARS',bbox=[0,0,100,40]),
               OCRTableCell(0,1,'QTY',bbox=[100,0,200,40]),
               OCRTableCell(0,3,'WEIGHT / Kgs',bbox=[220,0,300,40]),
               OCRTableCell(1,1,'20 PCS',bbox=[100,40,200,100]),
               OCRTableCell(1,3,'0.5 KGS',bbox=[220,40,300,100])]
        table=OCRTable(cells,2,4,bbox=[0,0,300,100])
        with patch('src.foc_extractor.weights._packing_column_regions',return_value=[]) as regions:
            _weight_regions(Image.new('RGB',(300,100),'white'),table,group_braces=False)
        self.assertEqual(regions.call_args.args[1],[200,40,300,100])

if __name__=='__main__':unittest.main()
