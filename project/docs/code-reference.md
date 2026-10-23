# Python code reference

Imports use src.foc_extractor with project/ on sys.path; the existing CLI scripts provide that path automatically. This repository is deployed as a source application, not an installed Python wheel. Underscore-prefixed helpers are internal implementation details, not a stable external API.

## Production module map

| Module | Responsibility / main interface |
|---|---|
| models.py | LineItem and FOCData dataclasses; FOCData.to_dict() |
| ocr_engine.py | OCRWord, OCRTableCell, OCRTable, OCRResult; analyze_pdf; Paddle readers, coordinates, orientation/skew, tables and caches |
| parser.py | parse_result; bounded field/goods extraction, composition/unit normalization, company directory, grouping/source references |
| india.py | India source currency/evidence, bounded same-line/adjacent-line/table header reading, explicit export/latest labelled packing date, bounded adjacent-table/page color continuation, monetary columns, source-backed HS continuation/width, PDF-first invoice-number reading and optional handwritten heading transcription |
| packages.py | packing_packages; explicit totals/ranges/IDs/physical package cells |
| weights.py | packing_weight; complete corrected physical KG-cell sums |
| local_vision.py | transcribe_cell and resolve_quantities; bounded Ollama transport and source/model-keyed answers |
| valuation.py | apply_valuation; separate approved BD/India category-unit rules, source-value priority, Decimal cent lines, whole-USD BD totals and cent India totals |
| excel_writer.py | populate_template; safe literal text, BD layout/style inheritance, dynamic India goods/typed dates/declarations, audit sheets and atomic save |
| pipeline.py | run; the shared direct/batch/worker conversion sequence |
| regions.py | Three supported layout mappings, validated country codes and destination/template identity checks |
| workbook_verification.py | verify_workbook; independent printed goods/audit/source coverage and regional print bounds; India header values, literal readable formats, carton references and visibility checks before publication |
| pipeline_config.py | PipelineConfig, load_config, attempt_metadata; validated paths and version snapshots |
| job_store.py | JobStore; short SQLite transactions, ownership, history, readiness, recovery and read-only access |
| folder_intake.py | FolderScanner.scan_once; verified stable snapshots; SourceChangedError/InvalidPDFError |
| process_lock.py | process_lock context manager; native process ownership released by OS |
| queue_worker.py | QueueWorker context manager/run_once; verification, preparation, save retry and crash reconciliation |
| processing_evidence.py | Optional observations, EvidenceRecorder, model_image and page_preview |
| system_runner.py | run_system; shared configuration, ownership, scanner/worker/web lifecycle and graceful shutdown |
| dashboard.py | create_app and DashboardData; read-only view model, guarded admin commands, local HTTP routes and user-facing summaries |
| frontend/templates / frontend/static (outside backend package) | Jinja pages and local CSS/JavaScript; no extraction logic |

## Shared conversion API

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

run(pdf, template=None, output_dir=None, save_json=False, max_pages=None, cache_dir=None, local_model=DEFAULT_MODEL, observer=None) returns the saved workbook Path. Unlike CLI defaults, the Python function's omitted output_dir resolves to output/bangladesh in the current working directory; pass explicit directories for embedding. cache_dir=None disables that cache path. max_pages is a diagnostic positive limit.

The optional observer receives callback(event_dict, png=None). Events are plain dictionaries; png is exact image bytes for a vision_request. The observer is scoped through ContextVar and reset after conversion. Its failure raises EvidenceWriteError, deliberately outside the normal model-unavailable fallback exception set. Do not mutate extraction state from an observer.

parse_result(ocr_result, source, *, region=None) returns FOCData; explicit INDIA enables its source-only regional rules. Existing Bangladesh callers retain their date/grouping behavior. analyze_pdf(pdf_path, max_pages=None, cache_dir=None) returns OCRResult. apply_valuation(data) mutates its argument and returns None. populate_template(template, output, data) writes the workbook and returns None. They are lower-level operations; prefer run to keep the complete rule sequence.

transcribe_cell(crop, model, cache_dir=None, prompt=PROMPT, schema=SCHEMA, context=None) returns (answer_dict_or_None, provenance_string). Transport errors can raise; quantity/package/weight callers decide fallback and acceptance. A structured answer is not itself accepted shipment data. resolve_quantities mutates unresolved OCR table cells while retaining original_content.

packing_packages(ocr, carton_range=None, pdf=None, cache_dir=None, local_model=None) returns total/basis/entries/reason, optionally carton_ids. packing_weight(ocr, pdf, cache_dir=None, local_model=None) returns total_kg/cells/reason. None totals mean not established; incomplete cells must not be treated as a zero-weight/package shipment.

