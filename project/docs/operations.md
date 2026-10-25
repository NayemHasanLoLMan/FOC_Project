# Operations and troubleshooting

## Daily start

For installation and the normal single-command start, see the [root README](../../README.md). The running system is managed as follows:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py
~~~

Open http://127.0.0.1:8080/. One Python process runs the folder scanner, extraction worker and dashboard on separate threads, using one configuration. It initializes/migrates the queue and creates a missing inbox. Drop completed Bangladesh PDFs into project/incoming/bangladesh; invoices appear in project/output/bangladesh. With India intake enabled in System, India uses its separate configured input/output pair (this installation: incoming/india → output/india). Jordan stays disabled. Additional unseen India PDFs still need acceptance testing. Existing data is preserved. The browser may be closed without stopping processing.

For custom paths/port:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py --config C:/shipments/pipeline_config.json --port 8081
~~~

Keep the installed Ollama service available when local vision is enabled. Models and Python dependencies must be installed before first use; the launcher does not install or download them. Do not run another scanner/worker against the same state, or another web server on the same port. Conflicts fail startup rather than taking over existing owners.

The separate init_pipeline.py, scan_incoming.py, run_worker.py and run_dashboard.py commands remain available for maintenance or independently managed deployments; they are no longer necessary for normal startup. run_dashboard.py starts only the web interface.

Stage 7 adds a current-user Windows Task Scheduler task. It starts after sign-in and runs hidden through the same launcher. Use the commands below. The PC must remain awake.

## Dashboard and invoice workflow

Overview separates the web page, folder scanner, invoice worker and local image reader. “Web available” does not mean the worker is running. A stale heartbeat is shown as unknown. Queued means waiting for the worker; waiting to save means an invoice was prepared but publication is blocked.

Jobs lists each source/content version once. A retry belongs to the same job as another processing run. Search by filename or recorded invoice number; filter by document date or status. Use the prominent View, Edit and Download actions.

The detail page explains **What happened**, shows invoice information and lists fields left blank. It uses “Invoice ready,” “Waiting to start” and other plain status labels. Developer details are available through the API rather than on the job page.

Image readings show the exact area read by the local image model and the highlighted original page. The page explains the value found and whether it was used. A reused saved reading still comes from the image model. An accepted reading can fail to contribute when a complete final field could not be established.

The source download is the accepted PDF snapshot, which may differ from a subsequently edited incoming file. The invoice download is the recorded output version, checked against its saved hash.

India invoice details show IEC/PAN/GST address information, destination, carton references, discharge port/terms and goods HS codes. Blank values use a dash; unsupported values are not inferred. India net weight is omitted. Earlier processing runs show their own saved information; original image readings remain available after manual edits. Use Preview Excel to inspect the invoice's printed layout.

### Missing fields and preserved versions

Unsupported/unreadable/conflicting information stays blank; no approval or validation prompt is added to the printed invoice. A completed invoice can therefore have missing information. Notes on the dashboard do not require intervention or automatically stop generation.

The PDF is the shipment source. Manual expected workbooks are development references and are never needed in production. Supported company-directory fallbacks and approved approximate valuation rates may supply maintained information/estimates. See [configuration](configuration.md) before changing those rules.

The queue preserves occupied output files and chooses a versioned filename when necessary. Identical unchanged arrivals do not create another job; changed bytes create a new source version. Renaming a PDF can create a distinct job because filenames may support invoice-number extraction.

Do not rename, edit or delete internal job snapshots/evidence to repair a result. Use the original PDF and the existing retry controls. Use Pause processing / Resume processing on Overview. Pause lets the current invoice finish while new PDFs continue to queue. On the latest eligible job detail, use Retry this PDF, Retry saving invoice, or Create another invoice. Earlier outputs stay available. A stopped worker must be started with run_system.py before queued requests can run.

Direct main.py/run_batch.py conversion remains available, but it is outside the durable queue. Its outputs do not automatically become dashboard jobs, and it does not provide queue-style historical collision protection. Prefer the folder pipeline for managed operations.

## Edit and add information

Choose Edit on Jobs or Edit / add information on a completed job. Add missing header information or change goods, quantities, units and unit values. Save new invoice version creates a separate workbook through the existing worker; original outputs and source images remain available. No OCR/model inference repeats for a manual save. A paused queue must resume before that save runs.

