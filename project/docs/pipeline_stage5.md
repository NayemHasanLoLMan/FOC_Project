# Stage 5 — read-only local admin dashboard

Implemented and verified on 20 October 2026. Stop before Stage 6 for approval. The dashboard displays state and evidence; pause/retry/settings controls and automatic startup remain pending.

## Start and use

From the repository root, after installing project/requirements.txt and initializing state with init_pipeline.py:

~~~powershell
project/.venv/Scripts/python.exe project/run_dashboard.py
~~~

Open **http://127.0.0.1:8080**. Use --config followed by a configuration path to select a queue, or --port 8081 for another port. Ctrl+C stops a dashboard you launch in your terminal. The host is fixed to loopback; no LAN option is added.

Scanner and worker still run independently:

~~~powershell
project/.venv/Scripts/python.exe project/scan_incoming.py
project/.venv/Scripts/python.exe project/run_worker.py
~~~

All three processes must use the same configuration to display/process the same queue. Opening the dashboard never starts processing. Closing a browser does not stop terminal processes.

For acceptance, the running dashboard uses reports/pipeline_stage5_20261020/worker_demo/pipeline_config.json and shows the 20 completed test jobs. The production configuration is unchanged and its queue remains empty. Old standalone/batch workbooks are not automatically imported as jobs. Only the selected queue is displayed.

## Delivered views

- **Overview:** queue counts and settling intake files; independent scanner/worker/Ollama health, heartbeats/errors; last recorded stage/page and elapsed time; today's received/completed jobs; all-time attempts; completed jobs with recorded issues; recent jobs and intake errors.
- **Jobs:** filename/invoice-number search, document-date/status/issue filters and 25-job pagination. One row represents one source-version job and its latest attempt. Today's counts use the PC's local date; the document-date filter uses the extracted invoice date. Historical attempts without field events show unrecorded searchable fields.
- **Job detail:** attempt history, immutable PDF and published Excel downloads, verified extracted headers/goods, optional-field issues, diagnostics, stage timeline and paginated events. Each attempt shows its application/template/rates versions and recorded model/cache use.
- **Vision evidence:** original OCR, exact retained model image, highlighted source page, answer/cache metrics, acceptance/rejection reason, prompt/settings and coordinates. Panels load images on demand. Missing/corrupt images show review errors without changing an invoice.
- **System:** configured folders, nearest-volume free space, template/model/timeout/token defaults, dependency/Python/platform versions and current fingerprints. Free space does not prove write permissions. Recorded request settings remain authoritative.

No speculative completion ETA is shown. Stage elapsed time and attempt age are available. A running worker heartbeat older than 30 seconds becomes **unknown**; scanner freshness accounts for its polling interval. Explicit stopped/failed states retain their last heartbeat. Web availability, worker liveness and model availability are separate, and a recent heartbeat does not prove stage progress.

Processing methods distinguish unrecorded history, OCR/source rules, model attempts without final contribution and model-assisted output. Cached answers remain model-derived information. Fresh-call count alone never labels a job OCR-only.

## Read-only and file boundaries

The dashboard opens JobStore with read_only=True, using SQLite mode=ro. It checks database identity/schema and refuses write transactions. It never creates or migrates state; use the existing initialization CLI first. No worker hook, schema change or extraction rule was needed.

Flask and Waitress are the two added direct dependencies. Waitress serves eight threads on 127.0.0.1, with debug/reloader off. Small status endpoints refresh every five seconds. Ollama availability is checked separately via /api/tags with a two-second timeout and ten-second cache. No inference or model download is requested. On-demand source previews use the existing renderer, limited to two concurrent renders. OCR and invoice conversion never run in web requests.

Files are served by job/attempt/event IDs, not arbitrary path parameters. PDFs, extracted JSON and invoices must pass retained hash and managed-path checks. PDFs/Excel are attachments. Model images use Stage 4 verification. HTML autoescaping, a restrictive content policy, local Host/client checks, cross-site rejection, no CORS permission and GET/HEAD-only routes protect the read-only surface. Browser errors contain no stack traces.

This is an unauthenticated local tool: do not port-forward it or expose it through a reverse proxy. LAN/multi-user deployment is separate scope. Evidence retention/backup policy is unchanged; no cleanup or startup task is installed.

## Acceptance

| Check | Result |
|---|---|
| Complete suite | **203 tests pass**, including 13 dashboard cases |
| Existing workflow | 20 PDFs completed during dashboard polling; 66 pages and 89 goods rows |
| Invoice regression | All 20 invoice values/types/styles, alignment, merges, dimensions, headers/footers and print settings unchanged |
| Manual references | Unchanged: strict goods recall 58/75, precision 58/82 |
| Live responsiveness | 83 HTTP status requests during processing: median 0.016 s, maximum 0.406 s |
| Real HTTP checks | 94 requests passed: all 20 job pages, 20 PDFs, 20 invoices, all 6 model images and search/status/system endpoints |
| Read-only proof | Database hash unchanged across all 94 requests; direct SQL writes rejected |
| Busy/error cases | Worker wait, slow concurrent previews, throttling, stale health, unknown history, invalid filters/foreign attempts, model cache, corrupt/outside files, untrusted Host/Origin/client, mutation rejection and escaped source text covered |
| UI | Actual overview and model-assisted reading viewed in the in-app browser, including responsive narrow layout and lazy images |
| Protected assets | All 81 protected baseline files unchanged; store read-only support and web requirements intentionally changed |
| Runtime | Schema 3 retained; production queue empty; scanner/worker stopped; read-only demo dashboard available |

Evidence: [regression](../reports/pipeline_stage5_20261020/regression.json), [live timing](../reports/pipeline_stage5_20261020/live_responsiveness.json), [HTTP checks](../reports/pipeline_stage5_20261020/http_acceptance.json), [reference comparison](../reports/pipeline_stage5_20261020/after/accuracy.md), [preview](../reports/pipeline_stage5_20261020/dashboard-preview.png).

The integration run reused valid OCR/model caches. It checks result preservation and responsiveness, not fresh inference accuracy, production load capacity or unseen-PDF accuracy. Native Excel print rendering was not repeated because invoice values/styles/print settings match. Full assistive-technology and multi-browser testing were not performed.

Next approval: **Stage 6 — pause/resume and selected retry/save-retry controls**, with transactional handling and request protection. Startup management remains Stage 7.

User-facing detail simplification, 20 October: the default job view now explains what happened, how the PDF was read, and why information was left blank in plain language. Image comparison is retained, with a readable result and whether it was used. Raw notes, model responses/settings, version hashes, stage timeline and events remain in collapsed Technical details. Goods show PDF page numbers instead of internal source-reference codes. Reading acceptance remains separate from final invoice use. No extraction, invoice data, downloads, permissions or Stage 6 controls changed.

Implementation references: [Flask/Waitress deployment](https://flask.palletsprojects.com/en/stable/deploying/waitress/), [Flask web security](https://flask.palletsprojects.com/en/stable/web-security/).
