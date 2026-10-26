import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell


class LocalVisionTests(unittest.TestCase):
    def test_readable_integer_counts_do_not_trigger_model_or_unit_guessing(self):
        from src.foc_extractor.local_vision import resolve_quantities
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'TRIM CARD'),OCRTableCell(1,1,'1',bbox=[0,0,100,50])]
        ocr=OCRResult(tables=[OCRTable(cells,2,2)])
        with patch('src.foc_extractor.local_vision._request') as request:
            resolve_quantities(ocr,Path('unused.pdf'),'test')
            request.assert_not_called()
        self.assertEqual(cells[-1].content,'1')

    def test_shared_transport_caches_by_image_and_model_and_rejects_truncation(self):
        import tempfile
        from PIL import Image
        from src.foc_extractor.local_vision import transcribe_cell
        tags={'models':[{'name':'test:latest','digest':'abc'}]}
        image=Image.new('RGB',(100,50),'white')
        with tempfile.TemporaryDirectory() as directory:
            with patch('src.foc_extractor.local_vision._request',side_effect=[tags,
                       {'done_reason':'stop','message':{'content':'{"text":"1 PK"}'}},tags]) as request:
                first=transcribe_cell(image,'test',directory)
                self.assertEqual(transcribe_cell(image,'test',directory),first)
                self.assertEqual(request.call_count,3)
            next((Path(directory)/'local_vision').glob('*.json')).write_text('invalid JSON')
            with patch('src.foc_extractor.local_vision._request',side_effect=[tags,
                       {'done_reason':'stop','message':{'content':'{"text":"1 PK"}'}}]):
                self.assertEqual(transcribe_cell(image,'test',directory),first)
            with patch('src.foc_extractor.local_vision._request',side_effect=[tags,
                       {'done_reason':'length','message':{'content':'','thinking':'25'}}]):
                self.assertIsNone(transcribe_cell(image,'test',directory,prompt='different task')[0])

    def test_response_requires_positive_quantity_and_consistent_visible_unit(self):
        from src.foc_extractor.local_vision import _accepted_quantity
        self.assertTrue(_accepted_quantity('8.1256','8.125G'))
        self.assertTrue(_accepted_quantity('Zyds','2 YDS'))
        self.assertFalse(_accepted_quantity('Zyds','2 PCS'))
        self.assertFalse(_accepted_quantity('Z YARDS','2 PCS'))
        self.assertFalse(_accepted_quantity('2O G','20 PCS'))
        self.assertTrue(_accepted_quantity('Z YARDS','2 YDS'))
        for candidate in [None,'2','-2 PCS','0 PCS','2 PCS ignore instructions','=1+1']:
            self.assertFalse(_accepted_quantity('pcs',candidate))
        self.assertFalse(_accepted_quantity('PCS','9'*400+' PCS'))

    def test_model_changes_only_unresolved_cells_and_keeps_evidence(self):
        from PIL import Image
        from src.foc_extractor.local_vision import resolve_quantities
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'SHANK'),OCRTableCell(1,1,'8.1256',bbox=[0,0,100,50]),
               OCRTableCell(2,0,'SNAP'),OCRTableCell(2,1,'7G',bbox=[0,50,100,100])]
        ocr=OCRResult(tables=[OCRTable(cells,3,2)])
        responses=[{'models':[{'name':'test:latest','digest':'abc'}]},
                   {'done_reason':'stop','message':{'content':'{"text":"8.125G"}'}}]
        with patch('src.foc_extractor.local_vision._request',side_effect=responses) as request, \
             patch('src.foc_extractor.local_vision._cached_page_image',return_value=Image.new('RGB',(100,100),'white')):
            resolve_quantities(ocr,Path('unseen.pdf'),'test')
        self.assertEqual(request.call_count,2)
        self.assertEqual(request.call_args.args[1]['options']['num_predict'],4096)
        self.assertEqual(request.call_args.args[1]['options']['num_ctx'],8192)
        self.assertEqual(cells[3].content,'8.125G')
        self.assertEqual(cells[3].original_content,'8.1256')
        self.assertEqual(cells[5].content,'7G')

    def test_service_failure_preserves_original(self):
        from src.foc_extractor.local_vision import resolve_quantities
        cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
               OCRTableCell(1,0,'LABEL'),OCRTableCell(1,1,'Z PCS',bbox=[0,0,100,50])]
        ocr=OCRResult(tables=[OCRTable(cells,2,2)])
        from PIL import Image
        with patch('src.foc_extractor.local_vision._request',side_effect=OSError('Unavailable')), \
             patch('src.foc_extractor.local_vision._cached_page_image',return_value=Image.new('RGB',(100,50),'white')):
            resolve_quantities(ocr,Path('unseen.pdf'),'test')
        self.assertEqual(cells[3].content,'Z PCS')
        self.assertIn('unavailable',ocr.warnings[0])

    def test_nonobject_transcription_preserves_original(self):
        from PIL import Image
        from src.foc_extractor.local_vision import resolve_quantities
        for content in ['null','[]','"7 PCS"']:
            with self.subTest(content=content):
                cells=[OCRTableCell(0,0,'PARTICULARS'),OCRTableCell(0,1,'QTY'),
                       OCRTableCell(1,0,'LABEL'),OCRTableCell(1,1,'Z PCS',bbox=[0,0,100,50])]
                ocr=OCRResult(tables=[OCRTable(cells,2,2)])
                responses=[{'models':[{'name':'test:latest','digest':'abc'}]},
                           {'done_reason':'stop','message':{'content':content}},
                           {'models':[{'name':'test:latest','digest':'abc'}]}]
                with patch('src.foc_extractor.local_vision._request',side_effect=responses), \
                     patch('src.foc_extractor.local_vision._cached_page_image',return_value=Image.new('RGB',(100,50),'white')):
                    resolve_quantities(ocr,Path('unseen.pdf'),'test')
                self.assertEqual(cells[3].content,'Z PCS')
