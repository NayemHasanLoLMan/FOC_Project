import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.parser import _extract_invoice_number, parse_result
from src.foc_extractor.ocr_engine import OCRResult


class InvoiceNumberTests(unittest.TestCase):
    def test_exact_filename_support_can_resolve_a_minority_pdf_reading(self):
        text='S/3481/27\n5/3481/27\nS/3491/27'
        self.assertEqual(_extract_invoice_number(text,'S/3491/27'),'S/3491/27')

    def test_frequency_and_first_occurrence_resolve_disagreement_without_filename(self):
        self.assertEqual(_extract_invoice_number('S/7654/28 S/2345/28 S/2345/28'),'S/2345/28')
        self.assertEqual(_extract_invoice_number('S/7654/28 S/2345/28'),'S/7654/28')

    def test_single_close_ocr_reading_uses_filename_support(self):
        self.assertEqual(_extract_invoice_number('S/1432/37','S/5432/27'),'S/5432/27')
        self.assertEqual(_extract_invoice_number('S/5438/27','S/5432/27'),'S/5432/27')

    def test_repeated_document_evidence_is_not_replaced_by_a_near_filename(self):
        self.assertEqual(_extract_invoice_number('S/5438/27 S/5438/27','S/5432/27'),'S/5438/27')

    def test_distant_or_different_length_filename_does_not_override_pdf(self):
        for hint in ('S/9876/29','S/05432/27'):
            self.assertEqual(_extract_invoice_number('S/5432/27',hint),'S/5432/27')

    def test_filename_fallback_and_no_evidence(self):
        self.assertEqual(_extract_invoice_number('PACKING LIST','S/5432/27'),'S/5432/27')
        self.assertIsNone(_extract_invoice_number('QTY 100 PCS STYLE 1234'))

    def test_format_normalization_does_not_change_other_numbers(self):
        self.assertEqual(_extract_invoice_number('5 / 5432 / 27\nS/5432/27'),'S/5432/27')
        self.assertIsNone(_extract_invoice_number('S/12/27 S/123456/27'))

    def test_pipeline_parser_records_selection_only_in_internal_diagnostics(self):
        data=parse_result(OCRResult(content='S/1432/37'),Path('27S5432-D.pdf'))
        self.assertEqual(data.invoice_number,'S/5432/27')
        self.assertTrue(any('Best-effort invoice number' in w for w in data.warnings))
        self.assertFalse(any('identifier left empty' in w for w in data.warnings))


if __name__=='__main__':
    unittest.main()
