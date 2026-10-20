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
    DB --> Web[Read-only Flask / Waitress dashboard]
    Prepared --> Web
    Excel --> Web
~~~

Scanner, worker and web server are separate processes. Long OCR/model inference does not hold a SQLite transaction or block folder scanning. The worker has a separate heartbeat thread. The web server has eight request threads and at most two concurrent on-demand source renders; it never invokes OCR/model generation or claims jobs.

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

Queued processing adds verified source/template/rate/application fingerprints, complete page/workbook checks, durable evidence and publication receipts around this same converter. Detailed business rules remain in [processing_flow.md](processing_flow.md).

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

BD is the validated development scope, not arbitrary layouts or all unreadable handwriting. Cached development-set checks do not establish unseen accuracy. No cloud OCR, universal autonomous correction, speculative completion ETA, admin controls or scheduled startup is implemented. The [roadmap](pipeline_dashboard_plan.md) preserves the approval boundary for those stages.
