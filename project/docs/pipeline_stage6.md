# Stage 6 - local admin controls and recovery

Implemented and verified on 21 October 2026. This is the historical Stage 6 acceptance record; [Stage 7 startup](pipeline_stage7.md) is now approved and implemented. Normal startup remains one command:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py
~~~

Open http://127.0.0.1:8080/. Overview has Pause processing and Resume processing. Pausing is saved in the database and prevents new conversion claims. Current conversion can finish, new PDFs still queue, and prepared invoice saves continue. Worker health remains a separate running/stopped/unknown signal. Resume does not launch a stopped process.

The latest eligible job detail offers:

- Retry this PDF for failed/interrupted jobs: queue a new attempt from the retained PDF.
- Retry saving invoice for waiting-to-save jobs: record an explicit request for the running worker's next regular publication check, reusing the prepared workbook without OCR/VL. Automatic publication retry already uses this same path.
- Create another invoice for a completed job: confirm a deliberate new attempt using the saved PDF and current configuration/template/rates/application metadata. Preserve earlier downloads and use a versioned output filename.

No web request performs conversion or publication. No job deletion, forced cancellation, bulk reprocess, shell access, model/path editing or Windows startup installation was added. Settings stay read-only. Review text stays on the dashboard, never on invoices.

## Transaction and request protection

Read views still use SQLite mode=ro. Only validated POST commands open short writable transactions. The pause check and worker claim share one transaction. Commands store a canonical UUID, action, target IDs, timestamp and result. Retrying the same UUID/payload returns the original result without requeueing later work. Reusing the ID for another action/payload conflicts. Job actions require the latest eligible attempt ID, preventing stale pages from affecting newer attempts.

Commands require loopback client/Host, matching Origin, application/json and the process-scoped X-CSRF-Token. The browser gets the token from page metadata; API clients use GET /api/controls. Reload after web restart. Existing same-origin/no-CORS/CSP/file-integrity checks remain. This is a local unauthenticated tool; LAN exposure and shared-user authentication remain separate scope.

See [API](api.md), [OpenAPI](openapi.json), [Postman](../development/postman/README.md) and [operations](operations.md).

## Schema and rollback

Schema 4 adds queue_control and admin_commands. Writable initialization supports versions 1, 2 and 3. Existing jobs, attempts, receipts, paths and artifacts are retained; migration starts resumed. Read-only web startup validates the schema and does not migrate it. run_system.py initializes/migrates before starting components.

The existing production and demo databases were backed up before migration. Production remains empty; the historical demo still has 20 completed jobs. Backups are in project/reports/pipeline_stage6_20261021/ as production_schema3_before.sqlite3 and demo_schema3_before.sqlite3. Do not run older code against schema 4. Stop components and restore a consistent matching application/state/artifact/output backup for rollback. Retain admin command records with state backups for replay protection.

The demo is currently running through run_system.py with the prior Stage 5 demo configuration on port 8080. It is distinct from the default production inbox/state. Isolated acceptance systems were shut down. No Task Scheduler or Windows service was installed.

## Acceptance

| Check | Result |
|---|---|
| Full suite | 227 passed, including 10 new admin tests |
| Pause boundary | 20 real PDFs queued, zero attempts while paused |
| Resume | All 20 PDFs / 66 pages / 89 goods completed |
| Invoice regression | All 20 printed values/types/styles and merged cells match existing outputs; original templates/outputs unchanged |
| Request replay | Eight concurrent identical POSTs return one saved result; stale attempt and mismatched request IDs rejected |
| Reprocess | 21 total attempts across 20 jobs; original invoice retained unchanged and new output version published |
| Save-only recovery | Prepared workbook saved while paused; converter called only once, no duplicate attempt |
| Failure safety | Invalid CSRF/Origin/JSON, foreign/stale IDs, component conflicts and transactional audit-write rollback tested |
| Migration | Schema 3 jobs/attempts preserved; writable legacy migrations pass |
| Browser | Pause/resume verified on live UI; left resumed with healthy scanner/worker |
| API assets | All 20 routes represented in OpenAPI and Postman; route/query coverage tested |

Live polling: 276 requests, median 0.094 seconds, maximum 0.563 seconds during the successful full-data run. These are local test observations, not a throughput guarantee. The run reused source/model caches; limited narrow OCR still initialized the installed models. It is not a fresh full-document or unseen-document benchmark.

Detailed evidence is in project/reports/pipeline_stage6_20261021/: verification.json, live_acceptance.json, migration_before.json and dashboard-controls.png. The first run completed 20 jobs but its comparison encountered an Excel owner-lock file; the successful fresh isolated rerun excluded those files, as the established evaluator does.

Native Excel print rendering, clean-machine installation, full accessibility/multi-browser coverage and reboot/unattended operation were not retested. Stage 7 installation is not enabled. Existing BD manual-reference differences remain unchanged.
