# India Fix 2: currency detection and safe export

Completed 22 October 2026. Only checklist task 2 is implemented. Invoice-number extraction is the next task; India automatic watching and manual editing remain disabled.

## Problem and resulting behavior

The audit reproduced an explicitly EUR-labelled PDF-like input being treated as USD and estimated at the default USD rate. India parsing now reads currency evidence before item pricing, using explicit currency labels, financial headings/values and supported adjacent currency cells in recovered tables. Source pages and OCR tables are unchanged.

| Source case | Result |
|---|---|
| Explicit USD, US dollars or US$ | Retain USD; source monetary values keep priority; approved USD estimates remain available |
| Explicit EUR, INR, GBP, HKD or another detected code | Retain the code in parser data; USD estimates are skipped; the USD India export is rejected |
| Contradictory source currency codes | Record candidate evidence and fail; do not choose one currency or convert money |
| Unreadable/ambiguous explicit currency declaration | Record evidence and fail; do not guess USD |
| Missing currency or an empty currency form field | Keep the existing approved USD default; emit approved_default_usd evidence, distinct from labelled_pdf_currency |
| Bare dollar sign in an amount, without another declaration | Does not independently declare a currency; existing USD default policy remains |
| Explicit Currency: $ or an unresolved yen/rupee marker in financial context | Fail safely rather than assume USD |

Financial detection supports common currency codes, money-adjacent three-letter codes and unambiguous US$/HK$/A$/C$/S$/euro/pound/Indian-rupee markers. It does not scan arbitrary address/product words as currency. Unknown three-letter explicit codes remain unsupported, not silently translated into USD. This is bounded OCR-based detection, not a universal recognition guarantee.

The existing valuation helper already excludes non-USD data; no rates changed. Regional selection now prevents non-USD India conversion and direct workbook writing before output replacement. The independent publication verifier checks both the data currency and saved workbook audit currency. Non-USD conversion requires a later supported template/currency workflow; this fix performs no exchange-rate conversion and creates no non-USD invoice.

## Verification

- The pre-fix reproducer failed 17 assertions with one error across nine initial tests.
- Final frozen-code suite: **344 tests passed in 79.953 seconds**. Eleven dedicated currency tests cover labels, adjacent text/table cells, header/cell markers, aliases, unknown codes, lower-case declarations, empty fields, conflicting currencies, ambiguous markers, source prices, unchanged OCR and source/default evidence.
- A direct pipeline test rejects non-USD/conflicting data while preserving existing Excel and JSON bytes, with no writer call.
- A real QueueWorker test records a failed EUR attempt, preserves an existing invoice and publishes no XLSX in attempt artifacts.
- Direct writer and independent verifier reject non-USD data; a changed currency in the workbook audit is independently rejected.
- The actual India PDF completed the real queue using the previously verified source-keyed OCR/model caches in fresh isolated folders. Its full structured result exactly matches Fix 1, including USD 82.40. This source leaves currency blank; the new evidence explicitly records the approved USD default.
- All 20 retained Bangladesh OCR documents were replayed through the current parser: all facts and diagnostics are unchanged. All 20 Bangladesh valuation baseline results are also unchanged.
- Final live verification records unchanged protected production files, retained jobs/history, healthy HTTP routes and the restarted service. No production conversion/reset was invoked.

New currency cases are controlled OCR/queue fixtures. No additional real EUR/INR shipment was available and no new OCR/model inference or native print export was performed. The writer layout/master are unchanged; unsupported-currency cases intentionally produce no invoice. Existing handwritten-reading limitations remain.

## Evidence, rollback and next task

Development evidence is under reports/india_fix2_20261022 and excluded from production releases: pre-fix2-backup.zip/before.json, before-fix-tests.log, final-acceptance.log (the final gate; intermediate acceptance.log is not the release gate), acceptance-final.json, worker-run-final, bd-parser-after.json, verification.json and release-verification.json. The verified backup holds matching stopped state, input/artifacts/output, masters, backend/frontend and configuration/rates. The preceding India-Fix-1 release supplies matching entry points/dependency declarations/documentation. Stop/drain before restoring matching application and data together. A destructive restore and physical reboot were not performed.

Next: **Fix 3 — improve PDF invoice-number extraction**. Obtain user approval before proceeding. Jordan remains the final checklist stage.
