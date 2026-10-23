# India Fix 4: bounded header layout reading

Completed 22 October 2026. Only checklist task 4 is implemented. Goods continuation across pages/tables is task 5 and requires the next approval. India watching/editing and Jordan remain disabled. Bangladesh behavior, templates, frontend, model settings and valuation are unchanged.

## Diagnosis and change

India's packing dates required a colon and same-line value. Shipping marks required a colon and a next-line value. Destination Airport required a next-line city/comma/India reading. Correct source values in equivalent layouts could therefore disappear even though OCR had read them.

The existing India module now reads a label's same-line remainder or immediate nonempty next line, and right/below neighbouring OCR table cells. It supports optional colon/equal/hyphen separators, Shipping Marks and Marks & Nos / Marks and No labels, and the original combined cover headings. Known next-field labels terminate a reading; it does not search through unrelated fields for a later answer. Retained OCR is not changed. Each candidate records its page, text/table location and source reading in evidence.

Dates use the existing calendar parser. Explicit export dates have priority; conflicting, ambiguous or unreadable declarations remain blank and block packing fallback, including declarations present only in tables. Without an export declaration, select the latest readable labelled packing date on a PACKING LIST page. Packing numeric dates retain the approved month/day/year convention; explicit export numeric dates remain strict. Order, expiry and other labelled dates do not become packing dates.

Marks and destination airport are read only from the cover. Supported package suffixes are separated from the mark. Conflicting readable marks/destinations remain blank. A destination requires a readable city and India, with the supported comma/space/parenthesis layouts. Consignee, warehouse, origin and other field labels cannot supply it. No airport-to-port inference is added. Source identifiers/address handling and explicit port/terms behavior remain unchanged.

This changes only india.py and its date dispatch in parser.py. There is no new dependency, additional OCR/vision request, frontend/API change or settings migration. No manual expected output is read by conversion; no validation text is printed on invoices.

## Acceptance

- **375 tests pass in 84.119 seconds**, including 17 new focused header tests with layout/boundary subcases. The existing dashboard status transition check passes.
- Layout tests cover same/next-line dates and marks, optional separators, combined cover headings, destination punctuation, adjacent right/below table cells, immutable OCR and source-location evidence. Negative cases cover unrelated dates/addresses/notes/cartons, conflicts, malformed/ambiguous dates and table-only unreadable export labels blocking packing fallback.
- The real QueueWorker converts the existing three-page India PDF under original, neutral and deliberately conflicting filenames in isolated report folders. All source facts and values remain identical to Fix 3, apart from each source_file. These are three filename cases for **one shipment**, not three independent PDFs. Verified source/model caches are reused; no OCR/parser/model response is mocked. Only the cache path is redirected. The reference-access guard records zero reads.
- Preserved source result: S/5196/26; 13-Oct-2026; TGPLFOCTS; Chennai, India; source consignee/address/IEC/PAN/GST; T01–T07; 7 packages; explicit gross 106 kg; fabric 378 YDS, zipper 65 PCS, printed FABRIC CUTTINGS 3 SETS; USD 82.40. Unsupported port/terms remain blank.
- Hidden read-only native Excel export is one page. Its extracted printed text is identical to Fix 3; the rendered invoice was visually inspected. Existing color/alignment/layout are preserved.
- All **20 Bangladesh parser results and 20 valuation results match exactly**, including existing diagnostics. All 169 protected files and job/attempt/event/queue/admin history match the stopped backup. SQLite integrity is OK. No production invoice was reset or reprocessed.
- The production service is restarted; eight dashboard/API/preview/download routes return HTTP 200. Production watching remains Bangladesh only.

## Evidence, limits and rollback

Development evidence is in reports/india_fix4_20261022: verified pre-fix4-backup.zip/before.json, focused-tests.log, final-acceptance.log, worker-acceptance.log, acceptance.json, isolated worker-run-final invoices/evidence, bd-parser-after.json, print/invoice.png and print/verification.json, verification.json and release-verification.json. Build output uses the existing allowlist and a verified SHA-256 manifest; test/report/runtime/input/reference folders are excluded.

This improves layouts when the source value is already present in OCR; it does not restore unreadable pixels or guarantee arbitrary form layouts. Unsupported label wording, distant values, non-India destination readings and unclear/conflicting fields may remain blank. A wrapped unreadable export label still blocks packing fallback. Table adjacency uses the immediate right/below cell, not a search across other fields. Additional unseen real India shipments are still required before making a general accuracy claim. Existing best-effort invoice-number/handwriting limits from Fix 3 remain.

Before this update the service was stopped/drained, and 197 stopped-state/application/data files were backed up with verified hashes. The backup excludes transient logs/native locks/WAL files. Stop and drain before restoring matching application and data together; do not overwrite a live SQLite database. The Fix 3 release supplies matching entry points/dependency/docs files. Destructive rollback and physical reboot were not performed.

Next: **Fix 5 — supported goods continuation across tables/pages**, after user approval.

