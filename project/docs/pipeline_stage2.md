# Stage 2 — folder scanning and safe PDF intake

Implemented and verified on 20 October 2026. Stopped before Stage 3 for user approval. The scanner can run continuously and queue PDF snapshots; it does not claim jobs, invoke OCR/VL or create invoices.

## Delivered behavior

- `scan_incoming.py` runs a foreground polling loop; `--once` checks once and exits, and `--config` chooses the configuration. Ctrl+C stops the scanner. No background startup task or service was installed, and no continuous process is left running.
- `folder_intake.py` scans the configured inbox non-recursively, with case-insensitive PDF extensions. Temporary/partial names, hidden/owner files, symbolic links, subfolders and non-files are ignored.
- Readiness requires matching file metadata **and SHA-256 content** across observations at least the configured interval apart. Hashing content also catches changed bytes when size/modified time are preserved. Reading errors remain waiting and do not prevent other files from being considered.
- The scanner copies a stable input into a versioned snapshot, preserves its original basename, verifies the copied hash, and checks source metadata/content again. Copying a file cannot create mixed-byte queued input. Existing snapshot contents are verified before reuse and a corrupted snapshot is not overwritten.
- Snapshot paths include source identity and content hash under the managed artifact directory. Identical bytes under a different original filename remain a distinct job because filename-based invoice-number fallback can affect extraction. Queued events record related same-content job IDs.
- PDF checks require a final EOF marker, PDF format, at least one page, no required password, no structural repair, and successful loading of all pages. Rejection/errors stay in intake records; no warning text is written onto an invoice. Unchanged rejected files are not repeatedly parsed. Changed bytes are reconsidered after readiness checks.
- Disappeared files are marked missing in intake records; previously accepted snapshots and jobs remain available. Missing/unavailable folders are reported and the continuous loop tries again. Database-write errors are fatal rather than silently reporting a healthy queue.
- Reopening the scanner reuses persisted readiness and deduplication. Snapshot publication before a queue-write interruption can be recovered on another scan.

## Durable state and counts

The job database migrates transactionally from schema 1 to schema 2, adding `intake_files`. Existing jobs, attempts, events, IDs and ownership constraints are preserved. A backup of the pre-migration local database is in the Stage 2 report folder. No new dependency was added; PDF validation uses the already installed PyMuPDF.

Readiness and conversion lifecycle are deliberately distinct. JSON `intake_counts` reports waiting/rejected/missing/accepted source observations; `jobs` reports queued/running/completed/failed conversion jobs. For example, 20 PDFs on their first scan means 20 waiting intake records and zero queued jobs. `accepted_job_ids` contains jobs accepted/reused on that scan, not a count of new conversion attempts. Already accepted unchanged arrivals report no IDs on later scans.

## Commands and current state

```powershell
project/.venv/Scripts/python.exe project/scan_incoming.py
project/.venv/Scripts/python.exe project/scan_incoming.py --once
```

Default inbox: `project/incoming`, created empty and successfully scanned. Default runtime database: schema 2, integrity/foreign-key checks pass, zero production jobs. The exact future production inbox can still be changed in `pipeline_config.json`; paths resolve relative to that file. Only the isolated acceptance database contains the 20 queued example jobs.

No continuous scanner is left running. The test loop verified an arrival after startup, queueing after stable observations, and Ctrl+C-style shutdown. Automatic Windows startup remains Stage 7.

## Acceptance checks

| Check | Result |
|---|---|
| Pre-change baseline | 142 tests passing |
| Final regression suite | **159 passing**, including 17 new intake tests |
| Slow/partial/invalid copies | Wait/reject until new complete, stable bytes arrive |
| Atomic final rename / uppercase extension | Discovered and queued after readiness checks |
| Same filename, changed bytes/size-preserved timestamp | New version; previous snapshot remains unchanged |
| Renamed identical bytes | Distinct filename identity, explicit related-content link |
| Restart | Readiness persists across a new Python process; unchanged files are not queued again |
| Password/repaired/empty/truncated PDFs | Rejected with stored reasons; valid neighbors continue |
| Missing folder/file, locked input, symlink/metadata error | Reported/ignored appropriately; other files and accepted jobs remain usable |
| Copy-time mutation | No job queued from inconsistent bytes; temporary file cleaned |
| Queue-write interruption | Saved snapshot reused without rewriting on restart |
| Corrupted stored snapshot | Error reported; no overwrite or new job |
| Concurrent scanners | One job per source/content identity |
| Schema migration | Version-1 jobs, attempts and events unchanged after migration; reopening is idempotent |
| Real BD intake | **20/20 PDFs queued**, 20 original-name/hash-verified snapshots, no errors, no extraction attempts |
| Real CLI restart | Zero duplicate acceptances; queue remains 20 in the isolated demo |
| Existing invoice checks | 20 files / 66 source pages / 89 goods rows; all checks pass |
| Existing reference comparison | Complete before/after JSON unchanged |
| Protected files | **81/81 exact SHA-256 matches**: converter/configuration, CLI entry points, dependencies/rates, templates, source PDFs, manual references, invoices and manifest |

The Stage 1 job store and its future-schema test were intentionally extended for intake/migration. Existing OCR/parser/model/writer code, invoice formatting and defaults were untouched. The existing template inheritance and Step 1 ownership/rollback tests still pass.

Evidence: `reports/pipeline_stage2_20261020/regression.json`, before/after comparison reports, `before_hashes.json`, `state_before.sqlite3`, and the isolated `intake_demo` database/snapshots. No fresh OCR/model benchmark or native Excel print export was needed: conversion/template/output bytes are unchanged.

## Limits and next gate

Stability checks cannot prove a producer has stopped writing, particularly if a writer pauses with a complete readable PDF. Prefer copying as `.part`/`.tmp` and renaming atomically to `.pdf` only after the producer finishes. PDFs without the final marker or requiring structural repair are not automatically accepted, even if a tolerant viewer opens them. A later valid replacement is reconsidered automatically.

Input hashing is streamed but occurs on each scan, including previously accepted files, so the scan duration grows with total inbox bytes. Each loop sleeps the configured interval after the scan. Archive policy/retention is a later task; no input deletion or automatic cleanup is introduced here. Review crops/model evidence and dashboard health are Stage 4 onward.

Next, only after approval: **Stage 3 — one processing worker** that consumes queued snapshots through the existing converter, publishes invoices safely and handles locked outputs/restarts. It must verify snapshot hashes before processing and preserve current invoice facts/styles.
