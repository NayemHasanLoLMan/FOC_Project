# India Fix 5: goods continuation across tables/pages

Completed 22 October 2026. This implements only checklist task 5. Printed-header publication verification is task 6; HS inheritance remains task 7. India automatic watching/editing and Jordan remain disabled.

## Diagnosis and change

India's existing product/color normalization reset its product and source-heading reference at every table. A ZIPPER heading with 2 PCS followed by an adjacent table/page containing Col. Blue with 1 PCS became unrelated descriptions instead of a supported 3 PCS zipper group.

The existing prepare_tables function now retains that context between consecutive compatible goods tables on the same or immediately following page. The new table must begin with an explicit color row. Quantity units must be explicit, complete and compatible with the preceding product. Blank rows do not erase context. Matching multiline quantities are summed once using the existing quantity rules. Original OCR is unchanged; each continued item retains its original row reference plus the original heading reference. Evidence records the original color text, heading source and whether a table boundary was crossed.

Context stops at new products/styles, meaningful rows without a description cell, totals, intervening unrecognized tables, incompatible columns, skipped/backwards pages, overlapping same-page tables, explicit new item/sender identities, and unknown/mixed/incompatible quantity units. A new explicit recognized product heading can restart context. Source text before the first continuation row is checked for a new style; ambiguous repeated color locations are rejected conservatively. Source matching uses original rows rather than normalized copies.

The existing parser/aggregation, source price/amount handling, valuation, writer and publication workflow are reused. Source money remains associated with its own row; compatible prices aggregate, different prices remain separate. HS codes, rates and amounts are not inherited into empty cells. No extra model/OCR call, dependency, API, setting, frontend or template change is added. Only india.py changes in production. Bangladesh's parser path is unchanged. No validation/review text is added to the invoice.

## Acceptance

- 21 focused continuation tests cover table/page/multiple-page carry-over, blank rows, original source references and immutable OCR, new styles/products/identities, missing descriptions, totals, unrelated tables, incompatible columns, page order/gaps, overlap, ambiguous color locations, unknown/mixed units, multiline quantities and row-specific source prices/amounts. A pipeline test writes the 3 PCS result and USD 0.30 calculated value into Excel.
- The real QueueWorker processes the existing three-page India PDF in isolated folders under original, neutral and conflicting filenames. All data apart from source_file remains identical to Fix 4. These are three filename cases for one real shipment, not three independently supplied PDFs. Verified source/model caches are reused without mocking OCR/parser/model responses. Only the cache path is redirected; a reference-access guard records zero manual expected-output reads.
- The real sample remains S/5196/26; 13-Oct-2026; TGPLFOCTS; Chennai, India; 7 packages; explicit gross 106 kg; fabric 378 YDS, zipper 65 PCS, printed FABRIC CUTTINGS 3 SETS; USD 82.40. Source address/identifiers, width, HS and legitimate blanks remain unchanged.
- Native hidden, read-only Excel export remains one page, with text identical to Fix 4. Its rendered invoice was visually inspected.
- All 20 Bangladesh parser results and 20 valuation results match exactly. All 169 protected files and the 20 jobs/20 attempts/832 events plus queue/admin history match the stopped backup; SQLite integrity is OK. No production invoice was reset or reprocessed. The service is restarted and eight dashboard/API/preview/download routes return HTTP 200. Watching remains Bangladesh only.

The full regression gate passes 396 tests in 86.655 seconds; the dashboard status transition check also passes. Final production preservation and release results are recorded in reports/india_fix5_20261022/verification.json and release-verification.json. Current acceptance totals are also recorded in the checklist and implementation-plan checkpoint.

## Limits, evidence and rollback

Cross-table continuation requires explicit color-prefix and quantity-unit evidence plus compatible discovered column positions. Headerless fragments, reordered column layouts, bare quantities without explicit units, repeated/ambiguous color locations and distant context may remain ungrouped. Unreadable source text is not invented. A repeated style above a new table may conservatively stop inheritance. Missing HS still prevents otherwise similar rows with different HS evidence from aggregating; fixing supported HS continuity is task 7, not part of this update.

The available real India shipment does not demonstrate every new continuation layout. New continuation boundaries are covered with synthetic OCR/table fixtures and a synthetic-PDF pipeline export test. Additional unseen real shipments remain necessary before claiming general extraction accuracy. Existing model/handwriting limits remain unchanged.

Evidence is under reports/india_fix5_20261022: pre-fix5-backup.zip/before.json; focused-tests.log and continuation-tests.log; final-acceptance.log; acceptance.json and worker-acceptance.log; isolated worker-run-final output/evidence; bd-parser-after.json; native print/invoice.png and print/verification.json; verification.json, startup-status.json and release-verification.json. Development artifacts are excluded by the production release allowlist.

Before editing, the service was stopped/drained and 197 stopped-state/application/data files were backed up with verified hashes. The backup excludes transient logs/native locks/WAL files. Stop and drain before restoring matching application and data together; never overwrite a live SQLite database. The Fix 4 release supplies matching entry points/dependency/docs files. Destructive rollback and physical reboot were not performed.

Next: **Fix 6 — verify every printed India header before publication**, after user approval.

