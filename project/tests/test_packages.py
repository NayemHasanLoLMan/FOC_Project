import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell, OCRWord
from src.foc_extractor.packages import _read_count, _carton_ids, packing_packages


class PackageTests(unittest.TestCase):
    def test_vision_recovers_missing_number_but_cannot_change_legible_package_kind(self):
        image,o=self.physical();o.words[-1].text='PK'
        reader=MagicMock();reader.predict.return_value=[{'rec_texts':['PK'],'rec_scores':[.95]}]
        for answer,total in [({'text':'1 PKS'},1),({'text':'1 roll'},None),({'text':'1 KG'},None),(None,None)]:
            with self.subTest(answer=answer),patch('src.foc_extractor.packages._cached_page_image',return_value=image), \
                 patch('src.foc_extractor.packages._paddle_readers',return_value=(reader,None)), \
                 patch('src.foc_extractor.local_vision.transcribe_cell',return_value=(answer,'test (abc)')):
                result=packing_packages(o,pdf='unused.pdf',local_model='test')
                self.assertEqual(result['total'],total)

    def table(self, values, page=0):
        rows=[['PARTICULARS','QTY','No of package / rolls']]+[[f'ITEM {n}','2 PCS',v] for n,v in enumerate(values)]
        return OCRTable([OCRTableCell(r,c,v,page=page) for r,row in enumerate(rows) for c,v in enumerate(row)],len(rows),3,page)

    def physical(self, shared=True, clipped=False):
        image=Image.new('RGB',(600,240),'white');d=ImageDraw.Draw(image)
        for x in (10,150,300,400,590):d.line((x,20,x,200),fill='black',width=2)
        for y in (20,60,200):d.line((10,y,590,y),fill='black',width=2)
        d.line((10,120,400 if shared else 590,120),fill='black',width=2)
        rows=[['PARTICULARS','QTY','WEIGHT KGS','No of package / rolls'],
              ['BLUE','2 PCS','1 KG','1 pack'],['RED','3 PCS','','' if shared else '1 pack']]
        xs=[10,150,300,400,590];ys=[20,60,120,200]
        cells=[OCRTableCell(r,c,v,bbox=[xs[c],ys[r],xs[c+1],ys[r+1]]) for r,row in enumerate(rows) for c,v in enumerate(row) if v and not(clipped and c==3)]
        table=OCRTable(cells,3,3 if clipped else 4,bbox=[10,20,400 if clipped else 590,200])
        words=[OCRWord('2 PCS',.99,180,80,260,100),OCRWord('3 PCS',.99,180,150,260,170),
               OCRWord('No of package / rolls',.99,405,30,580,50),OCRWord('1 pack',.99,450,80,530,100)]
        if not shared:words.append(OCRWord('1 pack',.99,450,150,530,170))
        return image,OCRResult(tables=[table],words=words,pages=['PACKING LIST'],total_pages=1)

    def test_declared_total_and_ranges_take_priority(self):
        o=OCRResult(content='TOTAL 5 PACKAGES\nTOTAL 5 PACKAGES',tables=[self.table(['20 ROLLS'])])
        r=packing_packages(o,'A01-A03');self.assertEqual(r['total'],5)
        self.assertIn('conflicts',r['reason'])
        o.content='';self.assertEqual(packing_packages(o,'A01-A03, A02-A04')['total'],4)

    def test_aliases_and_repeated_notes_within_one_cell(self):
        for value,count in [('1 CTN',1),('2 PKS',2),('3 bags',3),('1 box',1),('2 rolls',2),
                            ('1 package\n1 CARTON',1),('1 roll\n1 roll',1),('2 rolls + 3 bags',5),
                            ('1 pack (4 PCS/PACK)',1),('1',1),('1.5 packs',None),('-1 pack',None),
                            ('1 KG',None),('FOC #8',None)]:
            with self.subTest(value=value):self.assertEqual(_read_count(value),count)

    def test_multi_page_sums_do_not_deduplicate_generic_groups_or_equal_numbers(self):
        o=OCRResult(tables=[self.table(['1 pack']),self.table(['1 package'],1)],
                    pages=['PACKING LIST\nFOC #8','PACKING LIST\nFOC #8'],total_pages=2)
        self.assertEqual(packing_packages(o)['total'],2)
        o.pages=['CARTON #8\nPACKING LIST','CARTON #8\nPACKING LIST']
        self.assertEqual(packing_packages(o)['total'],1)

    def test_explicit_carton_ids_and_numeric_ranges(self):
        self.assertEqual(_carton_ids('CARTON #8\nCARTON NO. 08'),{'8'})
        self.assertEqual(_carton_ids('CARTON #1-3'),{'1','2','3'})
        self.assertEqual(_carton_ids('CARTON NO. A01-A03'),{'A1','A2','A3'})
        self.assertEqual(_carton_ids('FOC #8\nSTYLE 25\nCARTON #4-2'),set())

    def test_duplicate_ocr_table_does_not_duplicate_cells(self):
        t=self.table(['1 pack','2 bags']);o=OCRResult(tables=[t,t])
        self.assertEqual(packing_packages(o)['total'],3)

    def test_bare_numbers_require_goods_row_and_unreadable_declarations_are_not_zero(self):
        t=self.table(['1']);t.cells.extend([OCRTableCell(2,2,'2027')])
        self.assertEqual(packing_packages(OCRResult(tables=[t]))['total'],1)
        self.assertIsNone(packing_packages(OCRResult(tables=[self.table(['1 pack','UNREADABLE'])]))['total'])
        self.assertIsNone(packing_packages(OCRResult())['total'])

    def test_partial_pdf_cannot_supply_a_detail_sum(self):
        o=OCRResult(tables=[self.table(['1 package'])],pages=['PACKING LIST'],total_pages=2)
        self.assertIsNone(packing_packages(o)['total'])
        o.content='TOTAL 3 PACKAGES';o.pages=['SHIPPER\nCONSIGNEE\nTOTAL 3 PACKAGES']
        self.assertEqual(packing_packages(o)['total'],3)

    def test_physical_shared_cell_and_separate_equal_entries(self):
        for shared,expected in [(True,1),(False,2)]:
            image,o=self.physical(shared)
            with patch('src.foc_extractor.packages._cached_page_image',return_value=image), \
                 patch('src.foc_extractor.packages._paddle_readers') as reader:
                self.assertEqual(packing_packages(o,pdf='unused.pdf')['total'],expected)
                reader.assert_not_called()

    def test_clipped_grid_still_uses_the_visible_package_column(self):
        image,o=self.physical(clipped=True)
        with patch('src.foc_extractor.packages._cached_page_image',return_value=image):
            self.assertEqual(packing_packages(o,pdf='unused.pdf')['total'],1)

    def test_repeated_handwritten_note_outside_table_is_not_added(self):
        image,o=self.physical()
        o.words.append(OCRWord('1 Roll',.99,450,210,530,230))
        with patch('src.foc_extractor.packages._cached_page_image',return_value=image):
            self.assertEqual(packing_packages(o,pdf='unused.pdf')['total'],1)

    def test_local_reread_and_source_keyed_cache(self):
        image,o=self.physical();o.words=o.words[:-1]
        reader=MagicMock();reader.predict.return_value=[{'rec_texts':['1 PK'],'rec_scores':[.95]}]
        with tempfile.TemporaryDirectory() as directory:
            pdf=Path(directory)/'new.pdf';pdf.write_bytes(b'same source bytes')
            with patch('src.foc_extractor.packages._cached_page_image',return_value=image), \
                 patch('src.foc_extractor.packages._paddle_readers',return_value=(reader,None)):
                self.assertEqual(packing_packages(o,pdf=pdf,cache_dir=directory)['total'],1)
            renamed=Path(directory)/'renamed.pdf';renamed.write_bytes(pdf.read_bytes())
            with patch('src.foc_extractor.packages._cached_page_image') as render:
                self.assertEqual(packing_packages(o,pdf=renamed,cache_dir=directory)['total'],1)
                render.assert_not_called()

    def test_local_reread_unit_without_number_blocks_partial_total(self):
        image,o=self.physical(shared=False);o.words=o.words[:-1]
        reader=MagicMock();reader.predict.return_value=[{'rec_texts':['PK'],'rec_scores':[.95]}]
        with patch('src.foc_extractor.packages._cached_page_image',return_value=image), \
             patch('src.foc_extractor.packages._paddle_readers',return_value=(reader,None)):
            result=packing_packages(o,pdf='unused.pdf')
            self.assertIsNone(result['total'])
            self.assertEqual(result['entries'][-1]['text'],'PK')
            self.assertEqual(result['reason'],'Unreadable declared package count.')


if __name__=='__main__':unittest.main()