Only the latest completed Bangladesh or India invoice can be edited; stale/concurrent saves are rejected. Bangladesh exposes its applicable TIN/cover-note fields; India exposes HS, discharge port and terms. Country/template/currency stay protected. Net weight is not offered. New goods need a unit value; missing quantity or value leaves the calculated amount and automatic total blank. Bangladesh totals round half up to whole dollars, India to cents. An explicit total can override the automatic calculation. Description/HS-only India edits preserve source money. Manual changes do not train the extractor; Create another invoice reads the PDF afresh without those overrides.

## Download and preview

Downloads use clean names such as 26S8185-I.xlsx; stored versions retain internal job/attempt suffixes for safety. Preview Excel shows the verified first invoice sheet locally, including merged cells, sizes, colors and borders. It is read-only and does not recalculate formulas or reproduce every Excel drawing/format/pagination feature. Use native Excel for final print verification. No upload, workbook macros or external links are executed by the preview.

## Clear data for testing

System → Clear data is available on the main coordinated launcher at 8080 and requires confirmation. It refuses active work; pause first if more jobs are queued. It archives job history, generated invoices from the current Bangladesh/India output folders and retained evidence, preserving input PDFs, templates, settings and model/OCR caches. A successful clear resumes scanning: remaining PDFs pass normal stable-file checks and generate invoices again. Sequence numbers are not reset; repeated delivery of the same request is idempotent.

Recovery copies live under runtime/cleared/<time>-<request-id>/. Other-volume output archives are recorded beside their output under .foc-cleared with matching external-output metadata. Older configured output roots are not cleared. A move failure rolls back; recovery after an OS crash must restore matching database/artifacts/outputs together. Archives are not automatically purged. A standalone dashboard cannot clear data. This intentionally exposed development feature needs an access-policy review before wider deployment.

For an isolated test workspace, run `project/.venv/Scripts/python.exe project/run_system.py --development --port 8081`. Its data stays under development/runtime; do not run tests against the main queue. Development mode cannot combine with custom config or startup installation.

## Stop and restart

Press Ctrl+C once in the run_system.py terminal. It stops intake and requests worker shutdown, waits for the current invoice to finish, then closes the web server and releases ownership locks. Long model calls may delay shutdown through the existing two-hour timeout; keep the terminal open. A component failure stops the combined system with a nonzero exit; an ordinary failed PDF remains recorded without stopping the whole queue.

For independently launched maintenance components, stop scanner first, let the worker finish, and stop dashboard last. Do not terminate the user's Excel or Ollama to stop this application.

If the worker must be terminated externally, restart through run_system.py (or the maintenance run_worker.py command) with the same state/configuration. The native lock proves the prior managed owner exited. Prepared workbooks are reused; unprepared attempts are interrupted and can replay from source/cache. Three interrupted attempts mark the job failed. Do not delete lock files or manually change ownership rows to bypass a live process.

Changed application files require a worker restart before it claims another PDF. Stop/edit/validate/restart rather than modifying production code mid-conversion.

## Monitor

Check scanner, worker and Ollama separately. Queued files need a worker. A recent heartbeat means liveness, not progress. The last recorded stage/page can remain unchanged during a long model call. A stale running heartbeat is unknown. Inspect attempt history/technical records only when plain summaries are insufficient.

waiting_to_save retains a completed prepared workbook. Fix output-folder availability/permissions/free space and let the running worker retry. Saving retries do not rerun OCR. Existing occupied filenames are preserved and versioned rather than overwritten.

Ordinary failed jobs do not retry forever. Use Retry this PDF on the latest failed job detail. Retry saving invoice requests the next normal publication check without OCR. Create another invoice explicitly reprocesses a completed saved PDF while preserving its earlier output. Pause/resume is on Overview; it does not stop an active conversion, intake or prepared saves. Refresh details after a job changes. Do not edit SQLite manually.

## Backup and restore

Stop scanner/worker/dashboard for a simple consistent filesystem backup. Preserve:

- state_dir, including jobs.sqlite3 and any active SQLite sidecar files.
- artifact_dir, containing snapshots, receipts and evidence.
- All configured regional output folders and production input PDFs according to retention policy.
- Configuration, rates, templates and the exact source/dependency versions used.

Copy to a new protected backup location and verify file hashes/counts. A database backup alone does not preserve referenced files; a spreadsheet-only backup does not preserve recovery/evidence. An online SQLite backup requires its backup API plus a coordinated artifact/output snapshot; copying a changing live database alone is not a supported backup procedure.

Restore matching data together to their recorded paths while processes are stopped. Validate schema/configuration and source/artifact hashes before resuming. Absolute paths in historical attempts cannot be safely relocated by changing only current configuration. Plan a migration before moving machines/folders.

