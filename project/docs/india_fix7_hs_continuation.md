# India Fix 7: HS codes through supported continuations

Completed 23 October 2026. Only checklist task 7 is implemented. Handwritten-description review is task 8 and needs the next approval. India automatic watching/editing and Jordan remain disabled.

## Diagnosis and rule

India read an HS code only from an item's own source row. Fix 5 already linked supported product/color continuations, but an empty HS cell on the next row/page remained empty and could split an otherwise valid goods group.

HS enrichment now reuses those existing heading links. An explicit source code can extend forward to blank HS cells in the same supported product chain. For example, ZIPPER 2 PCS with 00012345 and a supported next-page color row with 1 PCS and a blank code become 3 PCS with literal HS 00012345. A heading without quantity can supply its printed code to following color rows. A later coded color row can supply following blanks, but does not backfill earlier rows.

Inheritance requires exactly one unique readable code in that linked chain, with no unreadable nonempty HS declaration or ambiguous HS-column mapping. If there are conflicting codes or an invalid declaration, blank rows stay blank throughout the chain; readable row-specific codes are preserved. No code is chosen to match a manual reference. The existing 6–10 digit source format and whitespace normalization are retained, including leading zeros; letters/punctuation are not repaired into a code. Missing codes do not generate classifications.

New products/styles, unrelated tables, page gaps and other Fix 5 boundaries do not share a heading link and cannot borrow a previous code. An established linked continuation can retain its known code when a later table omits the HS column. Different explicit codes remain separate through existing aggregation. Rates and amounts are never inherited; each row keeps its own source-money policy.

Original OCR is unchanged. Each accepted HS event records the destination source row, actual coded source row, original reading and direct/continuation method. Inherited items also retain the coded row in source_refs. The existing writer prints HS codes as text and the existing publication gate verifies them. Only india.py changes in production; no new OCR/model call, merged-cell detector, dependency, setting, API, template or dashboard change is added. Bangladesh and invoice-number/date logic are unchanged.

## Acceptance

- 124 focused India tests pass, including 13 new HS tests and an updated continuation assertion that still forbids money inheritance. Coverage includes same/next/multiple-page inheritance; quantity-free headings; conflicts; invalid/missing codes; independent headings/styles; no backward fill; ambiguous HS columns; absent continuation HS columns; whitespace/leading zeros; table/page boundaries; and exact coded-row provenance.
- A synthetic two-page pipeline test exports the combined 3 PCS row with 00012345 stored as text in printed cell E33.
- The real QueueWorker processes the existing three-page India PDF in isolated folders under original, neutral and conflicting filenames. All structured facts/values remain identical to Fix 6 apart from source_file. These are three filename cases for one shipment, not three independent PDFs. Verified source/model caches are reused without mocking OCR/parser/model responses. Only the cache path is redirected; the manual-reference-access guard records zero reads.

The full gate passes **421 tests in 89.346 seconds**, and the dashboard status check passes. The real invoice prints on one page with text identical to Fix 6 and was visually inspected. All 20 Bangladesh parser results and 20 valuation results match exactly. All 169 protected production files and 20 jobs/20 attempts/832 events plus queue/admin history match the stopped backup; SQLite integrity is OK. No production invoice was reset or reprocessed. The service is restarted, eight dashboard/API/preview/download routes return HTTP 200, and watching remains Bangladesh only. Final results and the verified release manifest are recorded in reports/india_fix7_20261023/verification.json and release-verification.json.

## Limits, evidence and rollback

This uses clear product/color continuation evidence already supported by Fix 5; it does not add physical merged-cell detection or extend product categories/column-layout recognition. A visually merged HS area without a readable product link is not assumed to classify unrelated rows. Conflicting or unreadable declarations deliberately leave blanks unresolved. The rule verifies association, not the legal correctness of the printed classification or OCR digits. No external HS lookup or model-invented classification is used.

The real sample does not demonstrate all new HS-continuation layouts. New boundaries are tested with synthetic OCR/table fixtures and a synthetic pipeline export; additional unseen real India shipments are still needed for a general accuracy claim. Existing handwriting/runtime limits remain unchanged.

Evidence is under reports/india_fix7_20261023: pre-fix7-backup.zip/before.json; focused-tests.log and final-acceptance.log; acceptance.json and worker-acceptance.log; isolated worker-run-final invoices/evidence; bd-parser-after.json; native print/invoice.png and print/verification.json; verification.json, startup-status.json and release-verification.json. Production packaging excludes development/test/runtime/input/reference folders using the existing allowlist.

The service was stopped/drained before editing and 197 stopped-state/application/data files were backed up with verified hashes. Transient logs/native locks/WAL files are excluded. Stop and drain before restoring matching application and data together; never overwrite a live SQLite database. The Fix 6 release supplies matching entry points/dependency/docs files. Destructive rollback and physical reboot were not performed.

Next: **Fix 8 — review the unresolved handwritten goods description**, after user approval.
