import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import tempfile
import cv2  # Keep the native extension loaded across sys.modules mock contexts.
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell


class OCRTests(unittest.TestCase):
    def test_partial_width_body_rules_keep_single_table_goods_inside_bounds(self):
        from PIL import Image,ImageDraw
        from src.foc_extractor.ocr_engine import _grid_tables,OCRWord
        image=Image.new('RGB',(1600,1100),'white');draw=ImageDraw.Draw(image)
        for x in (40,300,600,850,1100,1320,1560):draw.line((x,180,x,700),fill='black',width=2)
        for y in (180,280):draw.line((40,y,1560,y),fill='black',width=2)
        for y in (450,550,700):draw.line((850,y,1560,y),fill='black',width=2)
        words=[OCRWord('PARTICULARS',.99,900,210,1050,240),OCRWord('QTY',.99,1150,210,1210,240),
               OCRWord('COTTON',.99,900,470,1050,510),OCRWord('10 YDS',.99,1150,470,1250,510)]
        tables=_grid_tables(image,words,0)
        self.assertEqual(len(tables),1)
        self.assertTrue(any(c.content=='10 YDS' and c.row_index>0 for c in tables[0].cells))

    def test_sloping_horizontal_rules_recover_complete_rows(self):
        from PIL import Image,ImageDraw
        from src.foc_extractor.ocr_engine import _grid_tables,OCRWord
        image=Image.new('RGB',(2400,1400),'white');draw=ImageDraw.Draw(image)
        for x in (80,600,1300,1800,2300):draw.line((x,150,x,1100),fill='black',width=2)
        for y in (150,350,700,1100):draw.line((80,y,2300,y+25),fill='black',width=1)
        words=[OCRWord('PARTICULARS',.99,650,200,1000,240),OCRWord('QTY',.99,1400,200,1500,240),
               OCRWord('COTTON',.99,650,450,1000,490),OCRWord('25 YDS',.99,1400,450,1510,490)]
        tables=_grid_tables(image,words,0)
        self.assertEqual(len(tables),1)
        self.assertEqual([(c.row_index,c.column_index,c.content) for c in tables[0].cells],
                         [(0,1,'PARTICULARS'),(0,2,'QTY'),(1,1,'COTTON'),(1,2,'25 YDS')])

    def test_paddle_crop_recovery_keeps_source_unit_and_skips_known_values(self):
        from PIL import Image
        from src.foc_extractor.ocr_engine import _reread_paddle_quantities
        cells=[OCRTableCell(0,0,'DESCRIPTION'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'FABRIC'),OCRTableCell(1,1,'gyds',bbox=[0,0,80,50]),
               OCRTableCell(2,1,'7yds',bbox=[0,50,80,100]),
               OCRTableCell(3,1,'Z YARDS',bbox=[0,100,80,150])]
        reader=MagicMock();reader.predict.side_effect=[
            [{'rec_texts':['9yds'],'rec_scores':[.8]}],
            [{'rec_texts':['2 PCS'],'rec_scores':[.99]}]]
        _reread_paddle_quantities(Image.new('RGB',(80,150),'white'),[OCRTable(cells,4,2)],reader)
        self.assertEqual((cells[3].content,cells[3].original_content),('9yds','gyds'))
        self.assertEqual(cells[4].content,'7yds')
        self.assertEqual(cells[5].content,'Z YARDS')
        self.assertEqual(reader.predict.call_count,2)

    def test_paddle_preserves_coordinates_transform_and_resumes_without_model_calls(self):
        import pymupdf
        from PIL import Image
        from types import ModuleType
        from src.foc_extractor import ocr_engine
        reader=MagicMock();orientation=MagicMock()
        orientation.predict.return_value=[{'label_names':['90']}]
        reader.predict.return_value=[{'rec_texts':['LABEL 4 PCS'],'rec_scores':[.99],'rec_boxes':[[10,20,80,35]]}]
        sdk=ModuleType('paddleocr');sdk.PaddleOCR=MagicMock();sdk.DocImgOrientationClassification=MagicMock()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pdf=root/'new.pdf'
            with pymupdf.open() as document:
                document.new_page();document.new_page();document.save(pdf)
            (root/'cache').mkdir()
            (root/'cache/0.json').write_text('{broken')
            with patch.dict(sys.modules,{'paddleocr':sdk}), \
                 patch.object(ocr_engine,'_PADDLE_READERS',(reader,orientation),create=True), \
                 patch.object(ocr_engine,'_pdf_to_images',side_effect=lambda *a,**k:iter([(0,Image.new('RGB',(300,400),'white'))])), \
                 patch.object(ocr_engine,'_skew_angle',return_value=.25):
                first=ocr_engine.analyze_with_paddle(pdf,max_pages=1,page_cache_dir=root/'cache')
                second=ocr_engine.analyze_with_paddle(pdf,max_pages=1,page_cache_dir=root/'cache')
            self.assertEqual(first,second)
            self.assertEqual(first.page_transforms,[{'rotation':90,'skew':.25}])
            self.assertEqual((first.words[0].x0,first.words[0].page,first.dpi),(10,0,300))
            self.assertTrue(first.warnings)
            reader.predict.assert_called_once();orientation.predict.assert_called_once()


    def test_invalid_cache_is_rebuilt(self):
        import hashlib
        from src.foc_extractor.ocr_engine import analyze_pdf
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);pdf=root/'source.pdf';pdf.write_bytes(b'pdf')
            digest=hashlib.sha256(b'pdfpaddle-mobile-v1:3.7.0:3.2.0:None:300').hexdigest()
            (root/(digest+'.json')).write_text('{"broken":true}')
            with patch('src.foc_extractor.ocr_engine.analyze_with_paddle',return_value=OCRResult(content='recovered')) as analyze:
                result=analyze_pdf(pdf,cache_dir=root)
            analyze.assert_called_once()
            self.assertEqual(result.content,'recovered')

    def test_skew_accepts_installed_opencv_line_shape(self):
        from PIL import Image, ImageDraw
        from src.foc_extractor.ocr_engine import _skew_angle
        image=Image.new('RGB',(600,400),'white')
        draw=ImageDraw.Draw(image)
        for y in (50,150,250,350):draw.line((20,y,580,y),fill='black',width=2)
        self.assertAlmostEqual(_skew_angle(image),0,places=1)

    def test_grid_cells_use_word_coordinates(self):
        from PIL import Image, ImageDraw
        from src.foc_extractor.ocr_engine import _grid_tables, OCRWord
        image=Image.new('RGB',(800,500),'white');draw=ImageDraw.Draw(image)
        for x in (20,200,400,600,780):draw.line((x,40,x,460),fill='black',width=2)
        for y in (40,100,250,460):draw.line((20,y,780,y),fill='black',width=2)
        tables=_grid_tables(image,[OCRWord('PARTICULARS',.99,220,50,350,70),OCRWord('QTY',.99,420,50,460,70)],0)
        self.assertEqual(len(tables),1)
        self.assertEqual([(c.row_index,c.column_index,c.content) for c in tables[0].cells],[(0,1,'PARTICULARS'),(0,2,'QTY')])

    def test_grid_recovers_vertical_rules_interrupted_by_row_gutters(self):
        from PIL import Image, ImageDraw
        from src.foc_extractor.ocr_engine import _grid_tables, OCRWord
        image=Image.new('RGB',(800,500),'white');draw=ImageDraw.Draw(image)
        for x in (20,780):draw.line((x,40,x,460),fill='black',width=2)
        for x in (200,400,600):
            for top in range(40,460,60):draw.line((x,top,x,top+50),fill='black',width=2)
        for y in (40,100,160,220,280,340,400,460):draw.line((20,y,780,y),fill='black',width=2)
        tables=_grid_tables(image,[OCRWord('PARTICULARS',.99,220,50,350,70),OCRWord('QTY',.99,420,50,460,70)],0)
        self.assertEqual(tables[0].column_count,4)
        self.assertIsNotNone(tables[0].cells[0].bbox)

    def test_short_single_row_table_is_detected(self):
        from PIL import Image, ImageDraw
        from src.foc_extractor.ocr_engine import _grid_tables, OCRWord
        image=Image.new('RGB',(800,1000),'white');draw=ImageDraw.Draw(image)
        for x in (20,200,400,600,780):draw.line((x,40,x,190),fill='black',width=2)
        for y in (40,100,190):draw.line((20,y,780,y),fill='black',width=2)
        tables=_grid_tables(image,[OCRWord('PARTICULARS',.99,220,50,350,70),OCRWord('QTY',.99,420,50,460,70)],0)
        self.assertEqual(tables[0].column_count,4)

    def test_grid_keeps_slightly_leaning_column_rules(self):
        from PIL import Image,ImageDraw
        from src.foc_extractor.ocr_engine import _grid_tables
        image=Image.new('RGB',(1600,1100),'white');draw=ImageDraw.Draw(image)
        for x in (50,350,650,950,1250,1550):draw.line((x,180,x-12,800),fill='black',width=2)
        for y in (180,260,400,600,800):draw.line((38,y,1550,y),fill='black',width=2)
        tables=_grid_tables(image,[],0)
        self.assertEqual(tables[0].column_count,5)

    def test_grid_recovers_leaning_rules_without_morphology_support(self):
        from PIL import Image,ImageDraw
        from src.foc_extractor.ocr_engine import _grid_tables
        image=Image.new('RGB',(1600,1100),'white');draw=ImageDraw.Draw(image)
        for x in (50,350,650,950,1250,1550):draw.line((x,180,x-12,900),fill='black',width=1)
        for y in (180,280,450,650,900):draw.line((38,y,1550,y),fill='black',width=1)
        tables=_grid_tables(image,[],0)
        self.assertEqual(tables[0].column_count,5)