## Managed APIs

load_config(path=ROOT/"pipeline_config.json") returns a frozen PipelineConfig. to_dict() serializes Paths as strings. attempt_metadata(config) snapshots source/template/rates/Python/model-name configuration without contacting Ollama; the actual model digest starts unknown.

JobStore(path, read_only=False) initializes/migrates writable state. read_only=True requires an existing supported database, opens SQLite mode=ro and rejects writes. Read methods include get_job, get_attempt, counts, attempts, events, components, intake_files and unfinished_attempts.

Write transitions include enqueue, observe_intake/finish_intake/mark_missing_intakes, claim_next, heartbeat, prepare, publication_error, finish, recover_attempt, component/touch_worker, processing_event and retry. Prefer the scanner/worker coordinator over calling them manually. In particular, recover_attempt is only safe while holding the matching native lock; a timestamp does not grant ownership. retry exists internally but no public HTTP retry control is implemented.

FolderScanner(config, store).scan_once() returns scanned_at/incoming_dir/folder_error/accepted_job_ids/errors/intake_counts/jobs. The scanner CLI adds process locking, repeated polling and component health; a direct scan_once call is not a background service.

QueueWorker(config, store) must be used as a context manager. It acquires the native lock, recovers owned interrupted attempts and starts an independent heartbeat. run_once() retries owned prepared saves and processes at most one queued job; it returns a newly processed attempt ID or None. None does not mean all pending saves succeeded. Exiting the context stops heartbeats and releases the lock.

create_app(config) returns the local Flask WSGI app with read-only views and protected Stage 6 commands. Its DashboardData reader is exposed at app.extensions["dashboard_data"] for tests/internal use. Start it with run_dashboard.py / Waitress, not Flask debug mode.

model_image(store, job_id, event_id) returns verified PNG bytes for a retained vision request. page_preview(store, job_id, page, event_id=None) returns an on-demand PNG after source/OCR artifact verification. Page numbers here are one-based; OCR dataclass page indices are zero-based.

## Data classes and internal references

FOCData holds source_file; OCR coverage/backend; invoice number/date; consignee/address; marks/cartons; destination/port/terms; package count; gross/net weights; currency/total; template type; LineItem list and warnings. Every optional value defaults to None except currency USD and list fields.

LineItem holds description, quantity, unit, weight_kg, hs_code, unit_price, amount, source_page, confidence and source_refs. Table source references use page:table:row with one-based components; grouping preserves all contributing references. They are audit identifiers, not arbitrary filesystem paths.

OCRResult holds page text, words, tables, coverage, warnings, DPI and page transforms. OCRWord bounds and table/cell boxes are in the transformed rendered page coordinate system. Cell indices/pages are zero-based; dashboard observations convert pages to one-based. See [data and evidence](data-and-evidence.md) and [OpenAPI schemas](openapi.json).

JobStore.queue_control reads persisted pause state. JobStore.admin_command(request_id, action, job_id=None, attempt_id=None) validates and transactionally records pause/resume/retry/reprocess/retry_save commands; duplicate IDs return their saved results. claim_next checks pause before creating an attempt.

See [manual invoice editing](manual-invoice-editing.md) for the simplified dashboard and safe versioned editing workflow.

The dashboard shares one responsive stylesheet, `frontend/static/dashboard.css`, using local system fonts and no remote font or UI dependencies. Job tables become cards below 760px; sidebar navigation moves above content below 850px. Invoice and image tables retain their own scrolling area. Keyboard focus, skip navigation and reduced-motion preferences are supported. Editor saves and all data operations remain in the existing JavaScript/backend.

`src/foc_extractor/windows_startup.py` owns current-user Task Scheduler registration, status/management, native stop events and rotated background logs. It calls the existing launcher and never replaces extraction or queue recovery. Task management uses encoded PowerShell arguments and an ownership marker; install refuses replacement and uninstall refuses a running task.

`invoice_preview.py` reads verified workbook bytes into a bounded, escaped HTML invoice sheet. `development_reset.py` supports the standard main workspace and the isolated development workspace. The combined launcher coordinates clearing with separate scanner/worker guards, archives generated files and backs up/resets history with rollback. The main System page exposes Clear data; a standalone dashboard without the coordinator does not. Main archives live under `runtime/cleared`, separate from active state and artifacts.

`runtime_settings.py` validates/persists the seven dashboard overrides under the fixed state root. The combined launcher applies them under scanner/worker guards and restores them at startup. `local_vision.vision_limits` scopes generation/context/timeout settings to each worker conversion; existing standalone callers retain defaults. See configuration.md for POST /api/settings and folder/cache behavior.


