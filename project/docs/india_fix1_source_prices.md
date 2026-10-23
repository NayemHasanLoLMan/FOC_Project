# India Fix 1: source prices and amounts

Completed 22 October 2026. Only checklist task 1 is implemented. Currency detection and the other India tasks remain pending.

## Problem and change

The audit reproduced a table with printed USD 3.00 per unit and USD 30.00 item amount becoming the fallback USD 0.20 / USD 2.00 for 10 YDS. India now reads explicit monetary columns during table enrichment, before aggregation and valuation. Reuses the existing OCR/table parser, evidence, data model, valuation and writer; no new dependency, API, schema, master/template, frontend, model setting or rate change.

Recognized headers are UNIT PRICE, UNIT VALUE, UNIT COST or RATE; AMOUNT, LINE AMOUNT/TOTAL, ITEM AMOUNT/VALUE or TOTAL PRICE/AMOUNT/VALUE, optionally labelled USD. Cells accept a single nonnegative number, optional USD/US$/$, a decimal point and correctly grouped thousands commas. They preserve zero and fractional rates. Unreadable/multiple/negative/nonfinite values, duplicate matching columns and one monetary value attached to multiple extracted items are not assigned as explicit source money. Existing fallback valuation may still apply to unestablished monetary values where its category/unit is supported; no source amount is fabricated.

Associated source prices/amounts and their row references are emitted as labelled-PDF evidence. Original OCR is unchanged. A valid price without amount calculates the line using the existing cent half-up rule. A valid amount without price stays authoritative with unit price blank. Equal-price rows sum explicit amounts with Decimal; explicit-amount rows and rows requiring calculation stay separate. Differing source prices remain separate. A supplied source total is preserved even if a printed line amount differs from price multiplied by quantity.

## Acceptance

- Before the fix, the focused reproducer failed nine assertions across eight tests.
- After the fix, the full suite passes: **333 tests in 76.819 seconds**, including nine dedicated source-price tests and an end-to-end India workbook/evidence check.
- Printed source rate 3.00 and amount 29.75 survive the pipeline and Excel export, with the source total 29.75 retained. The intentional difference from 10 × 3.00 confirms the printed amount is not overwritten.
- Tests cover amount-only, price-only, absent values/fallback, explicit zero, fractional rates, thousands separators, grouped and partly priced rows, different rates, invalid/duplicate values and ambiguous split rows.
- The actual India PDF completed the real QueueWorker in isolated folders with source-keyed Stage 4A OCR/model caches. Its entire structured result matches Stage 4B, including 378 YDS, 65 PCS, 3 SETS, source headers and USD 82.40. The existing sample contains no printed source item prices, so new price scenarios are controlled OCR fixtures rather than a new real priced-shipment benchmark.
- Zero expected_outputs reads occurred during actual conversion. Source-price fixtures use no manual references.
- All 20 retained Bangladesh OCR documents were replayed through the current parser: all fields and diagnostics match the verified baseline. All 20 valued baseline results also remain identical.
- Final verification records unchanged production files/history and a healthy restarted dashboard. No production invoice was reset or reprocessed.

## Limits and next task

This is labelled row/column extraction, not universal handwritten price reading. Ambiguous shared/split money cells, comma-decimal formats and price factors such as per 100 units are not inferred. Currency detection remains **Fix 2**: current default-USD behavior is still a production limitation and India automatic watching remains disabled. No fresh model benchmark or native print export was required for this extraction-only change; the existing template/writer are unchanged and exported values are checked by the pipeline test.

Evidence: reports/india_fix1_20261022 contains the verified pre-fix1-backup.zip and before.json, before-fix-tests.log, acceptance.log, acceptance.json, bd-parser-after.json, isolated worker-run output, verification.json and release-verification.json. It is development-only and excluded from production bundles. The previous India-valuation release supplies matching entry points and dependency/docs files for rollback. Stop/drain before restoring matching application/rates/state/artifacts; never overwrite a live database. A destructive restore and physical reboot were not performed.

Proceed to Fix 2 only after user review/approval. Jordan remains the final checklist stage.
