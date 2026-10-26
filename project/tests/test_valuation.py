import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor.models import FOCData, LineItem
from src.foc_extractor.valuation import apply_valuation, RATES_FILE
from src.foc_extractor.pipeline import run
from src.foc_extractor.excel_writer import populate_template
from src.foc_extractor.ocr_engine import OCRResult
import openpyxl


class ValuationTests(unittest.TestCase):
    def data(self, items, **kwargs):
        return FOCData(source_file='unseen-name.pdf', template_type='BD', items=items, **kwargs)

    def test_fabric_lines_and_rounded_final_total(self):
        data = self.data([LineItem('100% COTTON WOVEN FABRICS', q, 'YDS')
                          for q in (10, 60, 40, 18, 20, 10.5)])
        apply_valuation(data)
        self.assertEqual([i.amount for i in data.items], [2, 12, 8, 3.6, 4, 2.1])
        self.assertEqual(data.total_value, 32)

    def test_supported_rates_and_button_gross_without_changing_quantity(self):
        examples = [
            ('DIE MOULD (RIVET)', 2, 'SETS', 1.44),
            ('SHANK & RIVET - 2G EACH ITEM & COLOR', 600, 'PCS', 15),
            ('FABRIC CARD', 1, 'PCS', 1), ('MEATAL SNAP', 150, 'SETS', 7.5),
            ('ZIPPER CLIP', 30, 'PCS', 1.5), ('FABRIC SWATCHES', 46, 'SETS', 4.6),
            ('BULK TRIM CARD', 2, 'SETS', 1), ('27L SHANK', 8.125, 'G', .98),
            ('27L SNAP', 7, 'G', .98), ('24L SHANK', 4.3, 'G', .56),
            ('24L SNAP', 6, 'G', 1.02), ('9.5MM RIVET', 20, 'G', 1),
            ('HIDDEN SNAP', 2, 'G', .5), ('FABRIC SWATCHES CARD', 2, 'SETS', 1),
            ('TRIM CARD', 19, 'PCS', 1.9),
            ('LADIES 98% COTTON 2% SPANDEX WOVEN PANTS', 7, 'PCS', 17.5),
            ("MEN'S 100% COTTON WOVEN PANTS", 2, 'PCS', 3),
            ('KIDS 100% COTTON WOVEN DRESS', 2, 'PCS', 1.5),
            ('LADIES 100% COTTON WOVEN DRESS', 1, 'PCS', 1),
        ]
        data = self.data([LineItem(d, q, u) for d, q, u, _ in examples])
        apply_valuation(data)
        self.assertEqual([i.amount for i in data.items], [a for _, _, _, a in examples])
        self.assertEqual([i.quantity for i in data.items], [q for _, q, _, _ in examples])
        self.assertEqual(data.items[7].unit, 'GROSS')
        self.assertEqual(data.total_value, 63)

    def test_garment_singular_plural_and_apostrophes_do_not_use_swatch_rates(self):
        for description,rate in [
            ("WOMEN'S 65% COTTON 30% POLYESTER 3% RAYON 2% SPANDEX WOVEN PANT",2.5),
            ("WOMEN’S 98% COTTON 2% ELASTANE WOVEN PANTS",2.5),
            ('LADIES 98% COTTON 2% STRETCH PANT',2.5),
            ("MEN'S 100% COTTON WOVEN PANT",1.5),
            ('100% POLYESTER WOVEN PANT',1.5),
            ('WOMENS 100% COTTON WOVEN DRESSES',1),
            ("KID'S 100% COTTON WOVEN DRESS",.75),
        ]:
            with self.subTest(description=description):
                item=LineItem(description,2,'PCS');apply_valuation(self.data([item]))
                self.assertEqual((item.unit_price,item.amount),(rate,rate*2))
                self.assertEqual(item.description,description)

    def test_new_fastener_interlining_and_composition_set_coverage(self):
        for description,quantity,unit,rate in [
            ('SHANK BUTTON OPTIONS',24,'GROSS',.35),('RIVETS',4,'GROSS',.35),
            ('SHANK 30L DOUBLE RIM',100,'SETS',.05),('SNAP 21L DOUBLE RIM',100,'SETS',.05),
            ('RIVET',200,'SETS',.05),('INTERLINING #NEW-CODE',40,'YDS',.2),
            ('30L NEW LOGO SHANK BUTTON - BLUE',288,'PCS',.025),
            ('12L NEW LOGO RIVET - BLUE',576,'PCS',.025),
            ('55% COTTON 45% VISCOSE',5,'SETS',.1),('100% COTTON',3,'SETS',.1),
        ]:
            with self.subTest(description=description):
                item=LineItem(description,quantity,unit);apply_valuation(self.data([item]))
                self.assertEqual(item.unit_price,rate)
                self.assertEqual((item.description,item.quantity,item.unit),(description,quantity,unit))
                self.assertIsNotNone(item.amount)

    def test_fallbacks_do_not_price_tools_garment_sets_or_invent_quantities(self):
        for description,quantity,unit in [
            ('SHANK BUTTON DIE MOULD',2,'SETS'),('RIVET INSTALLATION TOOL',1,'PCS'),
            ('RIVET MACHINE',1,'GROSS'),('SHANK BUTTON CARD',1,'PCS'),
            ('100% COTTON WOVEN PANTS',2,'SETS'),('INTERLINING',None,None),
            ('FABRIC SAMPLES',1,None),('RIVET',2,'GRAMS'),
        ]:
            with self.subTest(description=description):
                item=LineItem(description,quantity,unit);data=self.data([item]);apply_valuation(data)
                self.assertIsNone(item.amount);self.assertIsNone(data.total_value)
                self.assertEqual((item.quantity,item.unit),(quantity,unit))

    def test_specific_and_source_rates_remain_ahead_of_new_fallbacks(self):
        rates=json.loads(RATES_FILE.read_text())
        rates['metal_snap_per_set']='0.09'
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'rates.json';path.write_text(json.dumps(rates))
            with patch('src.foc_extractor.valuation.RATES_FILE',path):
                data=self.data([LineItem('METAL SNAP',3,'SETS'),LineItem('9.5MM RIVET',2,'GROSS')])
                apply_valuation(data)
                self.assertEqual([i.unit_price for i in data.items],[.09,.05])
        item=LineItem('RIVET',4,'SETS',amount=12.34);data=self.data([item]);apply_valuation(data)
        self.assertIsNone(item.unit_price);self.assertEqual((item.amount,data.total_value),(12.34,12))
        item=LineItem('FABRIC',5,'YDS',unit_price=0);data=self.data([item]);apply_valuation(data)
        self.assertEqual((item.unit_price,item.amount,data.total_value),(0,0,0))

    def test_interlining_does_not_expand_india_pricing_policy(self):
        data=FOCData(source_file='unseen.pdf',template_type='INDIA',items=[LineItem('INTERLINING',40,'YDS')])
        apply_valuation(data)
        self.assertIsNone(data.items[0].amount);self.assertIsNone(data.total_value)

    def test_unsupported_rows_do_not_become_a_partial_shipment_total(self):
        for description, quantity, unit in [
            ('UNIDENTIFIED ITEM', 2, 'PCS'),
            ('TRIM CARD', 12, None), ('27L SHANK', 8, 'GRAMS'),
            ('FABRIC', None, 'YDS'), ('FABRIC', -1, 'YDS'),
            ('FABRIC', float('nan'), 'YDS'), ('FABRIC', float('inf'), 'YDS'),
        ]:
            with self.subTest(description=description, unit=unit, quantity=quantity):
                data = self.data([LineItem('FABRIC', 10, 'YDS'), LineItem(description, quantity, unit)])
                apply_valuation(data)
                self.assertIsNone(data.items[1].amount)
                self.assertIsNone(data.total_value)

    def test_ambiguous_g_is_not_globally_converted(self):
        warning = 'Unit G is ambiguous; confirm meaning without automatic conversion.'
        data = self.data([LineItem('27L SHANK', 8.125, 'G'), LineItem('UNKNOWN', 3, 'G')], warnings=[warning])
        apply_valuation(data)
        self.assertEqual([i.unit for i in data.items], ['GROSS', 'G'])
        self.assertIn(warning, data.warnings)
        data.items.pop()
        apply_valuation(data)
        self.assertNotIn(warning, data.warnings)

    def test_new_category_rates_on_unseen_descriptions(self):
        cases = [
            ('FABRIC SWATCHES', 2, 'PCS', .5),
            ('100% NYLON', 6, 'PCS', 1.5),
            ('100% US COTTON', 3, 'PCS', .75),
            ('NEXT SEASON HANDLOOM FOR CVC SHIRT', 4, 'PCS', 1),
            ('YARN DYED - NEW COLOUR', 4, 'PCS', 1),
            ('FABRIC BOOKING - NEW STYLE', 4, 'PCS', 1),
            ('NEW CVC CARRYOVER PROGRAM', 4, 'PCS', 1),
            ('NEW PRINT PROGRAM - 55% US COTTON 45% POLYESTER AOP', 2, 'PCS', .5),
            ('CSI FAB SAMPLE STANDARD', 2, 'SETS', .2),
            ('ZIPPER', 5, 'PCS', .5),
            ('MENS 100% LINEN WOVEN SHIRT', 2, 'PCS', .7),
            ('100% COTTON WOVEN SHIRT', 1, 'PCS', .35),
            ('MENS WOVEN SHIRT 100% COTTON', 1, 'PCS', .35),
            ('WOMENS WOVEN BLOUSE', 1, 'PCS', 1),
            ('BULK FABRIC BLANKET - NEW STYLE', 4, 'PACKS', 2),
            ('TAPER CARD - NEW STYLE', 2, 'PACKS', .5),
            ('SAMPLE LACE', 72, 'YDS', 1.44),
            ('SIZE STICKER', 80, 'PCS', .4),
            ('FABRIC HANGER', 2, 'PCS', .5),
            ('MF PART CARD', 1, 'PCS', .1),
            ('EMBY MF PART CARD', 2, 'PCS', .2),
            ('FELT PATCH', 440, 'PCS', 4.4),
            ('SHANK BUTTON', 2, 'GROSS', .7),
            ('SNAP BUTTON', 1, 'GROSS', .35),
            ('100% COTTON WOVEN PANTS', 2, 'PCS', 3),
            ('SLVS BELTED MAXI DRESS', 1, 'PCS', 1),
            ('SAMPLE JACKET AND DRESS - CATEGORY UNCLEAR', 2, 'PCS', 2),
            ('SAMPLE JACKET', 1, 'PCS', 1),
        ]
        for description, quantity, unit, amount in cases:
            with self.subTest(description=description):
                item = LineItem(description, quantity, unit)
                apply_valuation(self.data([item]))
                self.assertEqual(item.amount, amount)
                self.assertEqual((item.description, item.quantity, item.unit), (description, quantity, unit))

    def test_specific_rates_take_priority_and_new_rates_do_not_convert_units(self):
        data = self.data([LineItem('FABRIC SWATCHES CARD', 2, 'SETS'),
                          LineItem('LADIES 98% COTTON 2% SPANDEX WOVEN PANTS', 2, 'PCS'),
                          LineItem('27L SHANK', 2, 'GROSS')])
        apply_valuation(data)
        self.assertEqual([i.amount for i in data.items], [1, 5, .24])
        for description, unit in [('SHANK BUTTON', 'G'), ('SAMPLE LACE', 'PCS'),
                                  ('FABRIC SWATCHES', 'PACKS'), ('TRIM CARD', None),
                                  ('SIZE STICKER', 'KG'), ('100% COTTON', None)]:
            item = LineItem(description, 2, unit)
            data = self.data([item]); apply_valuation(data)
            self.assertIsNone(item.amount)
            self.assertIsNone(data.total_value)
            self.assertEqual(item.unit, unit)

    def test_source_prices_amounts_and_total_take_priority(self):
        data = self.data([LineItem('FABRIC', 5, 'YDS', unit_price=3, amount=14.75)], total_value=14.75)
        apply_valuation(data)
        self.assertEqual((data.items[0].unit_price, data.items[0].amount, data.total_value), (3, 14.75, 14.75))
        data = self.data([LineItem('FABRIC', 5, 'YDS', unit_price=3)])
        apply_valuation(data)
        self.assertEqual(data.total_value, 15)

    def test_half_up_and_cent_rounding_do_not_use_binary_float_rounding(self):
        data = self.data([LineItem('SHANK & RIVET', 20, 'PCS'), LineItem('SHANK & RIVET', 1, 'PCS')])
        apply_valuation(data)
        self.assertEqual([i.amount for i in data.items], [.5, .03])
        self.assertEqual(data.total_value, 1)

    def test_empty_and_other_region_or_currency_are_not_estimated(self):
        for region, currency in [('INDIA', 'EUR'), ('BD', 'EUR'), ('JORDAN', 'USD')]:
            data = FOCData(source_file='new.pdf', template_type=region, currency=currency,
                           items=[LineItem('FABRIC', 10, 'YDS')])
            apply_valuation(data)
            self.assertIsNone(data.total_value)
            self.assertIsNone(data.items[0].unit_price)
        data = self.data([])
        apply_valuation(data)
        self.assertIsNone(data.total_value)

    def test_invalid_config_fails_before_mutating_goods(self):
        rates = json.loads(RATES_FILE.read_text())
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'rates.json'
            for bad in ('NaN', '-1', 'Infinity', 'oops', '0'):
                rates['fabric_per_yd'] = bad
                config.write_text(json.dumps(rates))
                data = self.data([LineItem('FABRIC', 10, 'YDS')])
                with patch('src.foc_extractor.valuation.RATES_FILE', config):
                    with self.assertRaises(ValueError):
                        apply_valuation(data)
                self.assertIsNone(data.items[0].unit_price)

    def test_pipeline_applies_rates_before_export(self):
        with tempfile.TemporaryDirectory() as directory:
            pdf = Path(directory) / 'new.pdf'
            pdf.touch()
            data = self.data([LineItem('FABRIC', 10, 'YDS')], gross_weight_kg=1)
            with patch('src.foc_extractor.pipeline.analyze_pdf', return_value=OCRResult()), \
                 patch('src.foc_extractor.pipeline.parse_result', return_value=data), \
                 patch('src.foc_extractor.pipeline.populate_template') as writer:
                run(pdf, template=ROOT / 'templates/BD_template.xlsx', output_dir=Path(directory))
            self.assertEqual(writer.call_args.args[2].total_value, 2)

    def test_partial_pdf_cannot_supply_an_estimated_shipment_total(self):
        data = self.data([LineItem('FABRIC', 10, 'YDS')], pages_processed=1, pages_total=2)
        apply_valuation(data)
        self.assertEqual(data.items[0].amount, 2)
        self.assertIsNone(data.total_value)

    def test_export_preserves_fractional_rates_and_two_decimal_line_values(self):
        data = self.data([LineItem('SHANK & RIVET', 1, 'PCS')])
        apply_valuation(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'new.xlsx'
            populate_template(ROOT / 'templates/BD_template.xlsx', path, data)
            wb = openpyxl.load_workbook(path)
            self.assertEqual(wb['Extracted_Items']['G2'].value, .025)
            self.assertEqual(wb['Extracted_Items']['H2'].value, .03)
            self.assertEqual(wb['Extracted_Items']['H2'].number_format, '0.00')
            wb.close()


if __name__ == '__main__':
    unittest.main()
