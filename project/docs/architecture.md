# Architecture

## Process boundaries

~~~mermaid
flowchart LR
    PDF[Configured PDF inbox] --> Scanner[Independent folder scanner]
    Scanner --> Snap[Verified original-name snapshot]
    Scanner --> DB[(SQLite jobs / attempts / events)]
    DB --> Worker[One extraction worker]
    Snap --> Worker
    Worker --> Convert[Shared OCR / parser / valuation / writer]
    Convert --> Prepared[Attempt workbook + JSON + evidence]
    Prepared --> Publish[Verified publication without overwrite]
    Publish --> Excel[Versioned Excel output]
    Worker --> DB
    DB --> Web[Flask / Waitress dashboard]
    Prepared --> Web
    Excel --> Web
~~~

The normal run_system.py entry point runs scanner, worker and web server as supervised threads in one process. Maintenance commands can still run them as separate processes. The scanner/worker retain their native ownership locks. On shutdown, intake stops and active conversion completes before the web server closes. Long OCR/model inference does not hold a SQLite transaction or block folder scanning. The worker has a separate heartbeat thread. The web server has eight request threads and at most two concurrent on-demand source renders; it never invokes OCR/model generation or claims jobs.

Direct CLI conversion uses the same pipeline but bypasses intake, job history and managed publication. No second extraction implementation exists in the dashboard.

## Conversion sequence

1. Resolve the blank template and validate input/diagnostic page limits.
2. Read all requested PDF pages through local PaddleOCR with source/settings-keyed cache reuse. Retain text, tables, confidence and transformed-page coordinates.
3. Resolve supported ambiguous goods quantities with the bounded local vision reader.
4. Parse shipment fields and bounded goods rows; normalize/group only under existing source-supported rules.
5. Count declared packages/cartons, using physical cells once. An unreadable count may use the image model when a package unit is established.
6. Prefer declared gross weight; otherwise use the approved complete corrected packing-weight sum. Ambiguous weight pages can use distinct physical cells plus their KG heading.
7. Keep unsupported fields empty; remove conflicting net weight above known gross.
8. Apply approved approximate USD product/unit rates only when appropriate; preserve source quantities and explicit values.
9. Fill the shared template and audit/item sheets, save atomically, optionally write parsed JSON.

Queued processing adds verified source/template/rate/application fingerprints, complete page/workbook checks, durable evidence and publication receipts around this same converter. Current business rules are described in [configuration](configuration.md); milestone narratives are not part of the production manuals.

## Queue lifecycle

Intake readiness is separate from conversion:

- intake_files: waiting_for_file → queued or rejected; disappearance can mark missing.
- jobs: queued → running → waiting_to_save → completed.
- Converter/integrity error: running/waiting_to_save → failed.
- An exited managed worker's unprepared attempt becomes interrupted; the job is queued again, or failed after three interrupted attempts.
- Valid prepared output is adopted and published after restart without another conversion.

waiting_for_file and interrupted are accepted job state names, but normal scanner readiness lives in intake_files and managed recovery normally requeues/fails the job while retaining interrupted attempt history. Do not sum intake rows and job rows as interchangeable counts.

## Ownership and integrity

The scanner and worker each hold a native process lock for their state directory. SQLite claim transactions enforce one running attempt and one unfinished attempt per job. A heartbeat is telemetry, not authority to steal ownership. Recovery requires acquiring the managed worker lock and matching its recorded lock path; unknown/manual owners are refused.

Source identity plus SHA-256 deduplicates unchanged arrivals. Original filenames survive snapshotting. Receipts bind job/attempt/source, prepared workbook/data hashes and output destination. Publication uses a temporary copy on the output volume and refuses an occupied final name. Existing unrelated invoices receive a versioned alternative.

An output lock or unavailable folder retains waiting_to_save and retries publication without OCR. One ordinary converter failure does not block another job and does not retry forever. A crash before preparation can repeat computation. Atomic file publication does not promise physical power-loss durability or exactly-once inference.

## Evidence and privacy

The optional pipeline observer persists structured stages, cell OCR/model results and exact input PNGs independently of invoice text. Missing evidence-write capability fails a managed attempt rather than silently losing records. Cache metrics and fresh-call metrics remain distinct. Final model contributions are separate from structured-response/cell acceptance.

The dashboard opens SQLite in read-only mode and serves artifacts only through job/attempt/event IDs with managed-path/hash checks. It is unauthenticated and loopback-only. Source/evidence/output directories contain shipment information; preserve them with state and protect local filesystem access.

