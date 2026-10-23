# India Fix 6: verify printed headers before publication

Completed 23 October 2026. Only checklist task 6 is implemented. HS continuity is task 7 and needs the next approval. India automatic watching/editing and Jordan remain disabled.

## Diagnosis and change

The existing publication check independently verified goods, totals, dates, audit/source coverage and regional print bounds. Most India header cells could differ from structured data without failing that check. A correct audit sheet alone did not prove that the customer-facing worksheet contained the right header.

The same verify_workbook function now compares the mapped India header against the structured conversion result, including legitimate blanks. It is already called by direct regional conversion before replacing an output and by QueueWorker before preparing a publication receipt. No second validator, workflow, API, dependency or OCR/model call is introduced. Only workbook_verification.py changes in production; extraction, valuation, templates, frontend, settings and Bangladesh/Jordan validation behavior are unchanged.

| Printed information | Verified locations |
|---|---|
| Invoice number and typed export date | C25, C9 |
| Consignee | B11 |
| Address and identifiers as rendered, including leading zeros | B12–B16 |
| Shipping marks and destination city/country | H11, H12, D20 |
| Carton declaration and all goods-column carton references | H13, column A from row 33 to the total |
| Package count and gross kilograms | B27, G27; PKG(S) ONLY. and KGS unit labels |
| Supported port of discharge and shipment terms | A22, A23 |

Address comparison independently applies the documented layout contract: trim nonempty source lines, split a single long comma-separated address, and retain excess lines together in the fifth address cell. It checks every resulting cell, including empty slots, rather than trusting the audit or dropping identifiers beyond five lines. Carton references are checked independently of the number of goods rows; extra, missing or changed references fail.

Numeric zero stays valid and is distinct from blank; booleans do not qualify as counts/weights. Formula-like source strings must remain literal text, not executable formulas. The primary India invoice worksheet must remain active and visible. Populated mapped cells must be within the print area and outside hidden/zero-height rows or hidden/zero-width columns, including grouped columns. The India print range must include the sheet from A1 through its goods and total. The gate accepts the known master-readable header formats and rejects formats that hide or replace values; it preserves the master's d-mmm format on literal carton strings because Excel prints that text unchanged. No formatting is changed by verification.

Supported unavailable fields remain blank. No validation/review message is printed on the invoice; failures use the existing job error path. No four-digit-only invoice-reference constraint is introduced.

## Acceptance

- **408 regression tests passed in 70.472 seconds**. All 111 focused India tests pass, including 12 new header/publication tests with field-by-field subcases. The dashboard status transition check passes.
- Each mapped header location is deliberately changed while the audit remains unchanged and must fail. Tests cover stale values in unsupported fields; all-blank optional data; numeric zero and boolean rejection; leading-zero identifiers; long/folded and comma-separated addresses; formula-like literal values versus formulas; changed/extra carton references; more cartons than goods rows; hidden/grouped columns/rows/sheets; truncated print areas; and invalid/hiding formats.
- Direct conversion rejects a corrupted header before replacing existing Excel or JSON output. A queue test first publishes a valid invoice, then rejects a new source version with a corrupted header: the prior job/output remains completed and byte-identical, and the rejected attempt has no published output path.
- The real QueueWorker processed the same three-page India PDF under original, neutral and conflicting filenames in isolated folders. All facts and values remain identical to Fix 5, apart from each source_file. These are three filename cases for one shipment, not three independent shipments. Verified OCR/model caches are reused; no OCR/parser/model response is mocked. Only the cache path is redirected. The reference-access guard records zero manual expected-output reads.
- The source result remains S/5196/26; 13-Oct-2026; TGPLFOCTS; Chennai, India; original consignee/address/IEC/PAN/GST; T01–T07; 7 packages; explicit gross 106 kg; 378 YDS fabric, 65 PCS zipper and 3 SETS printed FABRIC CUTTINGS; USD 82.40. Unsupported port/terms remain blank.
- Native hidden, read-only Excel export is one page, with printed text identical to Fix 5. The rendered invoice was visually inspected.
- All 20 Bangladesh parser results and 20 valuation results match exactly. All 169 protected files and 20 jobs/20 attempts/832 events plus queue/admin history match the stopped backup. SQLite integrity is OK. No production invoice was reset/reprocessed. The service is restarted and eight dashboard/API/preview/download routes return HTTP 200. Watching remains Bangladesh only.

## Limits, evidence and rollback

This verifies the printed workbook's agreement with structured data; it cannot establish that OCR/model readings are true to the PDF. It is a cell/layout/format gate for the known India master, not a full Excel rendering engine or a check of arbitrary custom typography, text clipping, corporate artwork or repeated page-header/footer formatting. Native print QA covers the available real sample; additional unseen real India shipments remain necessary for broader accuracy claims. Unsupported custom header formats fail conservatively rather than being interpreted by a new rendering layer. Existing extraction/handwriting and missing-HS limits remain unchanged.

Evidence is under reports/india_fix6_20261023: verified pre-fix6-backup.zip/before.json; focused-tests.log/india-tests.log; final-acceptance.log; acceptance.json and worker-acceptance.log; isolated worker-run-final invoices/evidence; bd-parser-after.json; native print/invoice.png and print/verification.json; verification.json, startup-status.json and release-verification.json. Production packaging uses the existing allowlist and verifies every release file against its SHA-256 manifest; development/test/input/runtime/reference folders are excluded.

Before editing, the service was stopped/drained and 197 stopped-state/application/data files were backed up with verified hashes. Transient logs/native locks/WAL files are excluded. Stop and drain before restoring matching application and data together; never overwrite a live SQLite database. The Fix 5 release supplies matching entry points/dependency/docs files. Destructive rollback and physical reboot were not performed.

Next: **Fix 7 — preserve HS codes through supported continuations**, after user approval.