## Troubleshooting

| Symptom | Check / action |
|---|---|
| Dashboard cannot start | Install web dependencies; initialize supported database; select correct config; choose an unused port |
| Dashboard empty | Verify its config matches the scanner/worker; old batch files are not queue jobs |
| PDF stays settling | Allow a second stable observation, finish the copy, check read permissions and filesystem changes |
| Rejected PDF | Open original error; supply a complete readable non-password PDF that requires no structural repair |
| Queued but idle | Start worker with the same state directory; inspect native ownership/error and component status |
| Another process owns lock | Find the existing scanner/worker; do not steal it or delete the held lock |
| Long model wait | Check current stage and heartbeat; existing request timeout is two hours; do not infer a hang from no token output |
| Model unavailable/missing | Check local Ollama tags and configured installed vision model; application never downloads it |
| Missing field | Check PDF/source-reading explanation; unsupported facts remain blank under approved rules |
| Waiting to save | Check output volume, write permissions, free space and external file interference |
| Review image/download fails | Retained file may be missing/edited or fail hash/path checks; restore matching backup, not a substitute image |
| Worker exits after code change | Restart with completed code/configuration; unfinished work follows normal recovery |
| Reference score differs | Distinguish source-correct PDF differences, grouping/unit policy and actual extraction loss; never copy expected values into production |

Foreground logs/status remain in the terminal. Background logs are described under Windows background operation below. Keep support records outside printed invoices.

## Privacy and cleanup

The dashboard is loopback-only and unauthenticated; do not expose it to a LAN/reverse proxy. PDFs, parsed JSON, OCR text and model crops contain shipment information. Protect local folders and backups. No cloud document processing is used.

No automatic evidence retention/deletion is enabled. Keep managed artifacts and state together until an explicit archive workflow exists. Do not remove evidence with OCR cache cleanup. Dependency/model caches can be reprovisioned, but clearing them can cause long recomputation/downloads.

## Windows background operation

Run from the repository root with the same config used at installation:

```powershell
project/.venv/Scripts/python.exe project/run_system.py --startup status
project/.venv/Scripts/python.exe project/run_system.py --startup start
project/.venv/Scripts/python.exe project/run_system.py --startup stop
```

For a new installation use `--startup install`, then `--startup start`. It creates a current-user Task Scheduler task running hidden through the same environment's pythonw.exe. A 30-second sign-in trigger and one-minute recovery trigger use IgnoreNew, so running work is not duplicated. This is not a Windows Service: it requires sign-in and an awake PC. Ollama and models remain separately provisioned.

Stop disables automatic triggers and requests graceful shutdown. Wait for the current invoice and normal process exit before backing up/upgrading; the model timeout may take two hours. Start re-enables triggers. After stopping, `--startup uninstall` removes only the matching task and preserves files. Do not run foreground and background launchers together.

Task identity derives from the absolute state directory. Install refuses to overwrite an existing task, and start does not silently change its saved port/configuration. Inspect status; deliberately reinstall after a planned migration. Logs rotate near 5 MiB with three backups under the state directory's logs/system.log. Moving an installed checkout requires coordinated task/data migration, not only changed folder settings. Actual reboot acceptance remains pending.

## Maintenance command reference

~~~powershell
project/.venv/Scripts/python.exe project/main.py --pdf C:/shipments/incoming/new.pdf --save-json
project/.venv/Scripts/python.exe project/run_batch.py --input-dir C:/shipments/incoming --output-dir C:/shipments/invoices
project/.venv/Scripts/python.exe project/init_pipeline.py --config C:/shipments/pipeline_config.json
project/.venv/Scripts/python.exe project/scan_incoming.py --config C:/shipments/pipeline_config.json
project/.venv/Scripts/python.exe project/run_worker.py --config C:/shipments/pipeline_config.json
project/.venv/Scripts/python.exe project/run_dashboard.py --config C:/shipments/pipeline_config.json --port 8081
~~~

Defaults for the five managed commands select project/pipeline_config.json regardless of current directory. A custom file must provide all six required keys; vision limits have compatible defaults. The dashboard requires an initialized schema-6 database and never migrates it. The single system launcher initializes/migrates state before starting its dashboard.

