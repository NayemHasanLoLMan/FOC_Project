"""QA contracts are development-only and must not become production lookups."""
import hashlib
import json
from pathlib import Path
import sys
import unittest

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from development.analysis.jordan_readiness import readiness, template_checks, writer_probe


class JordanReadinessTests(unittest.TestCase):
    def test_source_contract_covers_every_available_page_and_preserves_references(self):
        contracts = json.loads((ROOT/'development/analysis/baseline.json').read_text())['JORDAN']['samples']
        self.assertEqual(set(contracts), {p.name for p in (ROOT/'examples/jordan').glob('*.pdf')})
        self.assertEqual(sum(c['pages'] for c in contracts.values()), 28)
        for name, contract in contracts.items():
            source = ROOT/'examples/jordan'/name
            reference = ROOT/'expected_outputs/jordan'/name.replace('-D.pdf', '-I.xlsx')
            with pymupdf.open(source) as pdf:
                self.assertEqual(len(pdf), contract['pages'])
            self.assertEqual(len(contract['page_checks']), contract['pages'])
            self.assertTrue(all(checks for checks in contract['page_checks']))
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), contract['source_sha256'])
            self.assertEqual(hashlib.sha256(reference.read_bytes()).hexdigest(), contract['reference_sha256'])
        self.assertEqual(contracts['26S5173-D.pdf']['destination_conflict_pages'], [6])

    def test_readiness_report_is_separate_from_extraction_and_keeps_intake_disabled(self):
        result = readiness()
        self.assertEqual(result['source_pages'], 28)
        self.assertFalse(result['automatic_intake_enabled'])
        self.assertTrue(all(s['contract_matches_source'] and s['reference_unchanged'] for s in result['samples']))
        self.assertEqual(sum(s['embedded_text_pages'] for s in result['samples']), 0)
        self.assertEqual(result['writer_probe']['synthetic_requested_rows'], 25)
        self.assertEqual(result['writer_probe']['written_rows'],25)
        self.assertTrue(result['writer_probe']['publication_check_passed'])
        self.assertEqual(result['template']['duplicate_labels'],{})

    def test_report_helpers_leave_master_and_sources_unchanged(self):
        template = ROOT/'templates/JORDAN_template.xlsx'
        source = ROOT/'examples/jordan/26S5172-D.pdf'
        before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (template, source)]
        template_checks(template)
        writer_probe(source, template, rows=1)
        self.assertEqual(before, [hashlib.sha256(p.read_bytes()).hexdigest() for p in (template, source)])
