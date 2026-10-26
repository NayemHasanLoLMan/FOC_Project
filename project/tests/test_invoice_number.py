import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.parser import _extract_invoice_number, parse_result
from src.foc_extractor.ocr_engine import OCRResult


class InvoiceNumberTests(unittest.TestCase):
    def test_frequency_and_first_occurrence_use_only_document_evidence(self):
        self.assertEqual(_extract_invoice_number('S/3481/27\n5/3481/27\nS/3491/27'),'S/3481/27')
        self.assertEqual(_extract_invoice_number('S/7654/28 S/2345/28 S/2345/28'),'S/2345/28')
        self.assertEqual(_extract_invoice_number('S/7654/28 S/2345/28'),'S/7654/28')

    def test_renaming_cannot_supply_or_change_a_source_reference(self):
        for filename in ('27S5432-D.pdf','28S2345-D.pdf','anonymous.pdf'):
            self.assertIsNone(parse_result(OCRResult(content='PACKING LIST'),Path(filename)).invoice_number)
            self.assertEqual(parse_result(OCRResult(content='S/1432/37'),Path(filename)).invoice_number,'S/1432/37')

    def test_format_normalization_and_variable_serial_length(self):
        for text,expected in [('5 / 5432 / 27','S/5432/27'),('8/54321/27','S/54321/27'),
                              ('S⁄432⁄27','S/432/27'),('S\\5432\\27','S/5432/27')]:
            self.assertEqual(_extract_invoice_number(text),expected)
        self.assertIsNone(_extract_invoice_number('S/12/27 S/123456/27 QTY 100 PCS STYLE 1234'))


if __name__=='__main__':
    unittest.main()
