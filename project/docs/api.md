# HTTP API reference

Base URL: **http://127.0.0.1:8080**, or the selected --port. [openapi.json](openapi.json) describes the implemented routes and their request/response schemas. It can be opened in an OpenAPI 3.1-compatible viewer; no Swagger service is installed or exposed.

Job records have an immutable `region` (BD/INDIA/JORDAN); new attempt metadata records region and the actual `template_path`. Migrated jobs are BD; historical metadata can omit both fields. There is no region-changing command. Country intake is controlled by the saved Bangladesh, India and Jordan settings. India edits require goods `hs_code`, allow port/terms, protect country and omit BD-only fields. The server selects the contract using the saved job region. See [editing](operations.md#edit-and-add-information) and the regional OpenAPI schemas.

This is a local, unauthenticated dashboard API. GET/HEAD routes read retained state; guarded POST commands control the queue, settings, manual invoice updates and recoverable Clear data. POST /api/uploads accepts a PDF for a selected enabled country. The scanner accepts saved uploads and PDFs dropped into configured filesystem inboxes. There is no forced cancellation or arbitrary shell-command endpoint. All timestamps are UTC unless explicitly described as the PC's local date/time.

HTML detail pages use regional labels. JSON `data` and original `issues` retain historical values, including net-weight fields/notes omitted from India's presentation.

For newly generated, confidently matched invoices in all three countries, the approved factory master replaces consignee, address/tax identifiers, destination country, TIN and cover note, including explicit omissions. India's approved address contains IEC/PAN/GST. Under the approved 29 October 2026 regional rule, newly generated India invoices use CHENNAI, INDIA as discharge port and CPT as shipment terms, even when source values differ; originals are retained in field_source events with policy india_fixed_shipment. ON/ABT repeats the invoice export_date in uppercase month/day/year format (for example OCT. 14, 2026), or stays empty when that date is unavailable. The optional `data.shipment_text` and `data.remarks` store printed shipment wording and newline-separated declarations; Jordan's master omits the shipment line. Null preserves historical writer behavior; an empty string explicitly omits the wording. Original parsed values, factory ID, source row and profile checksum remain in `field_source` events with `method: approved_factory_master`. These rules do not modify existing saved invoices or reapply during manual edits. Approved shared pricing applies during generation; explicit PDF monetary values are preserved.

Automatic Jordan generation/reprocessing sets each `data.items[].origin_country` to CHINA under the approved regional rule, including for unmatched factories and explicit different source origins. This does not select a factory or change goods grouping, quantities, weights or prices. Per-item field_source events record method approved_regional_rule, policy jordan_always_china, original_value, item_index, source_page, source_refs and profile_sha256. These values are approved substitutions, not PDF extraction claims. Manual save retains explicitly entered origins without reapplying the generation rule.

Jordan settings include jordan_enabled, jordan_incoming_dir and jordan_output_dir. Both Jordan folders are required before enabling intake. Jordan detail/edit views include item origin and weight; corrected descriptions, origins and goods weights preserve existing amounts when quantity/unit/price are unchanged. The enabled countries share one scanner, worker and database.

## Access and response rules

- The server binds to 127.0.0.1; trusted Host values are localhost and 127.0.0.1.
- Nonlocal clients, cross-site fetches and mismatched Origin headers are rejected. No CORS permission is provided. Do not reverse-proxy or port-forward it.
- Responses use no-store, nosniff, no-referrer, frame denial and a same-origin content policy.
- JSON errors have an error string. HTML page errors normally render the error page; untrusted Host errors return JSON. Browser errors do not expose stack traces.
- File routes take IDs, never arbitrary paths. Source/invoice/evidence bytes must match their retained hash and managed location.
- Null means unavailable/unfinished data, not numeric zero. Optional telemetry fields can be absent. Source/model strings are data, not markup/instructions.

## JSON endpoints

| GET route | Query / result |
|---|---|
| /api/status | Live Status object: web availability/uptime, checked_at, counts, attempts, completed_with_issues, today, scanner, worker, active, intake_counts, intake_issues |
| /api/ollama | state, model, optional digest/checked_at; state is disabled, available, model_missing or unavailable |
| /api/system | folders/disk space, dependency versions, application/Python/platform, template, fingerprints, model/defaults and scan interval |
| /api/jobs | q, status, region, date, issues, page; returns jobs, total, page, pages |
| /api/jobs/{job_id} | attempt and event_page; selected attempt plus verified data, explanations, events and evidence |
| /api/jobs/{job_id}/status | Small poll response: job_id, state, status_label, updated_at |

### List filters and pagination

q is a literal case-insensitive SQL-LIKE substring of filename or recorded invoice number, with wildcard characters escaped; maximum 200 characters. status accepts waiting_for_file, queued, running, waiting_to_save, completed, failed or interrupted. date is extracted document date YYYY-MM-DD, not arrival date. issues=yes/no filters the latest attempt's recorded issue list. Omit/leave blank filters to include all.

region filters the recorded intake country: BD (Bangladesh), INDIA or JORDAN. It combines with the other filters on /jobs and /api/jobs, including pagination and refreshed results. Country labels describe the job's assigned intake country, rather than guessing from its filename.

page defaults to 1, with 25 rows ordered newest job ID first. page, attempt, event_page and event query numbers must be in 1–1,000,000. An out-of-range positive list page returns no rows rather than being silently clamped. total counts jobs, not attempts.

Historical jobs lacking field_source events can show null invoice number/date in list/search even when a verified old workbook exists. The detail data is read separately from the retained parsed JSON. Do not manufacture searchable field values from a filename.

### Status semantics

counts covers job lifecycle states. intake_counts covers file observations and is separate; a settling/rejected file may not have a job. attempts is all-time attempt count. today.received counts jobs created on the PC's local day; today.completed counts distinct jobs with a completed attempt on that day, independent of their current latest state. completed_with_issues uses the latest completed job/attempt state; missing optional fields count as issues.

scanner/worker include state, heartbeat_at, age_seconds and available PID/owner/error. An absent/stale running record is unknown. The worker threshold is 30 seconds; scanner threshold accounts for scan_interval_seconds. A heartbeat is not proof of progress or OS-lock ownership.

active can be null. Otherwise it includes job_id, stage, stage_status, last_observed_page, attempt_seconds and stage_seconds. If worker telemetry is unknown/stopped, active is retained database progress, not proof the process is currently executing. There is no estimated completion time.

Ollama is checked through its [local tags API](https://docs.ollama.com/api/tags) with a two-second timeout and ten-second cache. No inference is run. Model disabled avoids that network call. Cached check timestamps can therefore be older than the current web request.

### Detail shape

The response contains job, selected attempt (or null), attempts, method, data (FOCData or null), data_error, user_summary, stages, evidence, events, event_page and event_pages. attempt must belong to this job; otherwise 404. Events are paginated at 100; the evidence/stage summaries are not that event-page slice.

user_summary has result, how and notes for plain-language display. Evidence entries include request, related events, label, original/original_label, reading, outcome, saved and failed. The explanation distinguishes an accepted reading from one used in a final invoice field.

Raw path-serving fields such as image_path/artifact_path/output_path are removed from public job/event structures. Metadata may include recorded configuration and opaque source identity. Do not turn arbitrary metadata strings into download URLs; use the defined ID routes.

metadata.processing records attempts, fresh_calls, fresh_responses, cached_responses, accepted_cells, models and final vision_contributions. A cached answer is model-derived. Contributions null means not decided; [] means no linked final contribution. Missing historical telemetry is unknown.

## Downloads and review images

| GET route | Result / conditions |
|---|---|
| /files/jobs/{job_id}/source | application/pdf attachment, original accepted snapshot name and SHA |
| /files/attempts/{attempt_id}/invoice | .xlsx attachment for a completed attempt; validates the original workbook in retained attempt storage |
| /images/jobs/{job_id}/events/{event_id} | image/png, exact retained input of a vision_request from that job |
| /images/jobs/{job_id}/pages/{page} | image/png source preview; optional event query highlights a region from the same job/attempt |

Preview pages are one-based and must be within retained OCR coverage. Rendering uses the recorded DPI/rotation/skew before highlighting/resizing. At most two previews render concurrently; additional requests return 429 and can be retried later. Missing/corrupt files do not silently return another file or regenerate OCR.

Invoice preview and download use the same hash-verified system-saved workbook. Changes, metadata updates or removal of the published output-folder copy do not alter this saved version. Use Edit to update the current output file; internal attempt records and verified originals remain available for recovery and source review. Missing or corrupt retained originals still fail verification.

## HTML routes

/ shows overview; /jobs accepts the list filters and partial=1 for the escaped table fragment; /jobs/{job_id} accepts attempt/event_page; /system shows configuration/dependencies. /dashboard_static/... serves bundled UI assets through Flask's static endpoint; it is not an artifact API.

## Errors

| Status | Meaning |
|---|---|
| 400 | Invalid filter/number/date or untrusted Host |
| 403 | Nonlocal/cross-site/mismatched Origin request |
| 404 | Unknown job/attempt/event, missing retained file or missing preview document |
| 405 | Unsupported method for this route |
| 409 | State prevents invoice download, or retained path/hash/data verification fails |
| 429 | Source-preview capacity busy |
| 503 | Temporary database/filesystem/server-data failure; check local console |

A completed job remains completed if later review fails because an artifact was edited/deleted; the review/download request reports the problem. Source PDFs are never changed. The guarded Edit command updates the invoice through verified atomic replacement of its registered output file.

## Examples

~~~powershell
Invoke-RestMethod http://127.0.0.1:8080/api/status
Invoke-RestMethod 'http://127.0.0.1:8080/api/jobs?q=5188&status=completed&page=1'
Invoke-RestMethod http://127.0.0.1:8080/api/jobs/12
Invoke-WebRequest http://127.0.0.1:8080/files/attempts/12/invoice -OutFile C:/shipments/download.xlsx
~~~

IDs 12/5188 above illustrate the development demo; discover real IDs from /api/jobs and /api/jobs/{job_id}. GET examples do not create processing work. [CLI](operations.md#maintenance-command-reference) and [Python](architecture.md) interfaces are documented separately.

## Postman

Development checkout files: `project/development/postman/FOC-Invoice.postman_collection.json` and `Local.postman_environment.json`. They are not packaged; OpenAPI is included in production. Import both into the desktop Postman app/agent, select the local environment and send getStatus, then listJobs.

Set base_url (default http://127.0.0.1:8080), job_id, attempt_id, event_id and pdf_page from actual job responses. Example IDs are placeholders; pdf_page starts at 1 and attempt_id is a database ID, not an attempt sequence. Optional query parameters start disabled. Empty queues and absent-ID errors are valid; a blind full collection run is not an acceptance test.

For protected commands fetch getControls first for the current csrf_token. Match Origin, choose the current eligible attempt and use a new UUID request_id for each action. Reuse the same UUID only when replaying an uncertain request. Refresh the token after restart. The collection can pause, retry, reprocess, edit, change settings and clear data: use an isolated test queue for experimentation. No credentials or customer responses are shipped. Keep downloaded data local.

## Stage 6 commands

GET /api/controls returns csrf_token and queue {paused, updated_at}. GET /api/status also includes queue. Paused is a persisted policy, independent of scanner/worker health. New arrivals still queue; an existing conversion and prepared save retries continue. Resume needs a running worker and does not start a stopped process.

Every POST requires application/json, Origin equal to the exact base URL without a trailing slash, and X-CSRF-Token from this web process. Use a canonical UUID string request_id for each intended action. Reuse the same ID and identical payload to repeat an uncertain request: the original saved result is returned, even after the job changes or the web server restarts. A reused ID with another command/payload conflicts. The command token changes after web restart; fetch it again first. Browser controls handle these values automatically.

| POST route | Body in addition to request_id | Result |
|---|---|---|
| /api/queue/pause | none | Block new conversion claims after this transaction |
| /api/queue/resume | none | Permit new claims |
| /api/jobs/{job_id}/retry | attempt_id | Queue the latest failed/interrupted job for a new attempt |
| /api/jobs/{job_id}/reprocess | attempt_id | Rerun a completed job using its saved PDF and current settings; replace its registered invoice file, including manual changes |
| /api/jobs/{job_id}/retry-save | attempt_id | Record a save retry request; the running worker's next regular pass retries the prepared workbook without OCR |

attempt_id must match the latest eligible attempt in that job. This prevents a stale page or double-click from requeueing a newer failed attempt. Completed reprocessing creates a new attempt when the worker claims it, records current configuration/version fingerprints, and atomically replaces that job's registered invoice file in its existing folder. Manual changes are replaced by current extraction/default rules. Failed conversion leaves the current file intact; locked outputs wait for save recovery. Other jobs' files are never overwritten. Historical PDF/evidence/invoice downloads remain available. No inference or publication occurs inside a web request.

All commands return 200 with their accepted result; acceptance does not prove completion. A save request keeps waiting_to_save until publication succeeds. Publication already retries automatically every worker pass; this button records an explicit operator request using that same path. It does not bypass permissions, file locks or integrity checks. Stopped workers cannot perform accepted work.

400 means malformed fields/UUID; 403 means request protection failed; 404 means unknown job; 409 means a stale/ineligible action or mismatched request ID; 415 means unsupported content type. Non-command routes still reject POST with 405. Keep admin_commands audit/idempotency records with the queue backup.

Bangladesh extracted data now includes optional tin_number and import_cover_note from the PDF. Net weight is not applicable to BD and is omitted from printed/audit fields and unresolved-field lists. Other regions retain the shared model property. TIN/import cover notes use PDF values only. Bangladesh and India do not print net weight. See [configuration](configuration.md).

See [manual invoice editing](operations.md) for the simplified dashboard and safe manual invoice updates workflow.

See [invoice downloads, web preview and development reset](operations.md) for clean filenames, local viewing and the Clear data option on the main or isolated launcher.

See [editable processing settings](configuration.md#editable-dashboard-settings) for POST `/api/settings`, its twelve fields (or compatible legacy ten/seven-field requests), persistence, validation and idle-only application.

## Folder selection

POST `/api/folders/browse` accepts `{ "kind": "incoming" }` or output, plus an optional absolute `path`. It requires the combined launcher and normal JSON/Origin/CSRF protection. Omit path or use null to start at the configured parent. The response contains path, name, parent, directories and Home/drive locations. Files, dot-prefixed directories and redirected paths are not offered. No files, settings or job records are changed; no UUID is needed. A bad/unavailable directory returns 409.

The System form offers a folder-browser dialog inside the dashboard, with navigation, location entry and an explicit Use this folder button. One intake parent and one output parent each expand to country subfolders. The existing POST `/api/settings` contract now has twelve fields, with exact legacy ten/seven-field requests still supported: the browser submits Bangladesh/India child paths. Existing separate custom paths are retained unless replaced. Save settings applies selections and creates missing country directories; Jordan intake stays disabled.

Country controls add bangladesh_enabled and jordan_enabled to the settings payload. Submit all twelve fields or exact legacy ten/seven-field requests; omitted controls keep their current values. Jordan must remain false.

### Factory identification events

New conversions record kind=factory_identification in retained processing-event details. Fields include factory_id (null unless matched), status (matched, unknown, ambiguous or country_conflict), region, candidates, evidence and profile_sha256. Attempt metadata also records factory_profiles_sha256. These are identification records only; they do not mean that factory defaults were applied. Historical attempts can omit these fields.

Bangladesh invoice edit changes also accept optional remarks (string/null, up to 2000 characters, preserving line breaks). Saving uses the existing versioned publication workflow. Remarks are not added to India/Jordan edit changes.

### PDF upload

GET /upload provides the country/file form. POST /api/uploads accepts multipart/form-data with exactly one region (BD, INDIA or JORDAN) and one file. Send the same local Origin and X-CSRF-Token header used by admin commands; obtain the token through GET /api/controls. This endpoint is the multipart exception: existing command requests still require JSON and retain their 64 KiB body limit.

The maximum PDF size is 100 MiB. Filename/path, complete PDF structure and password checks run before atomic publication to the currently configured country inbox. Existing filenames return 409 and are never replaced. Disabled country intake returns 409. Invalid PDF/fields/name return 400; size 413; content type 415; local/CSRF rejection 403; storage failures 503. Success returns 201 with filename, region, status=waiting_for_intake and a country/filename-filtered jobs_url. The normal folder scanner then queues the upload; no extraction or model runs in the HTTP request. A paused queue stays paused. Check the jobs list after an uncertain network result before retrying.
