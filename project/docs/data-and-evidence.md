# Data, state and evidence

## SQLite schema 5

The database has application ID 0x464F4349 and user_version 5. Migrations 1/2/3/4 to 5 are supported by writable initialization. The dashboard validates an existing schema and never migrates it.

| Table | Key / content |
|---|---|
| jobs | Autoincrement id; source_path, normalized source_identity, source_sha256, immutable snapshot_path, state and created/updated UTC timestamps |
| attempts | Autoincrement id and job_id; owner worker_id, lifecycle timestamps/state, metadata JSON, output/error/issues and optional prepared receipt_path |
| events | Autoincrement id, job/optional attempt, created_at, event kind and JSON details |
| intake_files | source_identity key; source path, metadata/content signature, stable_since/last_seen Unix time, readiness state/error/job |
| queue_control | Singleton pause policy and UTC update time; new queues start resumed |
| admin_commands | UUID request ID, action, optional job/attempt IDs, time and saved result JSON; durable replay protection/audit |
| components | scanner/worker name key; owner, PID, state, heartbeat_at, error |

Jobs uniquely identify source identity/content hash. Partial unique indexes enforce one running attempt globally and one unfinished attempt per job. Foreign keys are enabled on connections. Transactions are short; no inference runs inside them.

Attempt metadata includes configuration, application version/hash, Python version, template/rates hashes, configured model, resolved model digest when known, native worker lock/PID and a compact processing summary. Issues are strings independent of success/failure; missing:net_weight_kg does not mean conversion failed.

Processing summary counts vision attempts, fresh calls/responses, cached responses and accepted cells. vision_contributions is null until the final decision, [] for no linked contribution, or field/source-reference entries. Legacy cached evidence may lack exact historical model/image telemetry: keep unknown values unknown.

## Managed layout

~~~text
artifact_dir/
  inputs/<source-identity-hash>/<source-sha256>/<original-name>.pdf
  jobs/<job-id>/attempt-<attempt-id>/
    <generated-name>.xlsx
    <source-stem>.json
    ready.json
    evidence/
      ocr.json
      <exact-png-sha256>.png
~~~

The source snapshot keeps its original basename. Attempt JSON is FOCData.to_dict(), with source-derived goods, approved valuation results and diagnostics. ready.json records job_id, attempt_id, source_sha256, workbook_name/workbook_sha256, data_name/data_sha256 and destination.

Ready receipts are written before the SQLite prepare transition. This permits recovery after receipt publication but before state commit. A matching already-published workbook is reconciled after a crash before completion commit. Corrupt prepared artifacts are not silently served/published.

## Processing event families

| Kind | Main payload |
|---|---|
| stage | Stage, started/completed/failed, elapsed seconds, optional error |
| ocr_cache / ocr_page | Fresh/cache state, page/word/table counts, DPI/transforms where available |
| ocr_document | Retained original OCR JSON artifact path/hash, page count/transforms |
| cell_ocr | Field/page/box, OCR texts/scores, candidate, acceptance and preprocessing |
| field_source | Field, selected value and method: PDF, filename policy, directory, derived sum or approved rates |
| field_cache / field_evidence | Cached or current package/weight basis, cells/entries, totals and reason |
| field_decision | Accepted/rejected field decision, such as conflicting net/gross |
| valuation_rate | Approved approximate rule/rate/unit and source references |
| vision_request | Correlation ID, field/page/box, original reading, exact PNG path/hash, prompt/schema/settings |
| vision_inference | A fresh chat request is about to be made; distinct from a cache lookup |
| vision_response | Answer, structured flag, done reason, model/digest, cached flag, available metrics and elapsed time |
| vision_decision | Candidate, acceptance and reason under extraction rules |
| vision_failed | Model/request failure, available model identity and diagnostic content |
| invoice_evidence | Final goods references, diagnostics, unresolved fields and linked vision contributions |

Events have job/attempt/time on the enclosing SQLite row. Not all methods have precise field-to-word links; the system does not invent them. Cached Ollama timing describes the historical cached request, not current compute.

## Workbook contract

The first worksheet is the invoice using the shared blank template. Extraction_Audit records extracted values/page coverage/diagnostics. Extracted_Items contains row data, rates/amounts and source references when goods exist. Diagnostics do not become validation/intervention wording on the invoice sheet. Source strings are literal text rather than executable Excel formulas.

BD goods begin at row 33 and expanded rows inherit formatting; the total/footer move with them. The master controls future appearance. Rates/line amounts appear on the item sheet while the existing invoice layout shows shipment total. Native A4 print settings and continuation identity belong to the shared writer/template.

## Retention and backup boundary

Retain database, snapshots, attempt artifacts and published invoices together. Do not remove evidence merely because the OCR cache can be rebuilt. Cache cleanup must never target artifact_dir. No automatic cleanup/retention workflow is enabled.

Backing up only the .xlsx loses provenance/restart capability. Backing up only SQLite leaves file references broken. Paths are recorded absolutely; restoring to a different directory/machine requires planned path migration, not blind SQL replacement. See [operations](operations.md).

Manual saves retain the base attempt and validated changes in jobs.manual_edit_json and attempt metadata. See [editing](manual-invoice-editing.md).
