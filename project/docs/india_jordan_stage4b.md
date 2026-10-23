# India / Jordan Stage 4B: India valuation

Completed 22 October 2026 after explicit approval of the rates and two-decimal total. This update changes valuation only: no OCR, extraction, template, frontend, API, schema, production model or regional watching changes.

## Approved standing policy

| Category | Required unit | USD unit rate |
|---|---|---:|
| Fabric | YDS | 0.20 |
| Zipper / zippers | PCS | 0.10 |
| Fabric (or FAB) swatch/swatches, sample/samples, cutting/cuttings | SETS | 0.10 |

The India rates live in a separate `india` object in the existing valuation_rates.json. Existing Bangladesh keys and amounts are unchanged. Reusing the same file preserves the existing build and attempt rate-fingerprint checks without adding another configuration interface.

The shared helper applies only approved regional category/unit matches, preserves explicit source prices/amounts/totals, calculates lines to cents and India shipment totals to cents using Decimal half-up. Source descriptions, quantities, units, HS and provenance remain unchanged. Unrecognized items, unmatched units or invalid quantities stay uncalculated; a missing line amount or incomplete PDF prevents a calculated shipment total. These approximate rates are commercial assumptions approved by the user, not amounts extracted from the PDF. Jordan remains unpriced.

## Actual sample acceptance

The actual India PDF was run through the real QueueWorker in isolated state/artifacts/output, reusing the source-keyed OCR and model cache already checked in Stage 4A. No new model inference was needed for a pricing-only update. Only the worker cache path was redirected for isolation; OCR/parser/valuation/writer/verification/publication results were not mocked. All reads of expected_outputs were blocked during conversion; zero reference reads occurred.

| Goods | Quantity | USD rate | USD amount |
|---|---:|---:|---:|
| Source fabric, with composition, width and HS | 378 YDS | 0.20 | 75.60 |
| ZIPPER | 65 PCS | 0.10 | 6.50 |
| Printed FABRIC CUTTINGS | 3 SETS | 0.10 | 0.30 |
| Total | | | **82.40** |

This total agrees with the manual reference. The system did not read or copy that reference at runtime. PDF-first differences established in Stage 4A remain: source date 13-Oct-2026, width 53 inches and printed cuttings when handwriting is unresolved. The invoice number still uses the existing recognizable-filename fallback. A matching example does not prove universal production accuracy.

## Verification

- All **324 tests passed in 77.902 seconds**. New tests cover category/unit boundaries, unsupported rows, source-value priority, invalid configuration/quantities, incomplete pages and exact half-up cent rounding.
- The same 20 Bangladesh source-parser results were valued before/after the update: all structured facts, prices, amounts, totals and diagnostics are identical.
- The isolated worker completed publication; receipt region, exact printed amounts, cent number format and the actual regional rates SHA-256 were verified.
- Native Excel exported the final workbook read-only to one PDF page. All four amounts were checked in PDF text, and the final page was visually inspected.
- Existing production input, artifacts, output, frontend and all masters remain unchanged. Final verification records retained job/history equality, live HTTP checks, service status and release-manifest hashes.

Evidence is in reports/india_jordan_stage4b_20261022, excluded from production releases: acceptance.log, acceptance.json, verify_stage4b.py, bd-valuation-before.json, worker-run/output/26S5196-I.xlsx, print/26S5196-I.pdf and verification.json.

## Rollback and next stage

The verified pre-stage4b-backup.zip contains the stopped matching schema-6 state, sources/artifacts/output, masters, backend/frontend, configuration and prior rate file. The previous India-extraction release supplies matching entry points and dependency/documentation files. Stop/drain before restoring matching code, rate file and data together. A destructive restore and physical reboot were not performed.

Next is **Stage 5: Jordan master and expanding writer**. Obtain user approval before implementing it. India/Jordan regional editing and automatic inbox watching remain later work; the existing BD watcher remains the only enabled production inbox.
