# India Fix 8: handwritten-description review

Reviewed 23 October 2026. Task 8 is complete as an investigation with a supported fallback; the handwritten subtype remains unresolved. **No production code, model setting, template or invoice behavior is changed.** Runtime/call optimization remains task 9 and needs the next approval.

## Source and fresh comparison

The third PDF page contains the readable printed heading Bulk Interlining fabric cuttings, a yellow-highlighted handwritten FAB note, and three color rows of 1 SET each. The invoice already preserves FABRIC CUTTINGS, 3 SETS. The original scan/context, retained OCR coordinates and focused crops were visually inspected. Manual reference invoices did not supply the transcription or candidate words.

Earlier Stage 4 tests produced SMARTONES/SMATONES variants using whole-cell and tight crops with both installed readers. This review tested a new focused crop based on the existing word box: 8-pixel source padding, a 16-pixel white border and 3× scaling. A maximum-RGB-channel grayscale version removes yellow highlighting while retaining the black ink geometry. The original color crop was also retained. No stroke reconstruction, character replacement, table-rule erasure or source-PDF edit was used. This preprocessing was a private experiment and was not installed in production.

| Installed reader / experiment | Fresh result | Elapsed |
|---|---|---:|
| qwen3.5:4b, highlighting separated, neutral transcription | FAB SMARTONES | 46.875 s |
| qwen3.5:4b, original color crop, neutral letter-by-letter instruction | FAB SMARTONES | 60.000 s |
| qwen3-vl:latest, highlighting separated, neutral letter-by-letter instruction | FAR SMARTOMES | 252.984 s |

All three requests completed normally with done_reason=stop and fresh responses, not a timeout or token truncation. Existing limits remained 4096 output / 8192 context tokens and 7200 seconds, temperature 0, think=false and keep_alive=0. Prompts contained no expected goods name, candidate list, invoice reference or filename answer. Exact sent RGB PNGs were reconstructed and verified against the existing transport's image/model/prompt/schema/options cache keys; raw responses, model digests and metrics are retained.

## Decision and acceptance

These results do not reliably establish a replacement for the printed heading. Do not map SMARTONES/SMARTOMES to a guessed subtype or force FAB SWATCHES from a reference. Retain **FABRIC CUTTINGS, 3 SETS**. Adding a preprocessing branch or automatic model cascade would add work without a demonstrated accuracy gain here, so neither is added. Larger timeout/output allowances would not resolve the completed recognition errors observed in these requests. Hardware improvements may reduce latency, but do not establish transcription correctness.

- All 14 existing India extraction/annotation tests pass, including acceptance/rejection, unusable/offline reader behavior, source retention and printed-description fallback.
- The real QueueWorker processes the same three-page PDF under original, neutral and conflicting filenames in isolated folders, reusing verified source/model caches. No OCR/parser/model response is mocked; only the cache path is redirected. All facts, values and diagnostics remain identical to Fix 7 apart from source_file. The reference-access guard records zero reads. These are three filename cases for one shipment.
- All 20 Bangladesh parser results and 20 valuation results match exactly. Production source hashes have no changed modules; all 169 other protected files and job/attempt/event/queue/admin history match the stopped backup. SQLite integrity is OK. No production invoice is reset/reprocessed.
- The service is restored and eight dashboard/API/preview/download routes return HTTP 200; watching remains Bangladesh only. No review/validation message is added to the printed invoice.

The production code is byte-identical to the Fix 7 code that passed the 421-test full gate. That full suite and native print export were not repeated for this documentation-only review; the focused fallback tests, fresh reader comparison, isolated queue comparisons and preservation checks were run. There is no claimed accuracy improvement for this handwritten note. A clearer source or a demonstrably better reader may resolve it later; the rest of the invoice is complete from supported source data.

## Evidence and recovery

Evidence is under reports/india_fix8_20261023: pre-fix8-backup.zip/before.json; original.png/highlight-separated.png and exact sent-*.png; reader-comparison.log/json with raw model responses and metrics; cache/local_vision completed responses; probe-verification.json; fallback-tests.log; acceptance.json/worker-acceptance.log and isolated worker-run-final invoices/evidence; bd-parser-after.json; verification.json, startup-status.json and release-verification.json. The production release allowlist excludes these private experiments/data/images; only documentation changes enter the release.

The service was stopped/drained and 197 stopped-state/application/data files backed up with verified hashes before testing. Transient logs/native locks/WAL files are excluded. Production application/data restore is unnecessary because they are unchanged. For any recovery, stop/drain before restoring matching files and never overwrite a live SQLite database. No destructive restore or physical reboot was performed.

Next: **Fix 9 — review vision runtime and unnecessary calls**, after user approval.
