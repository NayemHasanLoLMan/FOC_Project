import copy
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


class IndiaValuationTests(unittest.TestCase):
    def data(self, items, **kwargs):
        return FOCData(source_file='unseen.pdf', template_type='INDIA', items=items, **kwargs)

    def test_three_categories_and_cent_total_without_changing_source_facts(self):
        data = self.data([LineItem('NEW 100% LINEN WOVEN FABRIC, WIDTH 60 INCHES', 378, 'YDS', hs_code='00123456'),
                          LineItem('ZIPPER', 65, 'PCS'), LineItem('FABRIC CUTTINGS', 3, 'SETS')])
        before = copy.deepcopy(data.items)
        apply_valuation(data)
        self.assertEqual([i.unit_price for i in data.items], [.2, .1, .1])
        self.assertEqual([i.amount for i in data.items], [75.6, 6.5, .3])
        self.assertEqual(data.total_value, 82.4)
        for old, new in zip(before, data.items):
            old.unit_price, old.amount = new.unit_price, new.amount
            self.assertEqual(old, new)

    def test_sample_names_and_precise_half_up_line_rounding(self):
        for name in ('FAB SWATCHES', 'FABRIC SWATCH', 'FABRIC SAMPLES', 'FAB SAMPLE', 'FABRIC CUTTING'):
            data = self.data([LineItem(name, 1.25, 'SETS')])
            apply_valuation(data)
            self.assertEqual((data.items[0].amount, data.total_value), (.13, .13))

    def test_only_approved_categories_and_units_no_partial_total(self):
        for name, unit in [('FABRIC CARD', 'SETS'), ('FABRIC SAMPLE SHIRT', 'SETS'),
                           ('ZIPPER CLIP', 'PCS'), ('ZIPPER', 'SETS'), ('FABRIC', 'PCS'),
                           ('FABRIC CUTTINGS', None), ('UNKNOWN', 'PCS'), ('27L SHANK', 'G')]:
            with self.subTest(name=name, unit=unit):
                data = self.data([LineItem('FABRIC', 2, 'YDS'), LineItem(name, 3, unit)])
                apply_valuation(data)
                self.assertIsNone(data.items[1].unit_price)
                self.assertIsNone(data.items[1].amount)
                self.assertEqual(data.items[1].unit, unit)
                self.assertIsNone(data.total_value)

    def test_source_prices_amounts_and_total_remain_authoritative(self):
        data = self.data([LineItem('FABRIC', 2, 'YDS', unit_price=3, amount=5.75)], total_value=5.75)
        apply_valuation(data)
        self.assertEqual((data.items[0].unit_price, data.items[0].amount, data.total_value), (3, 5.75, 5.75))
        data = self.data([LineItem('UNLISTED SOURCE ITEM', 3, 'PCS', unit_price=.125)])
        apply_valuation(data)
        self.assertEqual((data.items[0].amount, data.total_value), (.38, .38))

    def test_incomplete_pdf_and_invalid_quantities_never_produce_total(self):
        data = self.data([LineItem('FABRIC', 5, 'YDS')], pages_processed=1, pages_total=2)
        apply_valuation(data)
        self.assertEqual(data.items[0].amount, 1)
        self.assertIsNone(data.total_value)
        for quantity in (None, -1, float('nan'), float('inf')):
            data = self.data([LineItem('FABRIC', quantity, 'YDS')])
            apply_valuation(data)
            self.assertIsNone(data.items[0].amount)
            self.assertIsNone(data.total_value)

    def test_regional_configuration_is_separate_and_validated_before_mutation(self):
        rates = json.loads(RATES_FILE.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'rates.json'
            for bad in ('NaN', 'Infinity', '-1', '0', 'oops'):
                rates['india']['fabric_per_yd'] = bad
                path.write_text(json.dumps(rates))
                data = self.data([LineItem('FABRIC', 5, 'YDS')])
                with patch('src.foc_extractor.valuation.RATES_FILE', path):
                    with self.assertRaises(ValueError):
                        apply_valuation(data)
                    self.assertIsNone(data.items[0].unit_price)
                    bd = FOCData(source_file='new.pdf', template_type='BD', items=[LineItem('FABRIC', 1.25, 'YDS')])
                    apply_valuation(bd)
                    self.assertEqual((bd.items[0].amount, bd.total_value), (.25, 0))


if __name__ == '__main__':
    unittest.main()
