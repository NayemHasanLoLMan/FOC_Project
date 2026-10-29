"""Approved Stage 6 estimates and source-money preservation across all regions."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_UP
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor.models import FOCData, LineItem
from src.foc_extractor.valuation import apply_valuation, RATES_FILE
from src.foc_extractor.processing_evidence import observed
from src.foc_extractor.parser import parse_result
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell
from src.foc_extractor.regions import select_region


class ValuationTests(unittest.TestCase):
    def data(self, items, region='BD', **kwargs):
        return FOCData(source_file='unseen.pdf', template_type=region, items=items, **kwargs)

    def test_unit_rates_are_universal_and_preserve_source_facts(self):
        for region in ('BD','INDIA','JORDAN'):
            data=self.data([LineItem('NEW FABRIC',10.5,'YDS',source_refs=['p2:r3']),
                            LineItem('UNSEEN ACCESSORY',12,'PCS'),LineItem('THREAD',3,'CONES'),
                            LineItem('BUTTON',2,'GROSS'),LineItem('NEW GOODS',4,'SETS')],region)
            old=deepcopy(data.items);apply_valuation(data)
            self.assertEqual([i.amount for i in data.items],[2.1,1.2,.3,.2,.4])
            self.assertEqual(data.total_value,4)
            for before,after in zip(old,data.items):
                before.unit_price,before.amount=after.unit_price,after.amount
                self.assertEqual(before,after)

    def test_india_sample_is_proportionally_capped_and_lines_reconcile(self):
        for region in ('BD','INDIA','JORDAN'):
            data=self.data([LineItem('FABRIC',378,'YDS'),LineItem('ZIPPER',65,'PCS'),LineItem('SWATCH',3,'SETS')],region)
            apply_valuation(data)
            self.assertEqual(data.total_value,80)
            self.assertEqual(sum(Decimal(str(i.amount)) for i in data.items),Decimal('80'))
            self.assertEqual([i.quantity for i in data.items],[378,65,3])
            self.assertTrue(all(i.unit_price<rate for i,rate in zip(data.items,[.2,.1,.1])))
            for item in data.items:
                self.assertEqual((Decimal(str(item.unit_price))*Decimal(str(item.quantity))).quantize(Decimal('.01'),rounding=ROUND_HALF_UP),Decimal(str(item.amount)))
            before=deepcopy(data);apply_valuation(data);self.assertEqual(data,before)

    def test_cap_protects_explicit_pdf_rates_amounts_and_total(self):
        for source,expected in [(30,80),(100,100)]:
            data=self.data([LineItem('SOURCE',2,'PCS',unit_price=source/2,amount=source),
                            LineItem('NEW',1000,'PCS')],total_value=125.75)
            apply_valuation(data)
            self.assertEqual((data.items[0].unit_price,data.items[0].amount),(source/2,source))
            self.assertEqual(data.total_value,125.75)
            self.assertEqual(sum(i.amount for i in data.items),expected)
            self.assertEqual(data.items[1].amount,max(0,80-source))
            self.assertIn('Declared PDF total preserved; it differs from the priced line sum.',data.warnings)

    def test_source_price_only_and_amount_only_are_not_scaled(self):
        data=self.data([LineItem('SOURCE',2,'PCS',unit_price=60),LineItem('AMOUNT ONLY',3,'SETS',amount=7.25),LineItem('NEW',10,'PCS')])
        apply_valuation(data)
        self.assertEqual([(i.unit_price,i.amount) for i in data.items],[(60,120),(None,7.25),(0,0)])
        self.assertEqual(data.total_value,127)
        source=self.data([LineItem('SOURCE',2,'PCS',unit_price=.125)])
        apply_valuation(source);self.assertEqual((source.items[0].amount,source.total_value),(.25,.25))

    def test_bangladesh_source_columns_are_preserved_before_estimation(self):
        rows=[['DESCRIPTION','QTY','UNIT PRICE (USD)','AMOUNT (USD)'],
              ['DIE MOULD','2 SETS','60.00','119.75']]
        ocr=OCRResult(content='PACKING LIST',pages=['PACKING LIST'],total_pages=1,tables=[OCRTable(
            [OCRTableCell(r,c,value) for r,row in enumerate(rows) for c,value in enumerate(row)],2,4)])
        data=parse_result(ocr,Path('new.pdf'),region='BD');apply_valuation(data)
        self.assertEqual([(i.unit_price,i.amount) for i in data.items],[(60,119.75)])
        self.assertEqual(data.total_value,119.75)
        ocr.content='CURRENCY: EUR';ocr.pages=[ocr.content];ocr.tables=[]
        data=parse_result(ocr,Path('foreign.pdf'),region='BD')
        self.assertEqual(data.currency,'EUR')
        with self.assertRaisesRegex(ValueError,'USD only'):
            select_region(data,'BD')

    def test_half_up_rounding_and_small_line_allocation(self):
        data=self.data([LineItem('GOODS',1.25,'PCS'),LineItem('GOODS',3.75,'PCS')])
        apply_valuation(data);self.assertEqual([i.amount for i in data.items],[.13,.38]);self.assertEqual(data.total_value,1)
        data=self.data([LineItem('PDF',1,'PCS',amount=79.99)]+[LineItem('GOODS',1,'PCS') for _ in range(3)])
        apply_valuation(data);self.assertEqual([i.amount for i in data.items[1:]],[.01,0,0])
        self.assertEqual(sum(Decimal(str(i.amount)) for i in data.items),Decimal('80'))

    def test_unreadable_quantity_unit_and_partial_pdf_do_not_invent_total(self):
        for quantity,unit in [(None,'PCS'),(-1,'PCS'),(float('nan'),'PCS'),(float('inf'),'PCS'),(1,None),(1,'')]:
            data=self.data([LineItem('GOODS',quantity,unit)]);apply_valuation(data)
            self.assertIsNone(data.items[0].amount);self.assertIsNone(data.total_value)
        data=self.data([LineItem('GOODS',10,'PCS')],pages_processed=1,pages_total=2)
        apply_valuation(data);self.assertEqual(data.items[0].amount,1);self.assertIsNone(data.total_value)
        data=self.data([LineItem('GOODS',0,'PCS')]);apply_valuation(data);self.assertEqual(data.total_value,0)

    def test_known_button_g_means_gross_without_converting_quantity(self):
        data=self.data([LineItem('27L SHANK',8.125,'G')]);apply_valuation(data)
        self.assertEqual((data.items[0].unit,data.items[0].quantity,data.items[0].amount),('GROSS',8.125,.81))

    def test_empty_other_currency_and_invalid_configuration(self):
        for region,currency in [('BD','EUR'),('INDIA','EUR'),('JORDAN','EUR'),('OTHER','USD')]:
            data=self.data([LineItem('GOODS',1,'PCS')],region,currency=currency);apply_valuation(data)
            self.assertIsNone(data.items[0].unit_price)
        data=self.data([]);apply_valuation(data);self.assertIsNone(data.total_value)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rates.json'
            for key in ('fabric_per_yd','other_per_unit','estimate_cap_usd'):
                for bad in ('NaN','Infinity','-1','0','oops'):
                    rates=json.loads(RATES_FILE.read_text());rates[key]=bad;path.write_text(json.dumps(rates))
                    data=self.data([LineItem('GOODS',2,'PCS')]);before=deepcopy(data)
                    with patch('src.foc_extractor.valuation.RATES_FILE',path):
                        with self.assertRaises(ValueError):apply_valuation(data)
                    self.assertEqual(data,before)

    def test_evidence_explains_estimate_cap_and_rounding(self):
        events=[];data=self.data([LineItem('GOODS',1000,'PCS',source_refs=['p1:r2'])])
        @observed
        def process():apply_valuation(data)
        process(observer=lambda event, **kwargs: events.append(event))
        self.assertTrue(any(e['kind']=='valuation_cap' for e in events))
        rate=next(e for e in events if e['kind']=='valuation_rate')
        self.assertEqual((rate['base_rate'],rate['rate'],rate['source_refs']),(.1,.08,['p1:r2']))
        total=next(e for e in events if e.get('field')=='total_value')
        self.assertEqual(total['rounding_adjustment'],0)


if __name__=='__main__':unittest.main()
