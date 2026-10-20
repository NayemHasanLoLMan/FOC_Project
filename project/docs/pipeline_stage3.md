# Stage 3 — queue worker and recoverable invoice publication

Historical acceptance checkpoint. [Stage 4](pipeline_stage4.md) now adds processing evidence, model attribution and retained review images; operating commands remain the same. Statements below about pending evidence describe the Stage 3 checkpoint.

Implemented and verified on 20 October 2026. Stopped before Stage 4 for user approval. The scanner and worker can now run continuously in separate terminals; no dashboard or startup task is installed, and neither process is left running.

## Operation

From the repository root, run these in two terminals:

```powershell
project/.venv/Scripts/python.exe project/scan_incoming.py
project/.venv/Scripts/python.exe project/run_worker.py
```

Both use `project/pipeline_config.json`; `--config <path>` selects another configuration. The default inbox is `project/incoming`, output is `project/output`, and state/artifacts are under `project/runtime`. The first scanner observation normally waits for a matching observation at least five seconds later. Scanning continues independently while OCR/VL runs. Keep the PC awake and Ollama available for local vision fallback.

Worker `--once` retries pending publications and processes at most one new PDF; `--drain` processes the available backlog and exits after an idle pass. They return code 1 when failed/interrupted/waiting-to-save jobs remain. The default worker polls continuously. Ctrl+C requests shutdown after the active conversion finishes, which can include the existing two-hour model timeout. Forced termination is recovered on the next worker start.

## Delivered behavior

- One native OS lock per scanner/worker state directory prevents duplicate CLI instances. Recovery requires acquiring the worker lock, proving the previous managed worker has exited; a stale timestamp never authorizes takeover. Unknown/manual owners are rejected rather than stolen.
- The worker claims one job transactionally and calls the existing shared converter against its verified original-name snapshot. It uses the current BD master template, rates, OCR cache and configured model. Full page coverage, workbook/audit goods parity, source hashes and source/template/rate/application stability are checked before publication. Missing unsupported fields remain permitted.
- Each attempt retains its generated workbook, extracted-data JSON and hash-verified `ready.json` receipt under `artifact_dir/jobs/<job>/attempt-<attempt>`. Production never reads manual expected workbooks or evaluation tools.
- Publication copies to a temporary file on the output volume, verifies its hash and publishes without replacing an occupied filename. The first available original filename is used; collisions receive `__job-N-attempt-M` and, if necessary, a numeric suffix. Existing legacy/batch invoices are preserved. Output publication has no per-invoice formatting step.
- Unavailable output folders and write/lock errors retain `waiting_to_save`. The worker retries these saves on later idle polls without another conversion or attempt; it can continue other queued PDFs. Repeated identical save errors do not flood the event table. Prepared-artifact corruption fails explicitly instead of publishing it.
- Restart reuses a verified prepared workbook, including a crash between writing its receipt and recording readiness in SQLite. A matching already-published workbook reconciles a crash before the completion commit. A crash before readiness interrupts the attempt and queues another using the existing caches; three such interruptions mark the job failed. Ordinary converter failures do not retry indefinitely or block the next PDF. Repeated save failures can wait indefinitely until the output becomes writable.
- Scanner and worker component records persist PID, owner, state, error and heartbeat. The worker refreshes its heartbeat independently every five seconds during conversion. A failed heartbeat stops further processing at the next safe boundary; unfinished attempts remain recoverable. A stopped/crashed process's last record is telemetry, not proof it is alive.
- SQLite migration 2 to 3 adds prepared-receipt references and component health records without deleting jobs/history. Existing v1 migration remains supported. The pre-stage default database backup is retained in the acceptance report folder.

No dependency, extraction rule, valuation rate, vision timeout/token allowance or master-template style changed. Raw converter diagnostics remain in extracted JSON/audit sheets. Per-field OCR/VL attribution, exact model-input images and actual model digest belong to Stage 4; issue classification is not implemented yet. The configured model name and version fingerprints are recorded, but a missing digest must not be interpreted as OCR-only processing.

## Acceptance

| Check | Result |
|---|---|
| Complete unit suite | 177 passed, including 18 worker/publication/recovery tests |
| Actual folder intake and worker conversion | 20 completed PDFs, 66 pages, 89 goods rows; no failures or pending saves |
| Invoice regression | All 20 invoice sheets retain cell values/types/styles, merges, row/column dimensions, alignment, headers/footers and print settings |
| Manual-reference comparison | Unchanged after accounting for the intentional output-directory difference; strict item recall 58/75, precision 58/82 |
| Original protected assets | All 82 protected core/config/template/source/reference/output files unchanged |
| Completed-queue restart | Still exactly 20 attempts and 20 outputs; no new job claimed |
| Failure/recovery checks | Blocked saves, unavailable output, file collisions/races, corrupt staged/copy bytes, native duplicate-worker rejection, actual abrupt child-process exit and both receipt/publication crash checkpoints pass |
| Ownership/liveness | Unmanaged-owner refusal, bounded interruption recovery and heartbeat during busy conversion pass |
| Default production state | Schema 3; zero jobs/attempts; scanner and worker stopped; integrity/foreign-key checks pass |

The real run reused the existing OCR/model caches where valid; it verifies worker integration and result preservation, not fresh OCR accuracy or production generalization. Original output workbooks were never regenerated. Evidence: [regression summary](../reports/pipeline_stage3_20261020/regression.json), [read-only verification script](../reports/pipeline_stage3_20261020/verify_stage3.py), [reference comparison](../reports/pipeline_stage3_20261020/after/accuracy.md). Isolated generated invoices are in `reports/pipeline_stage3_20261020/worker_demo/output`.

## Limits and next approval

Native Windows locking and abrupt process recovery were tested. Excel/write-denial behavior is covered by injected permission errors and real unavailable-path tests; no user's workbook was locked or closed for testing. Physical power loss, forced disk exhaustion, POSIX publication and unseen production PDFs were not tested. Native Excel print rendering was not repeated because all invoice print/style settings match the existing verified output. There is no fsync-based power-loss durability guarantee; retain routine backups of runtime state/artifacts and outputs. A crash before readiness can repeat computation.

The scanner and worker must be started manually until Stage 7. Automatic retries for failed jobs and admin controls remain Stage 6. Stage 4 will add structured processing evidence and retained exact vision-input images; Stage 5 will expose these through the read-only dashboard. Neither stage starts without user approval.