## Current limits

Bangladesh and one real India shipment have passed available-sample acceptance; arbitrary layouts, unseen India PDFs and all unreadable handwriting have not. Cached checks do not establish unseen accuracy. No cloud OCR, universal autonomous correction or speculative completion ETA is implemented. Local admin controls and current-user scheduled startup are supported. The [readiness checklist](roadmap.md) records remaining gates.

## Admin transaction boundary

Stage 6 keeps dashboard readers read-only and opens a separate short writable transaction only for validated commands. Queue pause is checked inside the same transaction as a worker claim. Idempotency results and retry/reprocess state changes commit together. The web app never invokes the converter or publisher. Queue policy survives restarts, and component liveness remains separate.

## Python interfaces and modules

Imports use src.foc_extractor with project/ on sys.path; the existing CLI scripts provide that path automatically. This repository is deployed as a source application, not an installed Python wheel. Underscore-prefixed helpers are internal implementation details, not a stable external API.

### Production module map

| Module | Responsibility / main interface |
|---|---|
| models.py | LineItem and FOCData dataclasses; FOCData.to_dict() |
| ocr_engine.py | OCRWord, OCRTableCell, OCRTable, OCRResult; analyze_pdf; Paddle readers, coordinates, orientation/skew, tables and caches |
| parser.py | parse_result; bounded field/goods extraction, composition/unit normalization, company directory, grouping/source references |
| india.py | India source currency/evidence, bounded same-line/adjacent-line/table header reading, explicit export/latest labelled packing date, bounded adjacent-table/page color continuation, monetary columns, source-backed HS continuation/width, PDF-first invoice-number reading and optional handwritten heading transcription |
| jordan.py | Source-only cover headers and all-page recipient evidence; reuses bounded reference/date readers, optional local vision and the approved include-all-pages/cover-destination policy |
| packages.py | packing_packages; explicit totals/ranges/IDs/physical package cells |
| weights.py | packing_weight; complete corrected physical KG-cell sums |
| local_vision.py | transcribe_cell and resolve_quantities; bounded Ollama transport and source/model-keyed answers |
| valuation.py | apply_valuation; separate approved BD/India category-unit rules, source-value priority, Decimal cent lines, whole-USD BD totals and cent India totals |
| excel_writer.py | populate_template; safe literal text, BD layout/style inheritance, dynamic India/Jordan goods, typed dates, regional columns/declarations and multi-page print settings, audit sheets and atomic save |
| pipeline.py | run; the shared direct/batch/worker conversion sequence |
| regions.py | Three supported layout mappings, validated country codes and destination/template identity checks |
| workbook_verification.py | verify_workbook; independent printed goods/audit/source coverage and regional print bounds; India/Jordan header values, totals, literal readable formats, carton references and visibility checks before publication |
| pipeline_config.py | PipelineConfig, load_config, attempt_metadata; validated paths and version snapshots |
| job_store.py | JobStore; short SQLite transactions, ownership, history, readiness, recovery and read-only access |
| folder_intake.py | FolderScanner.scan_once; verified stable snapshots; SourceChangedError/InvalidPDFError |
| process_lock.py | process_lock context manager; native process ownership released by OS |
| queue_worker.py | QueueWorker context manager/run_once; verification, preparation, save retry and crash reconciliation |
| processing_evidence.py | Optional observations, EvidenceRecorder, model_image and page_preview |
| system_runner.py | run_system; shared configuration, ownership, scanner/worker/web lifecycle and graceful shutdown |
| dashboard.py | create_app and DashboardData; read-only view model, guarded admin commands, local HTTP routes and user-facing summaries |
| frontend/templates / frontend/static (outside backend package) | Jinja pages and local CSS/JavaScript; no extraction logic |

### Shared conversion API

~~~python
from pathlib import Path
import sys
sys.path.insert(0, str(Path("project").resolve()))
from src.foc_extractor.pipeline import run

output = run(
    Path("C:/shipments/input.pdf"),
    output_dir=Path("C:/shipments/invoices"),
    cache_dir=Path("project/.cache/ocr"),
    save_json=True,
    local_model="qwen3-vl:latest",
)
~~~

run(pdf, template=None, output_dir=None, save_json=False, max_pages=None, cache_dir=None, local_model=DEFAULT_MODEL, observer=None, region=None) returns the saved workbook Path. The Python function's omitted output_dir resolves under output/<regional-folder> in the current working directory; pass explicit directories for embedding. cache_dir=None disables that cache path. max_pages is a diagnostic positive limit. Explicit region values are BD, INDIA and JORDAN; omitted region retains legacy source/template selection. Regional selection alone does not establish Jordan readiness.

