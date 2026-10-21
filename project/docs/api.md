# HTTP API reference

Base URL: **http://127.0.0.1:8080**, or the selected --port. [openapi.json](openapi.json) describes all 14 implemented routes and their request/response schemas. It can be opened in an OpenAPI 3.1-compatible viewer; no Swagger service is installed or exposed.

This is a local, unauthenticated **read-only** API. GET and HEAD are allowed; other methods are rejected. There is no PDF-upload, conversion-start, pause, retry, settings or delete endpoint. The scanner accepts PDFs from the configured filesystem inbox. All timestamps are UTC unless explicitly described as the PC's local date/time.

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
| /api/jobs | q, status, date, issues, page; returns jobs, total, page, pages |
| /api/jobs/{job_id} | attempt and event_page; selected attempt plus verified data, explanations, events and evidence |
| /api/jobs/{job_id}/status | Small poll response: job_id, state, status_label, updated_at |

### List filters and pagination

q is a literal case-insensitive SQL-LIKE substring of filename or recorded invoice number, with wildcard characters escaped; maximum 200 characters. status accepts waiting_for_file, queued, running, waiting_to_save, completed, failed or interrupted. date is extracted document date YYYY-MM-DD, not arrival date. issues=yes/no filters the latest attempt's recorded issue list. Omit/leave blank filters to include all.

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
| /files/attempts/{attempt_id}/invoice | .xlsx attachment for a completed attempt; validates its recorded version |
| /images/jobs/{job_id}/events/{event_id} | image/png, exact retained input of a vision_request from that job |
| /images/jobs/{job_id}/pages/{page} | image/png source preview; optional event query highlights a region from the same job/attempt |

Preview pages are one-based and must be within retained OCR coverage. Rendering uses the recorded DPI/rotation/skew before highlighting/resizing. At most two previews render concurrently; additional requests return 429 and can be retried later. Missing/corrupt files do not silently return another file or regenerate OCR.

## HTML routes

/ shows overview; /jobs accepts the list filters and partial=1 for the escaped table fragment; /jobs/{job_id} accepts attempt/event_page; /system shows configuration/dependencies. /dashboard_static/... serves bundled UI assets through Flask's static endpoint; it is not an artifact API.

## Errors

| Status | Meaning |
|---|---|
| 400 | Invalid filter/number/date or untrusted Host |
| 403 | Nonlocal/cross-site/mismatched Origin request |
| 404 | Unknown job/attempt/event, missing retained file or missing preview document |
| 405 | Unsupported method; this stage is read-only |
| 409 | State prevents invoice download, or retained path/hash/data verification fails |
| 429 | Source-preview capacity busy |
| 503 | Temporary database/filesystem/server-data failure; check local console |

A completed job remains completed if later review fails because an artifact was edited/deleted; the review/download request reports the problem. No endpoint repairs source data or overwrites an invoice.

## Examples

~~~powershell
Invoke-RestMethod http://127.0.0.1:8080/api/status
Invoke-RestMethod 'http://127.0.0.1:8080/api/jobs?q=5188&status=completed&page=1'
Invoke-RestMethod http://127.0.0.1:8080/api/jobs/12
Invoke-WebRequest http://127.0.0.1:8080/files/attempts/12/invoice -OutFile C:/shipments/download.xlsx
~~~

IDs 12/5188 above illustrate the development demo; discover real IDs from /api/jobs and /api/jobs/{job_id}. GET examples do not create processing work. [CLI](cli.md) and [Python](code-reference.md) interfaces are documented separately.

## Postman

Import the [collection](../development/postman/FOC-Invoice.postman_collection.json) and [local environment](../development/postman/Local.postman_environment.json). See [usage and ID selection](../development/postman/README.md). These development files are not shipped in the production ZIP; OpenAPI remains included.
