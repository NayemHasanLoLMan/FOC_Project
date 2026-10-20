# Operations and troubleshooting

## Daily start

Use one approved configuration for all components. Keep Ollama available under the same account when vision is enabled. Initialize/migrate state before the dashboard:

~~~powershell
project/.venv/Scripts/python.exe project/init_pipeline.py
project/.venv/Scripts/python.exe project/scan_incoming.py
project/.venv/Scripts/python.exe project/run_worker.py
project/.venv/Scripts/python.exe project/run_dashboard.py
~~~

The three long-running commands belong in separate terminals. For a custom configuration, supply the same --config path to all four commands. Opening/closing the web page never starts/stops the scanner or worker.

No Windows Service or Task Scheduler installation is provided yet. Processes do not automatically start after reboot. The PC must remain awake.

## Stop and restart

Stop scanner first to stop new intake. Ctrl+C on the worker requests shutdown after its current conversion finishes; keep the terminal alive while it completes. Stop dashboard last. Do not terminate the user's Excel or Ollama to stop this application.

If the worker must be terminated externally, restart through run_worker.py with the same state/configuration. The native lock proves the prior managed owner exited. Prepared workbooks are reused; unprepared attempts are interrupted and can replay from source/cache. Three interrupted attempts mark the job failed. Do not delete lock files or manually change ownership rows to bypass a live process.

Changed application files require a worker restart before it claims another PDF. Stop/edit/validate/restart rather than modifying production code mid-conversion.

## Monitor

Check scanner, worker and Ollama separately. Queued files need a worker. A recent heartbeat means liveness, not progress. The last recorded stage/page can remain unchanged during a long model call. A stale running heartbeat is unknown. Inspect attempt history/technical records only when plain summaries are insufficient.

waiting_to_save retains a completed prepared workbook. Fix output-folder availability/permissions/free space and let the running worker retry. Saving retries do not rerun OCR. Existing occupied filenames are preserved and versioned rather than overwritten.

Ordinary failed jobs do not retry forever. Internal JobStore retry exists for coordinators, but public admin retry controls remain Stage 6; do not invent an HTTP request or edit SQLite manually.

## Backup and restore

Stop scanner/worker/dashboard for a simple consistent filesystem backup. Preserve:

- state_dir, including jobs.sqlite3 and any active SQLite sidecar files.
- artifact_dir, containing snapshots, receipts and evidence.
- output_dir and the configured production input PDFs according to retention policy.
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

Logs/status are printed to each process terminal; OCR diagnostics can mix with JSON status. There is no centralized rotated log service yet. Keep support records outside printed invoices.

## Privacy and cleanup

The dashboard is loopback-only and unauthenticated; do not expose it to a LAN/reverse proxy. PDFs, parsed JSON, OCR text and model crops contain shipment information. Protect local folders and backups. No cloud document processing is used.

No automatic evidence retention/deletion is enabled. Keep managed artifacts and state together until an explicit archive workflow exists. Do not remove evidence with OCR cache cleanup. Dependency/model caches can be reprovisioned, but clearing them can cause long recomputation/downloads.