| Script |Purpose / options |
|---|---|
| run_system.py | Entire system: initialize state, scan PDFs, process invoices and serve dashboard; --config, --port (default 8080) |
| main.py | One PDF; required --pdf PATH. Optional --region BD/INDIA/JORDAN (default BD), --template, --output-dir, --cache-dir, --save-json, --max-pages, --local-model, --no-local-vision |
| run_batch.py | Each top-level *.pdf in --input-dir; optional --region BD/INDIA/JORDAN (default BD), --output-dir, --cache-dir, --max-pages, --local-model, --no-local-vision |
| init_pipeline.py | Validate --config and create/migrate durable state; never starts extraction |
| scan_incoming.py | Continuously accept stable PDFs; --config, --once |
| run_worker.py | Continuously consume queue; --config, mutually exclusive --once or --drain |
| run_dashboard.py | Localhost web server with protected controls; --config, --port (default 8080, range 1–65535) |

main.py/run_batch.py output defaults to project/output/bangladesh, project/output/india or project/output/jordan according to --region; omitted --region remains BD. Cache defaults to project/.cache/ocr. An explicitly conflicting destination or named regional master is rejected. The Python run API accepts region=None for legacy source-based selection, or an explicit BD/INDIA/JORDAN. Model defaults to qwen3-vl:latest. --no-local-vision overrides the model to None. max-pages must be positive; it is diagnostic, not a way to produce a complete shipment invoice. The managed worker does not expose page truncation.

Regional selection does not establish regional production readiness. India has passed available-sample acceptance with separate opt-in inbox/output settings, versioned editing and cent totals. Jordan can still reject legacy row truncation/duplicate totals or incomplete print areas until its master/writer stage. Non-BD direct conversion verifies a temporary workbook before replacing its final XLSX. CLI region flags do not enable a watched country; use validated System settings for India. Jordan watching/editing stays disabled. See [readiness](roadmap.md).

Batch defaults to project/examples for the development checkout and writes output/bangladesh/run_manifest.json. Its glob is top-level and case-sensitive according to pathlib/platform behavior; continuous intake explicitly handles PDF extensions case-insensitively and checks temporary/link/hidden names. Batch/direct commands bypass queue history and managed collision versioning.

Worker --once retries prepared saves and processes at most one new job. --drain handles the current backlog, then exits after an idle pass; it does not wait continuously for new arrivals. Both exit with code 1 if failed/interrupted/waiting-to-save job states remain. A continuous worker normally stays alive after a per-PDF converter failure. Database/ownership/heartbeat failures stop it.

Scanner --once records one readiness observation, usually waiting on the first arrival. A later observation after the interval can queue it. Continuous scans sleep for the configured interval after completing the prior scan. Rejections are recorded in JSON/status; a scan containing rejected inputs does not necessarily exit nonzero.

Ctrl+C stops scanner/dashboard. Worker Ctrl+C requests shutdown after the current conversion finishes; this can wait through the existing model timeout. Forced termination is recovered on restart under native lock ownership rules.

## Command exit behavior

Successful one-shot commands normally return 0. Argument validation uses argparse code 2. Batch reports each written/failed source and exits 1 if any source failed. A direct conversion prints its output path; an uncaught conversion/configuration error exits nonzero. Scanner/worker print JSON lifecycle/count status, while underlying OCR/model diagnostics can also appear on stdout; do not treat the whole stream as one JSON document.

Development commands are documented in [testing](development.md) and [build](development.md). They are not included in production archives.

run_system.py is the normal entry point. Ctrl+C waits for active processing before exiting. A port/ownership conflict or component failure exits nonzero; PDF-level failures remain in job history. It does not start a Windows service or install/download OCR/Ollama dependencies.

## Choose shared country folders

System shows Bangladesh, India and Jordan intake status. Bangladesh and India have enabled/disabled intake switches and explicit status badges. Jordan shows Disabled with a locked switch until its workflow is accepted. There is no folder/disk-space table on the page; diagnostics remain available through the API.

Use Choose folder for one PDF intake parent and one invoice output parent. A folder-browser dialog opens inside the dashboard. Navigate subfolders, Home or drives, then choose Use this folder; Location also accepts a known directory. Each parent has bangladesh, india and jordan subfolders; missing folders are created on Save settings. Selection alone changes nothing. Save while idle. Existing queued PDFs and historical downloads retain their original paths. Nonstandard separate country paths are preserved until explicitly replaced. Output and intake parents should be dedicated and separate from each other and application/state folders.

Each country shows an Enabled/Disabled badge and selector. Change Bangladesh or India and choose Save settings while idle. Badges label unsaved choices. Jordan is visibly Disabled and locked until its workflow is ready; accepted jobs continue even when new intake is disabled.
