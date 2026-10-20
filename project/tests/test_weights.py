import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell, OCRWord
from src.foc_extractor.weights import _read_weight, _weight_regions, packing_weight


class WeightTests(unittest.TestCase):
    def test_failed_page_rechecks_printed_old_number_in_other_corrected_cell(self):
        image,table=self.table(False)
        ocr=OCRResult(pages=['PACKING LIST'],total_pages=1,tables=[table])
        reader=MagicMock();reader.predict.side_effect=[
            [{'rec_texts':['16kg','25'],'rec_scores':[.99,.99]}],
            [{'rec_texts':['8kg'],'rec_scores':[.99]}]]
        with tempfile.TemporaryDirectory() as directory:
            pdf=Path(directory)/'source.pdf';pdf.write_bytes(b'source')
            with patch('src.foc_extractor.weights._cached_page_image',return_value=image), \
                 patch('src.foc_extractor.weights._paddle_readers',return_value=(reader,None)), \
                 patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[
                     ({'weight_kg':25},'test (abc)'),({'weight_kg':12},'test (abc)')]):
                self.assertEqual(packing_weight(ocr,pdf,local_model='test')['total_kg'],37)

    def test_vision_splits_failed_brace_group_and_requires_complete_positive_weights(self):
        image,table=self.table(False)
        ImageDraw.Draw(image).line([(305,70),(310,100),(305,140),(305,180)],fill='blue',width=3)
        ocr=OCRResult(pages=['PACKING LIST'],total_pages=1,tables=[table])
        reader=MagicMock();reader.predict.return_value=[{'rec_texts':['16kg','25'],'rec_scores':[.99,.99]}]
        for second,total in [(1.5,4.0),(None,None),(0,None),(-1,None),(True,None),(float('nan'),None)]:
            with self.subTest(second=second),tempfile.TemporaryDirectory() as directory:
                pdf=Path(directory)/'renamed.pdf';pdf.write_bytes(b'source')
                with patch('src.foc_extractor.weights._cached_page_image',return_value=image), \
                     patch('src.foc_extractor.weights._paddle_readers',return_value=(reader,None)), \
                     patch('src.foc_extractor.local_vision.transcribe_cell',side_effect=[
                         ({'weight_kg':2.5},'test (abc)'),({'weight_kg':second},'test (abc)')]) as vision:
                    result=packing_weight(ocr,pdf,Path(directory)/'cache',local_model='test')
                self.assertEqual(result['total_kg'],total)
                self.assertEqual(vision.call_count,2)
                if total:
                    self.assertEqual(len(result['cells']),2)
                    self.assertTrue(all(c['method']=='local vision' for c in result['cells']))

    def table(self, shared):
        image=Image.new('RGB',(450,250),'white');draw=ImageDraw.Draw(image)
        for x in (10,150,300,400):draw.line((x,20,x,200),fill='black',width=2)
        for y in (20,60,200):draw.line((10,y,400,y),fill='black',width=2)
        draw.line((10,120,300 if shared else 400,120),fill='black',width=2)
        cells=[OCRTableCell(0,0,'DESCRIPTION',bbox=[10,20,150,60]),
               OCRTableCell(0,1,'QTY',bbox=[150,20,300,60]),
               OCRTableCell(0,2,'WEIGHT / Kgs',bbox=[300,20,400,60]),
               OCRTableCell(1,0,'LABEL',bbox=[10,60,150,120]),
               OCRTableCell(1,1,'2 PCS',bbox=[150,60,300,120]),
               OCRTableCell(2,0,'BUTTON',bbox=[10,120,150,200]),
               OCRTableCell(2,1,'3 PCS',bbox=[150,120,300,200])]
        return image,OCRTable(cells,3,3,bbox=[10,20,400,200])

    def test_shared_cells_count_once_and_missing_cells_block_partial_total(self):
        for shared,reads,expected in [(True,['3kg'],3),(False,['1kg','2kg'],3),
                                      (False,['1kg',''],None),(False,['0.1kg','0.2kg'],.3)]:
            image,table=self.table(shared)
            self.assertEqual(len(_weight_regions(image,table)),1 if shared else 2)
            reader=MagicMock();reader.predict.side_effect=[iter([{'rec_texts':[s] if s else [],'rec_scores':[.99] if s else []}]) for s in reads]
            ocr=OCRResult(pages=['PACKING LIST'],total_pages=1,tables=[table])
            with tempfile.TemporaryDirectory() as directory:
                pdf=Path(directory)/'anonymous.pdf';pdf.write_bytes(b'synthetic')
                with patch('src.foc_extractor.weights._cached_page_image',return_value=image),patch('src.foc_extractor.weights._paddle_readers',return_value=(reader,None)):
                    result=packing_weight(ocr,pdf,Path(directory)/'cache')
                    self.assertEqual(result['total_kg'],expected)
                    self.assertEqual(packing_weight(ocr,pdf,Path(directory)/'cache'),result)
                self.assertEqual(reader.predict.call_count,len(reads))

    def test_ambiguous_corrections_and_low_confidence_are_not_selected(self):
        self.assertEqual(_read_weight({'rec_texts':['2.5'],'rec_scores':[.9]}),2.5)
        for text,scores in [(['16kg','25'],[.99,.99]),(['2S'],[.99]),(['2.5'],[.5]),(['1','2'],[.99])]:
            self.assertIsNone(_read_weight({'rec_texts':text,'rec_scores':scores}))
        self.assertIsNone(packing_weight(OCRResult(pages=['PACKING LIST'],total_pages=2),Path('unused'))['total_kg'])

    def test_weight_units_must_be_established_from_header_or_cells(self):
        image,table=self.table(True)
        table.cells[2].content='WEIGHT / lbs'
        with self.assertRaises(ValueError):_weight_regions(image,table)
        table.cells.append(OCRTableCell(1,2,'2.4 KGS',bbox=[300,60,400,200]))
        self.assertEqual(len(_weight_regions(image,table)),1)
        with self.assertRaises(ValueError):_weight_regions(image,table,[OCRWord('QTY',x0=160,y0=25,x1=190,y1=45)])

    def test_coloured_brace_groups_rows_but_separate_blanks_still_fail(self):
        image,table=self.table(False)
        draw=ImageDraw.Draw(image)
        draw.line([(305,70),(310,100),(305,140),(305,180)],fill='blue',width=3)
        self.assertEqual(_weight_regions(image,table),[[300,60,400,200]])
        self.assertEqual(_read_weight({'rec_texts':['IKG'],'rec_scores':[.98]}),1)
        self.assertIsNone(_read_weight({'rec_texts':['IKG'],'rec_scores':[.5]}))

    def test_phantom_kg_column_does_not_clip_the_leading_digit(self):
        image,table=self.table(True)
        table.cells[2].column_index=3
        table.cells[2].bbox[0]=320
        table.cells.append(OCRTableCell(1,2,'KG',bbox=[300,60,320,200]))
        self.assertEqual(_weight_regions(image,table),[[300,60,400,200]])

    def test_net_weight_conflicting_with_gross_stays_blank(self):
        from src.foc_extractor.pipeline import run
        with tempfile.TemporaryDirectory() as directory,patch('src.foc_extractor.pipeline.analyze_pdf',return_value=OCRResult(content='G.W. 2.4 KGS N.W. 2.7 KGS')):
            output=run(ROOT/'examples/26S5075-D.pdf',output_dir=Path(directory))
            import openpyxl
            wb=openpyxl.load_workbook(output)
            self.assertEqual(wb.active['G27'].value,2.4)
            self.assertIsNone(wb.active['G28'].value)
            wb.close()

    def test_declared_gross_weight_keeps_priority(self):
        from src.foc_extractor.pipeline import run
        with tempfile.TemporaryDirectory() as directory,patch('src.foc_extractor.pipeline.analyze_pdf',return_value=OCRResult(content='G.W. 9 KGS')),patch('src.foc_extractor.weights.packing_weight') as fallback:
            output=run(ROOT/'examples/26S5075-D.pdf',output_dir=Path(directory))
            import openpyxl
            wb=openpyxl.load_workbook(output)
            self.assertEqual(wb.active['G27'].value,9)
            wb.close();fallback.assert_not_called()
