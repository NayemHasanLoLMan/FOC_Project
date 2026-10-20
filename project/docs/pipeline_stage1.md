# Stage 1 — configuration and durable job state

Historical Stage 1 checkpoint. [Stage 2](pipeline_stage2.md) now adds optional folder intake and schema-2 migration; its acceptance report records the current state. The Stage 1 results below remain the original checkpoint.

Implemented and verified on 20 October 2026. Stopped before Stage 2 as requested. There is no folder watcher, extraction worker, web dashboard or startup task yet.

## What was added

- `pipeline_config.json`: incoming/output/state/artifact paths, scan interval and model choice. Relative paths resolve beside this file. Invalid/unknown settings and overlapping managed directories are rejected. Loading configuration creates nothing.
- `src/foc_extractor/pipeline_config.py`: validated configuration and attempt metadata snapshots. Template, rate and application hashes explain which local versions an attempt used. Model name is configured; actual model digest remains unknown until a later processing stage resolves it. No Ollama request is made here.
- `src/foc_extractor/job_store.py`: local SQLite jobs, attempts and transition events. Repeated same-identity/same-byte intake is idempotent; changed content or another filename is a separate job. Snapshots preserve source filenames because extraction can use them.
- Transactional claims enforce one running extraction attempt. Only the recorded owner can heartbeat/finish a running attempt. Failed/interrupted retries preserve earlier attempts, metadata, errors and events. A restarted client cannot automatically steal running work; confirmed worker-death recovery belongs to Stage 3.
- Completion can retain issue messages without putting those messages on invoices or claiming perfect accuracy. The store checks that a completed output exists; validating its actual invoice contents remains the worker's responsibility.
- `init_pipeline.py`: validates configuration and initializes an empty database. Runtime and incoming PDFs are ignored by version control. No new dependency was added.

## Command and current state

From the repository root:

```powershell
project/.venv/Scripts/python.exe project/init_pipeline.py
```

The initializer may be repeated safely. `--config <path>` selects a different configuration. It creates only the state directory/database, prints configuration and counts, and reports `processing_started: false`. It does not create the incoming/output/artifact directories, queue sample files, run OCR/VL, or install/start services.

The default database is `project/runtime/state/jobs.sqlite3`. It was initialized successfully and has zero jobs. The proposed input is `project/incoming`; the exact production folder remains to be confirmed before intake is enabled. Current single-file/batch commands still use their existing arguments/defaults; this new configuration has not been attached to them.

## Acceptance results

| Check | Result |
|---|---|
| Original regression baseline | 128 passing |
| After adding Stage 1 | 142 passing; 14 new configuration/state tests |
| Configuration behavior | Relative paths, strict keys/types, non-overlapping directories, no load side effects |
| Initialization | Subprocess tested from another working directory; empty state only, no processing |
| Persistent state | Ownership/history survives reopen and a separate Python process |
| Concurrent claims | Four separate database connections cannot claim duplicate or parallel running work |
| Failure handling | Wrong-owner/late updates rejected; attempts retained across retries; transaction/event failures roll back together |
| Database safety | Unrelated databases and unsupported schema versions rejected |
| Preserved files | 78/78 baseline files retain exact SHA-256 hashes |
| Invoice validation | 20 files, all 66 source pages accounted for, 89 goods rows; audit agrees with invoice |
| Reference comparison | Complete before/after report unchanged |
| Template appearance | Master and all output workbook bytes unchanged; existing color/alignment inheritance tests pass |
| Existing command entry points | Single-file and batch help commands pass; their code/defaults remain unchanged |

Evidence: `reports/pipeline_stage1_20261020/before_hashes.json`, `regression.json`, and before/after comparison reports. The baseline includes existing converter source files, CLI entry points, dependencies/rates, three templates, BD PDFs/manual references and generated invoices/manifest. No regeneration of the 20 outputs was necessary because existing processing code and those files were unchanged.

## Limits and next gate

This stage stores intake-validated snapshot references; it does not validate/copy arriving PDFs. It has no automatic stale-worker recovery, file-readiness loop, output publication retry, model evidence capture or web endpoints. Waiting-for-file/waiting-to-save state names are reserved for their later components. No fresh OCR/model benchmark or physical power-loss test was needed or performed for this isolated state layer.

Next: Stage 2, stable folder discovery/intake, only after user approval. Keep the existing invoice regression checks as the gate for every subsequent update.
