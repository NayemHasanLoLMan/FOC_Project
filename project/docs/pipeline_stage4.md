# Stage 4 — processing evidence and review artifacts

Implemented and verified on 20 October 2026. Stop before Stage 5 for user approval. This stage adds the data and image helpers for review; the web dashboard is not implemented yet. Scanner/worker commands and invoice-generation rules are unchanged.

## What is recorded

The queue worker passes an optional observer to the existing shared `pipeline.run`. Single-file/batch callers do not need an observer and retain their existing return value and output. Python context variables scope observations to a conversion; no console scraping, new dependency, database schema change or external service was added.

Each processing event is retained in the existing SQLite events table, linked to its job/attempt and UTC timestamp. The attempt metadata also keeps a compact processing summary for later dashboard reads. Observations include:

- Pipeline, OCR, quantity fallback, parsing, package extraction, weight extraction, valuation and workbook stage starts/completions/failures with elapsed seconds. OCR cache use, fresh/checkpoint page work and page transforms are distinct events. A full OCR-cache hit does not pretend pages were freshly processed.
- PDF and filename invoice-number selection, explicit versus packing-list dates, labelled consignee blocks versus maintained directory address/BIN/shipping-mark fallbacks, explicit weights/values, corrected packing-weight sums and approved approximate valuation rules. Existing goods source references survive grouping in the final evidence. Exact field/word provenance is not invented where the parser only has a document-level reading.
- Cell OCR readings/confidence/candidates and vision request/response/decision events. Each vision region includes a correlation ID, field, one-based page, transformed-page pixel bounds, DPI, available orientation/skew transform, original OCR reading and preprocessing details. Weight composites retain header/body bounds, the gap and scale.
- The configured and resolved model, full installed digest, prompt, schema, temperature/context/output allowance, request timeout and available Ollama timing/token metrics. Cached metrics are explicitly labelled as belonging to the cached response; they are not current inference time. Missing metrics remain absent.
- Completed, rejected, invalid/truncated and unavailable model outcomes. A structured model response is not automatically an accepted cell. A cell accepted by extraction rules is not automatically an invoice contribution: final quantity source references and completed package/weight totals establish that separately.

`metadata.processing` separates `vision_attempts`, `fresh_calls`, `fresh_responses`, `cached_responses`, `accepted_cells` and final `vision_contributions`. A vision attempt includes cache lookup/model resolution; only `vision_inference` denotes a fresh chat request. Empty contributions mean no supported final invoice value was linked to vision; `null` means the conversion has not reached that decision. A legacy field cache may carry model-derived evidence without a request in the current run, so never label a job OCR-only from fresh-call count alone. Retained field evidence/contributions take priority; missing historical telemetry stays unknown.

Missing final fields and rejected/failed vision readings are retained as issue codes on the attempt, independently of completed/failed job status. For example, `missing:net_weight_kg` describes an intentionally blank unsupported field; it does not mean invoice generation failed or require human intervention. Raw diagnostics remain available separately. Issues and processing metadata survive prepared-save retries, completion and restart.

## Retained files and previews

Each attempt stores review files under `artifact_dir/jobs/<job>/attempt-<attempt>/evidence`:

- `ocr.json`: original OCR document text, words/confidence, tables, source bounds and page transforms, retained before vision changes quantity cells. The event records its SHA-256.
- `<sha256>.png`: exact RGB PNG bytes used in the model request, including resizing and weight-header composites. Identical images within the attempt share a file. The same input is retained when its answer comes from cache or the model is unavailable; this records the attempted input, not proof of a successful network call.

`processing_evidence.model_image(store, job_id, event_id)` returns a retained request image after managed-path/hash checks. `page_preview(store, job_id, page, event_id=None)` verifies the immutable PDF and retained OCR evidence, renders the source page in the recorded OCR coordinate system and optionally highlights the request region before resizing. Page previews are generated on demand, not pre-rendered for every source page. These helpers are ready for Stage 5 routes; no browser interface is exposed yet. Missing/corrupt images produce explicit review errors and do not modify an invoice.

Retention policy: retain job snapshots, attempt artifacts and state together until an operator deliberately archives/removes the job under a future retention workflow. No automatic evidence cleanup is enabled. OCR/model cache cleanup must not delete managed job artifacts. Review files contain shipment information; back them up and protect them like the source PDFs. A legacy cached result cannot supply an exact historical model-input image if it was never retained; do not synthesize one and call it the original.

If managed evidence cannot be persisted, the worker fails that attempt rather than publishing an invoice with silently missing audit records. Existing preparation/publication recovery remains available. Review information never appears as validation/intervention wording on the printed invoice.

## Acceptance

| Check | Result |
|---|---|
| Complete regression suite | 190 tests pass; 13 added for Stage 4 |
| Actual worker run | 20 completed invoices, 66 source pages, 89 goods rows; no failed/pending saves |
| Invoice regression | All invoice cell values/types/styles, merges, dimensions, alignment and print/header/footer settings match established outputs |
| Reference comparison | Unchanged: strict goods recall 58/75 and precision 58/82 |
| Evidence attribution | 17 invoices without model contribution; 3 with model contribution; 6 cached accepted readings, zero fresh inference in this real run |
| Exact images | All 6 request images pass hash, dimensions and event-correlation checks; a unit test compares retained PNG bytes with the actual encoded request payload |
| Source review | Real handwritten package highlight and corrected weight/header composite visually inspected; preview bounds/transform/source-hash checks also tested |
| Error/recovery coverage | Fresh/cache responses, unavailable model, rejection, truncation, malformed JSON/message, missing/corrupt/outside-path artifacts, observer failure, owner enforcement and prepared-worker restart covered |
| Protected assets | All 72 protected files unchanged, including templates, sources, manual references, rates/dependencies and canonical outputs |
| Runtime safety | Schema remains 3; default production queue stays empty; no continuous process or startup task remains running |

Evidence: [regression summary](../reports/pipeline_stage4_20261020/regression.json), [read-only checks](../reports/pipeline_stage4_20261020/verify_stage4.py), [reference comparison](../reports/pipeline_stage4_20261020/after/accuracy.md), and [review samples](../reports/pipeline_stage4_20261020/review_samples). Final isolated invoices are under `reports/pipeline_stage4_20261020/final_demo/output`.

The real acceptance run reused existing OCR/model caches; fresh inference and failed responses were tested with controlled transport responses, not forced through another lengthy live model inference. This stage verifies provenance and preserves existing extraction accuracy; it does not establish accuracy on unseen PDFs. Exact manual-reference discrepancies remain governed by the previously approved PDF-first rules. Native Excel print rendering was not repeated because invoice formatting/print settings match the established workbooks.

Next approval: Stage 5, the read-only local dashboard for health, counts, job history, issues, invoice/PDF downloads and the retained review images. Admin controls and automatic Windows startup remain later stages.
