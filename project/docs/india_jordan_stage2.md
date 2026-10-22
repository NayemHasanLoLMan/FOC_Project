# India / Jordan Stage 2 — country-aware core

22 October 2026. This update prepares explicit regional conversion and durable job identity. The production watcher still accepts only its existing Bangladesh inbox. India/Jordan template repairs, extraction rules, rates, dashboard country controls and regional activation remain later stages.

## Implemented

- Direct and batch commands accept `--region BD|INDIA|JORDAN`, defaulting to BD. Default output follows that selection. The Python `run(..., region=None)` API retains legacy source selection; managed processing always supplies the recorded job region.
- Region codes are validated. A named master for another region, a conflicting parsed destination/recognized consignee, or an explicit conflicting destination-country label on the cover fails conversion instead of silently publishing a Bangladesh invoice. Later packing-page recipient conflicts are not used to reroute an entire shipment; the 5173 page-6 decision remains pending.
- Schema 6 adds `jobs.region` with a three-value constraint. Migration assigns BD to existing jobs without changing their other fields or historical attempts/paths. Same path/content cannot be accepted again under a different region. The scanner's omitted region remains BD.
- Each new managed attempt captures its region and the actual selected master path/hash. The worker selects these within the claim transaction from the queued job, rather than assuming a BD master. Conversion verifies its region before writing/preparing; source/template/rates/application change checks remain enforced.
- Prepared receipts record region. Recovery checks it against the job and attempt. Old receipts/attempt metadata without region remain valid for migrated BD jobs. Prepared-save recovery retains its original output directory, even if current settings differ.
- The existing independent worksheet verification now uses the region's real goods/quantity/unit/total columns. India additionally checks printed HS/amount; Jordan checks printed item kg/amount. Audit/source identity and full PDF-page coverage remain required. Regional print ranges must include all goods and the total.
- Direct non-BD conversion verifies a temporary workbook before replacing a final XLSX. Truncated rows, duplicate totals or unsafe legacy print bounds are rejected. The unchanged India/Jordan masters are deliberately **not yet production-ready**; their next writer stages must satisfy these gates.
- Both `expected_outputs` and legacy `expected_output`, including descendants/overlapping parents, are protected against output selection. Settings also protect them as input. Batch validates output before writing its manifest; direct conversion checks before OCR.
- Removed the unsupported rule that every non-BD invoice must have net weight. No new weight, package, pricing, date or origin inference policy was introduced.
- Updated CLI, state, API/OpenAPI, code and rollback documentation. New API region/template-path fields are additive responses; HTTP commands and Postman request bodies are unchanged. Regional editing remains unsupported until its planned stage.

## Verification

The saved evidence under `reports/india_jordan_stage2_20261022/` contains the final regression log, migration rehearsal, BD cover checks, isolated re-rendered workbooks and sheet comparisons, pre-migration database, and final live verification.

- Rehearsed migration against a copy of the actual stopped schema-5 database: all 20 jobs and 20 attempts preserved; every pre-existing row/field across all application tables unchanged; only the job region column added as BD; integrity check `ok`.
- Re-rendered all 20 completed Bangladesh results into the isolated report directory using the new writer entry path. **20/20 visible invoice sheets match** in values, cell style arrays, dimensions, row heights, column widths, print ranges and repeated-header settings. Production outputs were not replaced.
- All 20 retained Bangladesh cover/result pairs pass explicit BD identity selection.
- New tests cover schema-5 migration/read-only gating, existing-source reassignment refusal, actual regional master fingerprints, destination/template/unknown-region rejection before output, protected reference folders, regional quantity/HS/weight tampering, page coverage and print bounds, legacy regional row truncation, safe direct-write failure, regional retry and prepared-save recovery to the original destination.
- Final frozen-code suite: **297 tests passed in 80.140 seconds**; dashboard JavaScript checks passed. CLI help exposes the new region option. Results are recorded in `verification.json` and `regression-gate.log`.
- The main background service migrated and restarted successfully on port 8080: 20 completed jobs/attempts, no active or failed work, unpaused queue, healthy scanner/worker/web. Existing job fields, attempt/event history and admin/queue records are preserved. All 147 managed input/evidence/output/settings files, all three masters and all 20 published XLSX files retain their baseline hashes.
- Ten live HTTP checks passed, including dashboard/jobs/system, job detail/edit, JSON views, invoice preview and an existing canonical-name download. No live reset, manual edit or reprocessing was invoked.

Earlier development runs are retained in `tests.log`/`tests-final.log`. They include an outdated legacy schema fixture and a run during source edits; use the final frozen-code gate as the acceptance result. Deliberately injected locked-folder/disk errors in recovery tests are not live failures.

## Operation and rollback

Normal launch remains `project/.venv/Scripts/python.exe project/run_system.py`. The background task uses the same configuration and port 8080. Existing BD settings and directories are unchanged. Do not enable a new regional inbox yet.

Before moving an older installation to this version, stop/drain it and back up the database/artifacts/output together. Writable initialization migrates schema 5 to 6 automatically; read-only standalone dashboards require prior initialization. To roll back, stop/drain again and restore matching earlier code **and schema-5 state**, retaining the matching artifacts/output. Older code cannot open schema 6. The Stage 1 verified application/data archives and this stage's immediate pre-migration database are retained locally; do not restore over a running system.

This stage does not measure fresh India/Jordan OCR/VL accuracy or complete the earlier reboot acceptance. Synthetic regional verifier workbooks are tests of infrastructure, not usable customer invoices. No production rate, master workbook, frontend asset, input PDF, retained evidence or existing published invoice should change in this stage.

## Next review gate

Stage 2 is complete. Stage 3: India master/writer only—correct columns and typed date, safe expanding goods/descriptions, totals/declarations within print area and 0/1/7/40-item tests. Keep source-extraction and valuation updates separate. Start only after the user approves this stage.
