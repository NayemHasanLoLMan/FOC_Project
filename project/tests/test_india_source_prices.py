from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell
from src.foc_extractor.parser import parse_result
from src.foc_extractor.valuation import apply_valuation
from src.foc_extractor.pipeline import run


class IndiaSourcePriceTests(unittest.TestCase):
    def parse(self, rows, content=''):
        ocr = OCRResult(content=content, pages=[content], total_pages=1, tables=[OCRTable(
            [OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)], len(rows), len(rows[0]))])
        original = deepcopy(ocr)
        with patch('src.foc_extractor.parser._consignee_region', return_value='NEW INDIA FACTORY\nNEW SOURCE ROAD'):
            data = parse_result(ocr, Path('unseen-priced.pdf'), region='INDIA')
        self.assertEqual(ocr, original)
        return data

    def test_printed_usd_prices_amounts_and_total_override_estimates(self):
        data = self.parse([['DESCRIPTION','QTY','UNIT PRICE (USD)','AMOUNT (USD)'],
                           ['100% COTTON FABRIC','10 YDS','USD 3.00','$29.75']], 'TOTAL VALUE: USD 29.75')
        self.assertEqual((data.items[0].unit_price, data.items[0].amount), (3,29.75))
        apply_valuation(data)
        self.assertEqual((data.items[0].unit_price, data.items[0].amount, data.total_value), (3,29.75,29.75))

    def test_grouped_source_amounts_sum_and_distinct_prices_remain_separate(self):
        data = self.parse([['DESCRIPTION','QTY','RATE','LINE TOTAL'],
                           ['ZIPPER','2 PCS','0.10','0.19'], ['ZIPPER','3 PCS','0.10','0.29'],
                           ['ZIPPER','1 PCS','0.20','0.20']])
        self.assertEqual([(i.quantity,i.unit_price,i.amount) for i in data.items], [(5,.1,.48),(1,.2,.2)])
        apply_valuation(data)
        self.assertEqual(data.total_value,.68)

    def test_source_amount_only_is_not_assigned_a_guessed_unit_price(self):
        data = self.parse([['DESCRIPTION','QTY','ITEM VALUE'], ['ZIPPER','2 PCS','1.25']])
        apply_valuation(data)
        self.assertEqual((data.items[0].unit_price,data.items[0].amount,data.total_value), (None,1.25,1.25))

    def test_partly_priced_rows_do_not_lose_quantities_or_amounts_when_grouped(self):
        data = self.parse([['DESCRIPTION','QTY','AMOUNT'],
                           ['ZIPPER','2 PCS','1.25'], ['ZIPPER','3 PCS','']])
        self.assertEqual([(i.quantity,i.amount) for i in data.items], [(2,1.25),(3,None)])
        apply_valuation(data)
        self.assertEqual([i.amount for i in data.items], [1.25,.3])
        self.assertEqual(data.total_value,2)

    def test_zero_source_rate_and_amount_remain_zero(self):
        for price,amount in [('0',''),('','0'),('0','0')]:
            with self.subTest(price=price,amount=amount):
                data = self.parse([['DESCRIPTION','QTY','UNIT VALUE','AMOUNT'], ['ZIPPER','2 PCS',price,amount]])
                apply_valuation(data)
                self.assertEqual((data.items[0].amount,data.total_value), (0,0))

    def test_fractional_rate_and_thousands_amount_preserved(self):
        data = self.parse([['DESCRIPTION','QTY','UNIT PRICE','TOTAL AMOUNT'],
                           ['ZIPPER','10000 PCS','0.125','1,250.00']])
        apply_valuation(data)
        self.assertEqual((data.items[0].unit_price,data.items[0].amount,data.total_value), (.125,1250,1250))

    def test_price_only_calculates_amount_and_absent_prices_use_fallback(self):
        data = self.parse([['DESCRIPTION','QTY','UNIT PRICE','AMOUNT'],
                           ['ZIPPER','3 PCS','0.125',''], ['FABRIC','10 YDS','','']])
        apply_valuation(data)
        self.assertEqual([i.amount for i in data.items], [.38,2])
        self.assertEqual(data.total_value,2)

    def test_ambiguous_values_columns_and_split_rows_are_not_copied(self):
        for headers,values in [(['UNIT PRICE','AMOUNT'],['3.00\n4.00','30.00\n40.00']),
                               (['UNIT PRICE','UNIT PRICE'],['3.00','4.00']),
                               (['UNIT PRICE','AMOUNT'],['NaN','Infinity']),
                               (['UNIT PRICE','AMOUNT'],['-3','-30']),
                               (['UNIT PRICE','AMOUNT'],['1,25','1,25'])]:
            data = self.parse([['DESCRIPTION','QTY',*headers], ['ZIPPER','2 PCS',*values]])
            self.assertIsNone(data.items[0].unit_price)
            self.assertIsNone(data.items[0].amount)
        data = self.parse([['DESCRIPTION','QTY','UNIT PRICE','AMOUNT'],
                           ['100% COTTON\n100% LINEN','2 YDS\n3 YDS','3.00','15.00']])
        self.assertEqual(len(data.items),2)
        self.assertTrue(all(i.unit_price is None and i.amount is None for i in data.items))

    def test_pipeline_exports_source_amount_and_records_price_evidence(self):
        rows = [['DESCRIPTION','QTY','UNIT PRICE','AMOUNT'], ['100% COTTON FABRIC','10 YDS','USD 3.00','USD 29.75']]
        ocr = OCRResult(content='TOTAL VALUE: USD 29.75', pages=['TOTAL VALUE: USD 29.75'], total_pages=1,
                        tables=[OCRTable([OCRTableCell(r,c,v) for r,row in enumerate(rows) for c,v in enumerate(row)],2,4)])
        events = []
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'unseen.pdf'
            with pymupdf.open() as pdf:
                pdf.new_page();pdf.save(source)
            with patch('src.foc_extractor.pipeline.analyze_pdf',return_value=ocr), \
                 patch('src.foc_extractor.parser._consignee_region',return_value='NEW INDIA FACTORY\nSOURCE ROAD'):
                output = run(source,region='INDIA',output_dir=Path(directory)/'output',local_model=None,
                             observer=lambda event,**kwargs:events.append(event))
            book = load_workbook(output)
            self.assertEqual((book.active['I33'].value,book.active['I42'].value), (29.75,29.75))
            self.assertEqual(book['Extracted_Items']['G2'].value,3)
            book.close()
        source_events = [e for e in events if e.get('method')=='labelled_pdf_table_column' and e.get('field') in ('goods_unit_price','goods_amount')]
        self.assertEqual({e['field']:e['value'] for e in source_events}, {'goods_unit_price':3,'goods_amount':29.75})
        self.assertTrue(all(e['source_ref']=='1:1:2' for e in source_events))


if __name__ == '__main__':
    unittest.main()
