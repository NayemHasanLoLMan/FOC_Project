# Operations and troubleshooting

## Daily start

Start the entire invoice system from the repository/release root:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py
~~~

Open http://127.0.0.1:8080/. One Python process runs the folder scanner, extraction worker and dashboard on separate threads, using one configuration. It initializes/migrates the queue and creates a missing inbox. Drop completed PDFs into project/incoming/bangladesh; invoices appear in project/output/bangladesh. Existing data is preserved. The browser may be closed without stopping processing.

For custom paths/port:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py --config C:/shipments/pipeline_config.json --port 8081
~~~

Keep the installed Ollama service available when local vision is enabled. Models and Python dependencies must be installed before first use; the launcher does not install or download them. Do not run another scanner/worker against the same state, or another web server on the same port. Conflicts fail startup rather than taking over existing owners.

The separate init_pipeline.py, scan_incoming.py, run_worker.py and run_dashboard.py commands remain available for maintenance or independently managed deployments; they are no longer necessary for normal startup. run_dashboard.py starts only the web interface.

Stage 7 adds a current-user Windows Task Scheduler task. It starts after sign-in and runs hidden through the same launcher. See [background startup and stop commands](pipeline_stage7.md). The PC must remain awake.

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

Foreground logs/status remain in the terminal. Background startup writes rotated Python logs under the configured state directory in logs/system.log; see [Stage 7](pipeline_stage7.md). Keep support records outside printed invoices.

## Privacy and cleanup

The dashboard is loopback-only and unauthenticated; do not expose it to a LAN/reverse proxy. PDFs, parsed JSON, OCR text and model crops contain shipment information. Protect local folders and backups. No cloud document processing is used.

No automatic evidence retention/deletion is enabled. Keep managed artifacts and state together until an explicit archive workflow exists. Do not remove evidence with OCR cache cleanup. Dependency/model caches can be reprovisioned, but clearing them can cause long recomputation/downloads.

See [manual invoice editing](manual-invoice-editing.md) for the simplified dashboard and safe versioned editing workflow.

See [invoice downloads, web preview and development reset](invoice-web-tools.md) for clean filenames, local viewing and the isolated Clear data option.
