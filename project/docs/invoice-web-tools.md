# Invoice downloads, web preview and development reset

## Download filename

Browser downloads use the original generated workbook name, for example `26S8185-I.xlsx`. Internal job/attempt suffixes stay on stored versions so previous invoices remain protected. The download is the same hash-verified workbook; it is not rewritten or reprocessed.

## Preview Excel

Open a completed job and choose **Preview Excel** beside Download invoice. The local read-only page reads the first invoice worksheet from the verified saved workbook, including its print area, merged cells, text, row/column sizes, colors, red rich-text fragments and borders. It does not upload data or require an online office viewer.

This is an invoice-sheet preview, not a full Excel editor. Formulas are not recalculated; stored cached results appear when available. Native Excel pagination, drawings, every theme/number format and other worksheets are not reproduced. Download the workbook for Excel editing or final print verification. Existing Edit / add information remains the supported web editing flow and creates another version.

## Clear data on the main dashboard

Open http://127.0.0.1:8080/system and choose **Clear data**. It is available in the normal single-command launcher and the background startup service. Confirming clears the current job/attempt/event history and archives all generated invoices and review evidence from the configured Bangladesh output and artifact folders. It does not permanently delete those files.

Input PDFs, templates, settings, company data and model/OCR caches are preserved. A consistent database backup and the generated folders are kept together under `project/runtime/cleared/<UTC-time>-<request-id>/`. Wait for active work to finish; the command refuses while a scan or invoice is active. Pause processing on Overview first if more PDFs are queued; a successful clear then resumes processing automatically.

Clearing also resets intake observations and resumes queue processing. PDFs still in the inbox are automatically rediscovered, pass the normal stable-file checks across two scans, and create new jobs/invoices once. No manual copying is needed. Command replay IDs remain and job/attempt sequence numbers are not reset. Replaying a reset UUID returns its previous result without clearing later work or changing its pause state. The scanner also recovers orphaned queued observations left by the earlier clear implementation.

If a file move fails, moved folders and the database transaction roll back. After an operating-system crash mid-reset, stop the system and restore the matching database, output and artifacts from the recovery archive as one set. Archives require manual recovery and are not automatically purged. If the selected output folder is on another volume, `external-output.json` records its matching archive under `.foc-cleared` beside that output folder; restore that folder along with the database/artifacts.

Clearing requires the fixed main state/artifact roots or the isolated development workspace. Incoming/output folders may be changed through validated System settings; the current output folder is archived, while older output folders remain in place. Redirected paths and unsafe folder overlaps are rejected. A standalone dashboard without the coordinated scanner/worker launcher cannot clear data. The existing Origin/CSRF/UUID protections and browser confirmation remain in place. This feature is intentionally available on the main dashboard for the current development workflow; isolate or disable it before wider deployment if needed.

## Optional isolated test workspace

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py --development --port 8081
~~~

This optional launcher uses the same **Clear data** button with a Development workspace banner. Its inputs, outputs, database and artifacts live under `project/development/runtime/`, and its archives under that folder's `cleared/`. It does not affect the main workspace. Development mode cannot be combined with startup/background installation or custom config selection.

## API

- GET `/files/attempts/{attempt_id}/invoice`: unchanged workbook, canonical attachment filename.
- GET `/invoices/attempts/{attempt_id}`: local HTML sheet preview, no OCR or writes.
- POST `/api/development/reset`: JSON `{ "request_id": "a-new-UUID" }`; main or isolated coordinated launcher. Returns action, cleared job count and recovery-folder name. A dashboard without reset enabled responds 403; active work or unsupported paths respond 409. The existing endpoint name is retained for compatibility.

Preview cells are autoescaped and generated style rules are restricted to workbook formatting values under a per-response CSP nonce. Browser scripts, macros, formulas and external workbook links are not executed. See [OpenAPI](openapi.json) and the development Postman collection.