The optional observer receives callback(event_dict, png=None). Events are plain dictionaries; png is exact image bytes for a vision_request. The observer is scoped through ContextVar and reset after conversion. Its failure raises EvidenceWriteError, deliberately outside the normal model-unavailable fallback exception set. Do not mutate extraction state from an observer.

parse_result(ocr_result, source, *, region=None) returns FOCData; explicit INDIA enables its source-only regional rules. Existing Bangladesh callers retain their date/grouping behavior. analyze_pdf(pdf_path, max_pages=None, cache_dir=None) returns OCRResult. apply_valuation(data) mutates its argument and returns None. populate_template(template, output, data) writes the workbook and returns None. They are lower-level operations; prefer run to keep the complete rule sequence.

transcribe_cell(crop, model, cache_dir=None, prompt=PROMPT, schema=SCHEMA, context=None) returns (answer_dict_or_None, provenance_string). Transport errors can raise; quantity/package/weight callers decide fallback and acceptance. A structured answer is not itself accepted shipment data. resolve_quantities mutates unresolved OCR table cells while retaining original_content.

packing_packages(ocr, carton_range=None, pdf=None, cache_dir=None, local_model=None) returns total/basis/entries/reason, optionally carton_ids. packing_weight(ocr, pdf, cache_dir=None, local_model=None) returns total_kg/cells/reason. None totals mean not established; incomplete cells must not be treated as a zero-weight/package shipment.

### Managed APIs

load_config(path=ROOT/"pipeline_config.json") returns a frozen PipelineConfig. to_dict() serializes Paths as strings. attempt_metadata(config) snapshots source/template/rates/Python/model-name configuration without contacting Ollama; the actual model digest starts unknown.

JobStore(path, read_only=False) initializes/migrates writable state. read_only=True requires an existing supported database, opens SQLite mode=ro and rejects writes. Read methods include get_job, get_attempt, counts, attempts, events, components, intake_files and unfinished_attempts.

Write transitions include enqueue, observe_intake/finish_intake/mark_missing_intakes, claim_next, heartbeat, prepare, publication_error, finish, recover_attempt, component/touch_worker, processing_event and retry. Prefer the scanner/worker coordinator over calling them manually. In particular, recover_attempt is only safe while holding the matching native lock; a timestamp does not grant ownership. Public retries use the guarded admin-command API rather than direct transition calls.

FolderScanner(config, store).scan_once() returns scanned_at/incoming_dir/folder_error/accepted_job_ids/errors/intake_counts/jobs plus per-region folders. Incoming_dir retains the Bangladesh path; enabled-folder counts/errors/jobs are aggregated. India is opt-in with an explicit folder pair. The scanner CLI adds process locking, repeated polling and component health; a direct scan_once call is not a background service.

QueueWorker(config, store) must be used as a context manager. It acquires the native lock, recovers owned interrupted attempts and starts an independent heartbeat. run_once() retries owned prepared saves and processes at most one queued job; it returns a newly processed attempt ID or None. None does not mean all pending saves succeeded. Exiting the context stops heartbeats and releases the lock.

create_app(config) returns the local Flask WSGI app with read-only views and protected Stage 6 commands. Its DashboardData reader is exposed at app.extensions["dashboard_data"] for tests/internal use. Start it with run_dashboard.py / Waitress, not Flask debug mode.

model_image(store, job_id, event_id) returns verified PNG bytes for a retained vision request. page_preview(store, job_id, page, event_id=None) returns an on-demand PNG after source/OCR artifact verification. Page numbers here are one-based; OCR dataclass page indices are zero-based.

### Data classes and internal references

FOCData holds source_file; OCR coverage/backend; invoice number/date; consignee/address; marks/cartons; destination/port/terms; package count; gross/net weights; currency/total; template type; LineItem list and warnings. Every optional value defaults to None except currency USD and list fields.

LineItem holds description, quantity, unit, weight_kg, hs_code, unit_price, amount, source_page, confidence and source_refs. Table source references use page:table:row with one-based components; grouping preserves all contributing references. They are audit identifiers, not arbitrary filesystem paths.

