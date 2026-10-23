"""HS codes need explicit source readings and a supported product continuation."""
from copy import deepcopy
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch

import pymupdf
from openpyxl import load_workbook

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.ocr_engine import OCRResult,OCRTable,OCRTableCell
from src.foc_extractor.parser import parse_result
from src.foc_extractor.processing_evidence import observed
from src.foc_extractor.pipeline import run


def table(rows,page=0):
    return OCRTable([OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)],
                    len(rows),len(rows[0]),page=page)


class IndiaHSContinuationTests(unittest.TestCase):
    def parse(self,tables):
        ocr=OCRResult(tables=tables,pages=['']*(max(t.page for t in tables)+1))
        original=deepcopy(ocr)
        with patch('src.foc_extractor.parser._consignee_region',return_value='UNSEEN FACTORY\nNEW ROAD'):
            result=parse_result(ocr,Path('unseen.pdf'),region='INDIA')
        self.assertEqual(ocr,original)
        return result

    def test_same_table_and_adjacent_page_inherit_only_linked_explicit_code(self):
        for page in (0,1):
            with self.subTest(page=page):
                data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS','00012345']]),
                                 table([['DESCRIPTION','QTY','HS CODE'],['Col. Blue','1 PCS','']],page)])
                self.assertEqual([(i.description,i.quantity,i.hs_code) for i in data.items],[('ZIPPER',3,'00012345')])
                self.assertEqual(set(data.items[0].source_refs),{'1:1:2',f'{page+1}:2:2'})

    def test_heading_without_quantity_supplies_code_to_its_color_rows(self):
        data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['FABRIC CUTTINGS','','00012345'],
                               ['Col. Blue','2 SETS',''],['Col. Red','1 SETS','']])])
        self.assertEqual([(i.quantity,i.hs_code) for i in data.items],[(3,'00012345')])
        self.assertIn('1:1:2',data.items[0].source_refs)

    def test_different_codes_remain_separate_and_blank_rows_do_not_guess(self):
        data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS','00012345'],
                               ['Col. Blue','1 PCS',''],['Col. Red','4 PCS','00099999'],['Col. Green','3 PCS','']])])
        self.assertEqual([(i.quantity,i.hs_code) for i in data.items],[(2,'00012345'),(4,None),(4,'00099999')])

    def test_missing_and_invalid_codes_are_not_invented_or_repaired(self):
        for reading in ('','N/A','12345','12345678901','0012O345','0012.3456'):
            with self.subTest(reading=reading):
                data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS',reading],['Col. Blue','1 PCS','']])])
                self.assertTrue(all(i.hs_code is None for i in data.items))

    def test_an_unreadable_declaration_blocks_inheritance_but_preserves_readable_rows(self):
        data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS','00012345'],
                               ['Col. Blue','1 PCS','UNREADABLE'],['Col. Red','3 PCS','']])])
        self.assertEqual([(i.quantity,i.hs_code) for i in data.items],[(2,'00012345'),(4,None)])

    def test_new_style_or_independent_heading_does_not_borrow_a_previous_code(self):
        for row in (['STYLE#NEW',''],['ZIPPER',''],['BUTTON','']):
            with self.subTest(row=row):
                data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS','00012345'],
                                       [*row,''],['Col. Blue','1 PCS','']])])
                self.assertEqual(data.items[0].quantity,2)
                self.assertIsNone(data.items[1].hs_code)

    def test_no_backward_fill_from_a_later_color_code(self):
        data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS',''],
                               ['Col. Blue','1 PCS','00012345'],['Col. Red','3 PCS','']])])
        self.assertEqual([(i.quantity,i.hs_code) for i in data.items],[(2,None),(4,'00012345')])
        self.assertIn('1:1:3',data.items[1].source_refs)

    def test_ambiguous_hs_columns_do_not_select_or_inherit_a_code(self):
        data=self.parse([table([['DESCRIPTION','QTY','HS CODE','HS CODE'],['ZIPPER','2 PCS','00012345','00099999'],
                               ['Col. Blue','1 PCS','','']])])
        self.assertTrue(all(i.hs_code is None for i in data.items))

    def test_shared_code_survives_multiple_pages_and_absent_hs_column(self):
        tables=[table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS','00012345']]),
                table([['DESCRIPTION','QTY'],['Col. Blue','1 PCS']],1),
                table([['DESCRIPTION','QTY','HS CODE'],['Col. Red','3 PCS','']],2)]
        self.assertEqual([(i.quantity,i.hs_code) for i in self.parse(tables).items],[(6,'00012345')])

    def test_source_whitespace_is_normalized_but_leading_zeros_are_preserved(self):
        data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS','00 012345'],['Col. Blue','1 PCS','']])])
        self.assertEqual(data.items[0].hs_code,'00012345')

    def test_unsupported_table_or_page_gap_does_not_bridge_a_code(self):
        for middle in ([table([['OTHER'],['NOT GOODS']],1)],[]):
            data=self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS','00012345']]),
                             *middle,table([['DESCRIPTION','QTY','HS CODE'],['Col. Blue','1 PCS','']],2)])
            self.assertIsNone(data.items[1].hs_code)

    def test_inherited_code_evidence_identifies_the_actual_coded_row(self):
        events=[]
        @observed
        def extract():
            return self.parse([table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS',''],
                                      ['Col. Blue','1 PCS','00012345'],['Col. Red','3 PCS','']])])
        extract(observer=lambda event,**kwargs:events.append(event))
        entry=next(e for e in events if e.get('method')=='supported_product_continuation')
        self.assertEqual((entry['field'],entry['source_ref'],entry['hs_source_ref'],entry['value']),
                         ('goods_hs_code','1:1:4','1:1:3','00012345'))

    def test_pipeline_keeps_leading_zero_code_as_text_in_the_printed_invoice(self):
        ocr=OCRResult(pages=['',''],total_pages=2,tables=[
            table([['DESCRIPTION','QTY','HS CODE'],['ZIPPER','2 PCS','00012345']]),
            table([['DESCRIPTION','QTY','HS CODE'],['Col. Blue','1 PCS','']],1)])
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'unseen.pdf'
            with pymupdf.open() as pdf:
                pdf.new_page();pdf.new_page();pdf.save(source)
            with patch('src.foc_extractor.pipeline.analyze_pdf',return_value=ocr), \
                 patch('src.foc_extractor.parser._consignee_region',return_value='UNSEEN FACTORY\nNEW ROAD'):
                output=run(source,region='INDIA',output_dir=Path(directory)/'out',local_model=None)
            book=load_workbook(output)
            self.assertEqual((book.active['E33'].value,book.active['E33'].data_type),('00012345','s'))
            self.assertEqual(book.active['F33'].value,3);book.close()


if __name__=='__main__':unittest.main()
