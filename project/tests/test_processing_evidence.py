import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.local_vision import transcribe_cell, resolve_quantities
from src.foc_extractor.ocr_engine import OCRResult, OCRTable, OCRTableCell
from src.foc_extractor.pipeline_config import load_config, attempt_metadata
from src.foc_extractor.processing_evidence import (EvidenceRecorder, EvidenceWriteError, emit, observed,
    accepted_vision_refs, model_image, page_preview)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        config = self.root / 'pipeline_config.json'
        config.write_text((ROOT / 'pipeline_config.json').read_text())
        self.config = load_config(config)
        self.store = JobStore(self.config.state_dir / 'jobs.sqlite3')
        self.source = self.config.artifact_dir / 'inputs/shipment.pdf'
        self.source.parent.mkdir(parents=True)
        with pymupdf.open() as pdf:
            pdf.new_page(width=200, height=200).insert_text((30, 30), 'SOURCE')
            pdf.save(self.source)
        self.job = self.store.enqueue(self.config.incoming_dir / self.source.name,
            hashlib.sha256(self.source.read_bytes()).hexdigest(), self.source)
        self.attempt = self.store.claim_next('test', attempt_metadata(self.config))
        self.folder = self.config.artifact_dir / 'jobs' / str(self.job) / f"attempt-{self.attempt['id']}" / 'evidence'
        self.recorder = EvidenceRecorder(self.store, self.attempt, self.folder)
        self.image = Image.new('RGB', (80, 40), 'white')
        self.tags = {'models': [{'name': 'test:latest', 'digest': 'digest-abc'}]}
        self.answer = {'done_reason': 'stop', 'message': {'content': '{"text":"2 PCS"}'}, 'eval_count': 7}
        self.context = {'call_id': 'call-1', 'field': 'goods_quantity', 'page': 1,
                        'bbox': [10, 10, 50, 40], 'source_ref': '1:1:2'}

    def events(self, kind):
        return [e for e in self.store.events(self.job) if e['details'].get('kind') == kind]

    def transcribe(self, response=None, **kwargs):
        @observed
        def work():
            return transcribe_cell(self.image, 'test', self.root / 'cache', context=self.context, **kwargs)
        with patch('src.foc_extractor.local_vision._request', side_effect=[self.tags, response or self.answer]) as request:
            answer = work(observer=self.recorder)
        return answer, request

    def test_exact_sent_png_cached_answer_and_actual_digest_are_retained(self):
        first, request = self.transcribe()
        sent = base64.b64decode(request.call_args.args[1]['messages'][0]['images'][0])
        event = self.events('vision_request')[0]
        self.assertEqual(model_image(self.store, self.job, event['id']), sent)
        @observed
        def cached():
            return transcribe_cell(self.image, 'test', self.root / 'cache', context=self.context)
        with patch('src.foc_extractor.local_vision._request', return_value=self.tags) as request:
            self.assertEqual(cached(observer=self.recorder), first)
        self.assertEqual(request.call_count, 1)
        summary = self.store.get_attempt(self.attempt['id'])['metadata']['processing']
        self.assertEqual((summary['vision_attempts'], summary['fresh_calls'], summary['fresh_responses'], summary['cached_responses']), (2, 1, 1, 1))
        self.assertEqual(self.store.get_attempt(self.attempt['id'])['metadata']['model_digest'], 'digest-abc')
        response = self.events('vision_response')[-1]['details']
        self.assertEqual(response['metrics_origin'], 'cached_response')
        self.assertEqual(response['metrics'], {'eval_count': 7})
        self.assertEqual(len(list(self.folder.glob('*.png'))), 1)

    def test_unavailable_model_records_failure_and_image_without_claiming_inference(self):
        @observed
        def work():
            return transcribe_cell(self.image, 'test', context=self.context)
        with patch('src.foc_extractor.local_vision._request', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError): work(observer=self.recorder)
        attempt = self.store.get_attempt(self.attempt['id'])
        self.assertEqual(attempt['metadata']['processing']['fresh_calls'], 0)
        self.assertEqual(len(self.events('vision_failed')), 1)
        self.assertTrue(attempt['issues'])
        self.assertEqual(len(list(self.folder.glob('*.png'))), 1)

    def test_truncated_and_invalid_json_responses_are_distinguished(self):
        result, _ = self.transcribe({'done_reason': 'length', 'message': {'content': ''}})
        self.assertIsNone(result[0])
        self.assertEqual(self.events('vision_response')[-1]['details']['done_reason'], 'length')
        self.assertFalse(self.events('vision_response')[-1]['details']['structured'])
        with self.assertRaises(ValueError):
            self.transcribe({'done_reason': 'stop', 'message': {'content': '{bad'}},prompt='separate invalid JSON test')
        self.assertEqual(self.events('vision_failed')[-1]['details']['raw_content'], '{bad')

    def test_quantity_acceptance_and_groupable_source_reference_are_separate_from_transport(self):
        cells = [OCRTableCell(0, 0, 'PARTICULARS'), OCRTableCell(0, 1, 'QTY'),
                 OCRTableCell(1, 0, 'CARD'), OCRTableCell(1, 1, 'Z PCS', bbox=[0, 0, 80, 40])]
        ocr = OCRResult(tables=[OCRTable(cells, 2, 2)])
        @observed
        def work():
            resolve_quantities(ocr, self.source, 'test')
            return accepted_vision_refs().copy()
        with patch('src.foc_extractor.local_vision._request', side_effect=[self.tags, self.answer]), \
             patch('src.foc_extractor.local_vision._cached_page_image', return_value=self.image):
            self.assertEqual(work(observer=self.recorder), {'1:1:2'})
        self.assertEqual(cells[-1].content, '2 PCS')
        self.assertEqual(self.events('vision_decision')[0]['details']['original'], 'Z PCS')
        self.assertTrue(self.events('vision_decision')[0]['details']['accepted'])
        self.assertEqual(accepted_vision_refs(), set())

    def test_rejected_quantity_keeps_original_and_does_not_contribute(self):
        cells = [OCRTableCell(0, 0, 'PARTICULARS'), OCRTableCell(0, 1, 'QTY'),
                 OCRTableCell(1, 0, 'CARD'), OCRTableCell(1, 1, 'Z YDS', bbox=[0, 0, 80, 40])]
        @observed
        def work():
            resolve_quantities(OCRResult(tables=[OCRTable(cells, 2, 2)]), self.source, 'test')
            return accepted_vision_refs().copy()
        with patch('src.foc_extractor.local_vision._request', side_effect=[self.tags, self.answer,self.tags]), \
             patch('src.foc_extractor.local_vision._cached_page_image', return_value=self.image):
            self.assertEqual(work(observer=self.recorder), set())
        self.assertEqual(cells[-1].content, 'Z YDS')
        self.assertFalse(self.events('vision_decision')[0]['details']['accepted'])

    def test_ocr_only_completion_and_issues_survive_save_and_store_reopen(self):
        self.recorder({'kind': 'invoice_evidence', 'vision_contributions': [], 'unresolved_fields': ['net_weight_kg']})
        receipt = self.folder.parent / 'ready.json'
        receipt.write_text('{}')
        self.store.prepare(self.attempt['id'], 'test', receipt)
        self.store.publication_error(self.attempt['id'], 'test', 'locked')
        output = self.folder.parent / 'invoice.xlsx'
        output.write_bytes(b'fixture')
        self.store.finish(self.attempt['id'], 'test', 'completed', output_path=output)
        attempt = JobStore(self.store.path).get_attempt(self.attempt['id'])
        self.assertEqual(attempt['issues'], ['missing:net_weight_kg'])
        self.assertEqual(attempt['metadata']['processing']['vision_attempts'], 0)
        self.assertEqual(attempt['metadata']['processing']['vision_contributions'], [])

    def test_missing_or_tampered_images_fail_review_without_touching_invoice_state(self):
        self.transcribe()
        event = self.events('vision_request')[0]
        path = Path(event['details']['image_path'])
        path.write_bytes(b'wrong')
        with self.assertRaises(ValueError): model_image(self.store, self.job, event['id'])
        path.unlink()
        with self.assertRaises(FileNotFoundError): model_image(self.store, self.job, event['id'])
        self.assertEqual(self.store.get_attempt(self.attempt['id'])['state'], 'running')

    def test_source_preview_uses_retained_transform_highlight_and_snapshot_hash(self):
        self.recorder({'kind': 'ocr_document', 'document': {'pages': ['SOURCE'], 'dpi': 72,
                       'page_transforms': [{'rotation': 0, 'skew': 0}]}})
        self.transcribe()
        event = self.events('vision_request')[0]
        image = Image.open(io.BytesIO(page_preview(self.store, self.job, 1, event['id'])))
        self.assertEqual(image.getpixel((10, 10)), (255, 0, 0))
        with self.assertRaises(ValueError): page_preview(self.store, self.job, 2)
        with self.assertRaises(ValueError): page_preview(self.store, self.job, 1, -1)
        self.source.write_bytes(b'tampered')
        with self.assertRaises(ValueError): page_preview(self.store, self.job, 1)

    def test_observation_failure_is_not_swallowed_as_model_unavailability(self):
        @observed
        def work():
            emit('anything')
        def broken(event, **kwargs):
            raise PermissionError('disk denied')
        with self.assertRaises(EvidenceWriteError): work(observer=broken)
        self.assertIsNone(work())

    def test_processing_events_require_live_owner(self):
        with self.assertRaises(ValueError):
            self.store.processing_event(self.attempt['id'], 'foreign', {'kind': 'stage', 'stage': 'ocr', 'status': 'started'})

    def test_malformed_message_preserves_the_failure_record(self):
        with self.assertRaises(ValueError):
            self.transcribe({'done_reason':'stop','message':None})
        self.assertEqual(len(self.events('vision_failed')), 1)

    def test_review_cannot_read_an_artifact_outside_its_attempt(self):
        self.transcribe()
        event = self.events('vision_request')[0]
        self.store.processing_event(self.attempt['id'], 'test',
            {**event['details'], 'image_path':str(self.source), 'image_sha256':hashlib.sha256(self.source.read_bytes()).hexdigest()})
        foreign = self.events('vision_request')[-1]
        with self.assertRaises(ValueError): model_image(self.store, self.job, foreign['id'])


if __name__ == '__main__':
    unittest.main()
