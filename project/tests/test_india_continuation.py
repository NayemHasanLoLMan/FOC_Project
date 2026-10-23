"""Cross-table product context needs adjacent compatible tables and explicit color/unit evidence."""
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


def table(rows,page=0,bbox=None):
    return OCRTable([OCRTableCell(r,c,value) for r,row in enumerate(rows) for c,value in enumerate(row)],
                    len(rows),len(rows[0]),page=page,bbox=bbox)


class IndiaContinuationTests(unittest.TestCase):
    def parse(self,tables,pages=None):
        pages=pages or ['']*(max(t.page for t in tables)+1)
        ocr=OCRResult(content='\n'.join(pages),pages=pages,tables=tables)
        before=deepcopy(ocr)
        with patch('src.foc_extractor.parser._consignee_region',return_value='UNSEEN FACTORY\nNEW ROAD'):
            data=parse_result(ocr,Path('anonymous.pdf'),region='INDIA')
        self.assertEqual(ocr,before)
        return data

    def pair(self,page=1,tail='Col. Blue',quantity='1 PCS'):
        return [table([['DESCRIPTION','QTY'],['ZIPPER','2 PCS']]),
                table([['DESCRIPTION','QTY'],[tail,quantity]],page)]

    def test_adjacent_table_and_next_page_color_continue_the_product(self):
        for page in (0,1):
            with self.subTest(page=page):
                data=self.parse(self.pair(page))
                self.assertEqual([(i.description,i.quantity,i.unit) for i in data.items],[('ZIPPER',3,'PCS')])
                self.assertEqual(set(data.items[0].source_refs),{'1:1:2',f'{page+1}:2:2'})
                self.assertEqual(data.items[0].source_page,1 if page==0 else None)

    def test_context_can_continue_over_multiple_adjacent_pages(self):
        tables=self.pair()+[table([['DESCRIPTION','QTY'],['Colour: Red','4 PCS']],2)]
        data=self.parse(tables)
        self.assertEqual([(i.description,i.quantity) for i in data.items],[('ZIPPER',7)])
        self.assertIn('3:3:2',data.items[0].source_refs)

    def test_blank_rows_do_not_erase_the_last_product(self):
        tables=self.pair()
        tables[0]=table([['DESCRIPTION','QTY'],['ZIPPER','2 PCS'],['','']])
        tables[1]=table([['DESCRIPTION','QTY'],['',''],['Col. Blue','1 PCS']],1)
        self.assertEqual(self.parse(tables).items[0].quantity,3)

    def test_new_product_or_style_does_not_inherit_the_old_heading(self):
        for rows in ([['BUTTON','1 PCS'],['Col. Blue','4 PCS']],
                     [['STYLE#NEW',''],['Col. Blue','1 PCS']],
                     [['STYLE: NEW\nCol. Blue','1 PCS']]):
            with self.subTest(rows=rows):
                tables=self.pair();tables[1]=table([['DESCRIPTION','QTY'],*rows],1)
                data=self.parse(tables)
                self.assertEqual(next(i.quantity for i in data.items if i.description=='ZIPPER'),2)
                self.assertFalse(any(i.description=='ZIPPER' and '2:2:2' in i.source_refs for i in data.items))

    def test_new_style_in_another_cell_stops_continuation(self):
        tables=[table([['DESCRIPTION','QTY','NOTES'],['ZIPPER','2 PCS','']]),
                table([['DESCRIPTION','QTY','NOTES'],['Col. Blue','1 PCS','STYLE#NEW']],1)]
        self.assertEqual(self.parse(tables).items[0].quantity,2)

    def test_new_style_above_the_continuation_table_stops_inheritance(self):
        pages=['ZIPPER\n2 PCS','PACKING LIST\nSTYLE#NEW\nCol. Blue\n1 PCS']
        self.assertEqual(self.parse(self.pair(),pages).items[0].quantity,2)

    def test_later_new_style_does_not_block_a_supported_initial_continuation(self):
        tables=self.pair();tables[1]=table([['DESCRIPTION','QTY'],['Col. Blue','1 PCS'],
                                          ['STYLE#NEW',''],['Col. Red','4 PCS']],1)
        data=self.parse(tables,['ZIPPER\n2 PCS','Col. Blue\n1 PCS\nSTYLE#NEW\nCol. Red\n4 PCS'])
        self.assertEqual(data.items[0].quantity,3)

    def test_no_carry_over_a_page_gap_backwards_page_or_incompatible_columns(self):
        cases=[self.pair(page=2),list(reversed(self.pair())),
               [table([['DESCRIPTION','QTY'],['ZIPPER','2 PCS']]),
                table([['QTY','DESCRIPTION'],['1 PCS','Col. Blue']],1)]]
        for tables in cases:
            with self.subTest(tables=tables):
                self.assertEqual(next(i.quantity for i in self.parse(tables).items if i.description=='ZIPPER'),2)

    def test_intervening_unrecognized_table_and_total_stop_continuation(self):
        tables=self.pair();tables.insert(1,table([['OTHER'],['NOT GOODS']]))
        self.assertEqual(self.parse(tables).items[0].quantity,2)
        tables=self.pair();tables[0]=table([['DESCRIPTION','QTY'],['ZIPPER','2 PCS'],['TOTAL','2 PCS']])
        self.assertEqual(self.parse(tables).items[0].quantity,2)

    def test_missing_description_row_is_a_boundary(self):
        tables=self.pair();tables[0].cells.append(OCRTableCell(2,1,'4 PCS'));tables[0].row_count=3
        self.assertEqual(self.parse(tables).items[0].quantity,2)

    def test_incompatible_unknown_and_mixed_units_do_not_inherit(self):
        for quantity in ('1 YDS','1','1 PCS + 2 SETS','unknown PCS'):
            with self.subTest(quantity=quantity):
                self.assertEqual(self.parse(self.pair(quantity=quantity)).items[0].quantity,2)
        tables=self.pair();tables[0]=table([['DESCRIPTION','QTY'],['ZIPPER','2 PCS'],['Col. Red','3']])
        self.assertEqual([(i.description,i.quantity,i.unit) for i in self.parse(tables).items],
                         [('ZIPPER',2,'PCS'),('ZIPPER',3,None),('COL. BLUE',1,'PCS')])

    def test_explicit_heading_restarts_context_after_an_incompatible_color(self):
        tables=self.pair();tables[1]=table([['DESCRIPTION','QTY'],['Col. Blue','1 YDS'],
                                          ['FABRIC CUTTINGS',''],['Col. Red','2 SETS']],1)
        data=self.parse(tables)
        self.assertEqual([(i.description,i.quantity) for i in data.items],
                         [('ZIPPER',2),('COL. BLUE',1),('FABRIC CUTTINGS',2)])

    def test_explicit_sender_or_item_prevents_inherited_description(self):
        for header in ('SENDER','ITEM'):
            with self.subTest(header=header):
                tables=[table([['DESCRIPTION','QTY',header],['ZIPPER','2 PCS','']]),
                        table([['DESCRIPTION','QTY',header],['Col. Blue','1 PCS','OTHER']],1)]
                self.assertEqual(self.parse(tables).items[0].quantity,2)

    def test_overlapping_same_page_tables_are_not_continuations(self):
        tables=self.pair(page=0);tables[0].bbox=[0,100,500,400];tables[1].bbox=[0,200,500,300]
        self.assertEqual(self.parse(tables).items[0].quantity,2)

    def test_same_page_context_uses_original_last_row_when_a_style_precedes_its_heading(self):
        tables=[table([['DESCRIPTION','QTY'],['STYLE#FIRST\nZipper','2 PCS'],['Col. Black','1 PCS']]),
                table([['DESCRIPTION','QTY'],['Col. Blue','1 PCS']])]
        data=self.parse(tables,['STYLE#FIRST\nZipper\n2 PCS\nCol. Black\n1 PCS\nCol. Blue\n1 PCS'])
        self.assertEqual(data.items[0].quantity,4)

    def test_ambiguous_repeated_color_location_does_not_hide_an_outside_style(self):
        pages=['ZIPPER','Col. Blue\nOLD NOTE\nSTYLE#NEW\nCol. Blue\n1 PCS']
        self.assertEqual(self.parse(self.pair(),pages).items[0].quantity,2)

    def test_each_continuation_row_keeps_its_own_source_rate_and_amount(self):
        for rate,amount in (('0.2','0.2'),('0.3','0.3')):
            with self.subTest(rate=rate):
                tables=[table([['DESCRIPTION','QTY','RATE','AMOUNT'],['ZIPPER','2 PCS','0.2','0.4']]),
                        table([['DESCRIPTION','QTY','RATE','AMOUNT'],['Col. Blue','1 PCS',rate,amount]],1)]
                data=self.parse(tables)
                expected=[('ZIPPER',3,.2,.6)] if rate=='0.2' else [('ZIPPER',2,.2,.4),('ZIPPER',1,.3,.3)]
                self.assertEqual([(i.description,i.quantity,i.unit_price,i.amount) for i in data.items],expected)

    def test_cross_page_multiline_compatible_quantities_are_counted_once(self):
        data=self.parse(self.pair(quantity='1 PCS\n3 PCS'))
        self.assertEqual([(i.description,i.quantity) for i in data.items],[('ZIPPER',6)])

    def test_supported_hs_continues_without_inheriting_money(self):
        tables=[table([['DESCRIPTION','QTY','HS CODE','RATE','AMOUNT'],['ZIPPER','2 PCS','00012345','0.2','0.4']]),
                table([['DESCRIPTION','QTY','HS CODE','RATE','AMOUNT'],['Col. Blue','1 PCS','','','']],1)]
        data=self.parse(tables)
        self.assertEqual([(i.description,i.quantity,i.hs_code,i.unit_price,i.amount) for i in data.items],
                         [('ZIPPER',2,'00012345',.2,.4),('ZIPPER',1,'00012345',None,None)])

    def test_continuation_records_the_original_heading_and_original_color(self):
        events=[]
        @observed
        def extract():return self.parse(self.pair())
        extract(observer=lambda event,**kwargs:events.append(event))
        entry=next(e for e in events if e.get('continued_table'))
        self.assertEqual((entry['source_ref'],entry['heading_source_ref'],entry['original']),
                         ('2:2:2','1:1:2','Col. Blue'))

    def test_continuation_pipeline_writes_three_pieces_and_calculated_value(self):
        ocr=OCRResult(tables=self.pair(),pages=['',''],total_pages=2)
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'unseen.pdf'
            with pymupdf.open() as pdf:
                pdf.new_page();pdf.new_page();pdf.save(source)
            with patch('src.foc_extractor.pipeline.analyze_pdf',return_value=ocr), \
                 patch('src.foc_extractor.parser._consignee_region',return_value='UNSEEN FACTORY\nNEW ROAD'):
                output=run(source,region='INDIA',output_dir=Path(directory)/'out',local_model=None)
            book=load_workbook(output)
            self.assertEqual(book.active['F33'].value,3)
            self.assertEqual(book.active['I33'].value,.3)
            self.assertEqual(book['Extracted_Items']['C2'].value,3)
            book.close()


if __name__=='__main__':unittest.main()