OCRResult holds page text, words, tables, coverage, warnings, DPI and page transforms. OCRWord bounds and table/cell boxes are in the transformed rendered page coordinate system. Cell indices/pages are zero-based; dashboard observations convert pages to one-based. See [data and evidence](architecture.md) and [OpenAPI schemas](openapi.json).

JobStore.queue_control reads persisted pause state. JobStore.admin_command(request_id, action, job_id=None, attempt_id=None) validates and transactionally records pause/resume/retry/reprocess/retry_save commands; duplicate IDs return their saved results. claim_next checks pause before creating an attempt.

`windows_startup.py` owns current-user Task Scheduler registration, status/management, native stop events and rotated background logs. It calls the existing launcher and never replaces extraction or queue recovery. Task management uses encoded PowerShell arguments and an ownership marker; install refuses replacement and uninstall refuses a running task.

`invoice_preview.py` reads verified workbook bytes into a bounded, escaped HTML invoice sheet. `development_reset.py` supports the standard main workspace and the isolated development workspace. The combined launcher coordinates clearing with separate scanner/worker guards, archives generated files and backs up/resets history with rollback. The main System page exposes Clear data; a standalone dashboard without the coordinator does not. Main archives live under `runtime/cleared`, separate from active state and artifacts.

`runtime_settings.py` validates/persists ten dashboard overrides under the fixed state root, accepting the compatible seven-field payload when all India fields are omitted. The combined launcher applies them under scanner/worker guards and restores them at startup. `local_vision.vision_limits` scopes generation/context/timeout settings to each worker conversion; existing standalone callers retain defaults. See [configuration](configuration.md) for POST /api/settings and folder/cache behavior.

## Stored data contract

### SQLite schema 6

The database has application ID 0x464F4349 and user_version 6. Migrations 1/2/3/4/5 to 6 are supported by writable initialization. The dashboard validates an existing schema and never migrates it. Schema 6 adds jobs.region (BD/INDIA/JORDAN), defaulting retained jobs to BD without moving snapshots/output or rewriting historical attempts.

| Table | Key / content |
|---|---|
| jobs | Autoincrement id; source_path, normalized source_identity, source_sha256, immutable snapshot_path, region, state, manual_edit_json and created/updated UTC timestamps |
| attempts | Autoincrement id and job_id; owner worker_id, lifecycle timestamps/state, metadata JSON, output/error/issues and optional prepared receipt_path |
| events | Autoincrement id, job/optional attempt, created_at, event kind and JSON details |
| intake_files | source_identity key; source path, metadata/content signature, stable_since/last_seen Unix time, readiness state/error/job |
| queue_control | Singleton pause policy and UTC update time; new queues start resumed |
| admin_commands | UUID request ID, action, optional job/attempt IDs, time and saved result JSON; durable replay protection/audit |
| components | scanner/worker name key; owner, PID, state, heartbeat_at, error |

Jobs uniquely identify source identity/content hash. Partial unique indexes enforce one running attempt globally and one unfinished attempt per job. Foreign keys are enabled on connections. Transactions are short; no inference runs inside them.

Attempt metadata includes configuration, application version/hash, Python version, region, actual template path/hash, rates hash, configured model, resolved model digest when known, native worker lock/PID and a compact processing summary. Historical BD attempts/receipts without region remain readable as BD. New receipts record region and recovery checks it against the job. The same accepted path/content cannot be reassigned to a different region. Issues are strings independent of success/failure; an old missing:net_weight_kg issue does not mean conversion failed. Net weight is no longer required merely because the invoice is non-BD.

Processing summary counts vision attempts, fresh calls/responses, cached responses and accepted cells. vision_contributions is null until the final decision, [] for no linked contribution, or field/source-reference entries. Legacy cached evidence may lack exact historical model/image telemetry: keep unknown values unknown.

### Managed layout

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

### Processing event families

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

### Workbook contract

The first worksheet is the invoice using the shared blank template. Extraction_Audit records extracted values/page coverage/diagnostics. Extracted_Items contains row data, rates/amounts and source references when goods exist. Diagnostics do not become validation/intervention wording on the invoice sheet. Source strings are literal text rather than executable Excel formulas.

BD goods begin at row 33 and expanded rows inherit formatting; the total/footer move with them. The master controls future appearance. Rates/line amounts appear on the item sheet while the existing invoice layout shows shipment total. Native A4 print settings and continuation identity belong to the shared writer/template.

For consistent backup/restore see [operations](operations.md#backup-and-restore). Manual saves retain base-attempt attribution and validated changes; source evidence is never relabelled as a manual extraction.
