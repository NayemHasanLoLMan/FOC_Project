# India / Jordan Stage 3 — India master and writer

22 October 2026. Stage 3 updates the reusable India master and its writer. It does not change OCR, parsing, grouping, valuation, regional activation, dashboard behavior or the Bangladesh/Jordan layout functions.

## Delivered

- Cleaned `templates/INDIA_template.xlsx` once so future invoices inherit the same Arial typography, aligned columns, sensible merging/wrapping and explicit A4 portrait print settings. Kept the original shipper/title, invoice structure, HS/quantity/value columns and three trade-sample declarations.
- Removed the fixed Chennai shipping route/country defaults and duplicate generic declarations. Destination, port and shipment terms print only when supplied by structured data. This is rendering support, not a new extraction or business rule; unsupported fields stay blank.
- Dates are real Excel dates displayed as `dd-mmm-yyyy`. Quantities/weights/totals remain numeric; HS codes are literal text, preserving leading zeros. Text beginning with `=` is stored as text rather than a spreadsheet formula.
- Preserved red highlights for supplied carton/package/gross/total and address identifiers, with blue supplied header identifiers. Corrected the inherited black-and-white print flag so colors survive native Excel export.
- Replaced the six-item truncation with dynamic insertion before totals/footer. All goods print; carton labels occupy their own column, and descriptions expand through row heights without moving quantities into another item. Extra carton labels can grow the area independently of goods.
- Long addresses keep all lines: overflow is folded into the last address row with wrapping. Empty unused address/goods rows collapse to reduce blank space.
- The total and declarations move with the goods area and stay within print bounds. The three declarations share one multiline cell/physical row, preventing that block from splitting across pages. Table headers repeat on continuation pages with separate company/invoice identity and one page counter.
- Oversized text exceeding Excel's printable single-row height is rejected with a specific error rather than silently clipped. Splitting a single exceptionally large description over multiple physical rows is not part of this stage.
- India publication verification now independently checks the actual numeric total, typed date, and each required declaration exactly once below the total inside the print area, in addition to existing source coverage/goods/HS/amount checks.

## Acceptance checks

| Check | Result |
|---|---|
| Full frozen-code regression suite | **303 tests passed**, 109.925 seconds |
| Dashboard JavaScript checks | Passed |
| India 0 / 1 / 7 / 40 goods rows | All rows, quantities, identifiers, amounts and moving footer verified |
| Native Excel PDF exports | Blank master plus five isolated QA invoices exported using a separate hidden, read-only Excel instance |
| Native page counts | Master, 0/1/7-item and long-description/address samples: one page each; 40 items: two pages |
| All 40 items in native PDF | Present; repeated table heading on each page; final total/declarations present |
| Visual inspection | Every page of the final six PDF exports inspected; no clipped tested text/numbers, overlapping continuation header or orphaned declaration lines |
| Print colors and footer identity | Red/blue retained; escaped ampersand followed by digits prints literally; duplicate old page counter removed |
| Missing/stale data | Supplied-master stale cells cleared; absent destination/port/terms/prices/date remain empty; zeros preserved |
| Safe regional publication | Wrong total/text date/missing or unprinted declarations rejected; oversized-field failure preserves an existing output |
| Bangladesh preservation | All 20 retained results re-rendered in isolation: identical visible values, cell styles, dimensions, row heights, column widths, print areas and repeated headers |
| Other country writers | Bangladesh and Jordan function ASTs unchanged; BD/Jordan masters unchanged |

Tests use synthetic structured values to isolate layout. Their dates, rates and totals do not approve India valuation or resolve PDF date conflicts. The 2025/2026 source conflict, missing source prices, explicit identifiers/HS extraction and universal goods grouping remain Stage 4 work. No fresh India OCR/model result or production-accuracy percentage is claimed.

The first print pass revealed black-and-white export, continuation-header spacing and declaration splitting; these were fixed before the final exports/checks. Earlier sample PNGs may remain as development evidence; `print/final-*.png` and the current PDFs are the final reviewed versions.

## Evidence and rollback

Evidence is under `reports/india_jordan_stage3_20261022/`: verified `pre-stage3-backup.zip`/`before.json`, `regression.log`, `native-print-verification.json`, `bd-preservation.json`, isolated `samples/`, native `print/` exports and final `verification.json`. No generated QA workbook was placed in the production output folder.

The backup includes matching stopped schema-6 state, input snapshots, evidence, output, masters, backend and frontend. The Stage 2 production ZIP supplies matching configuration/entry points/dependency declarations/documentation. To roll back, stop/drain first and restore matching code, the previous India master and matching state/artifacts/output together. Do not overwrite a live SQLite database or combine unrelated application/data snapshots. Native Excel/model installations are not bundled. A destructive restore and physical reboot were not performed.

The main service restarted successfully after regression/preservation checks passed, with the same Bangladesh settings and no new regional inbox enabled. All 20 completed jobs/attempts, existing events/queue/admin history and published invoices are preserved; input/evidence/frontend/other masters/settings hashes are unchanged. Eight live dashboard/detail/edit/preview/download HTTP checks passed. See `verification.json` for the exact record. Stage 3 introduces no schema migration.

## Next gate

Stage 4 starts with India source extraction only: printed IEC/PAN/GST, HS, composition/width, quantity and grouping, followed by isolated PDF-based comparison. Resolve conflicting source dates before accepting an invoice date policy. India rates and rounding require a separate reviewed valuation update. Await user approval before starting Stage 4; Jordan remains unchanged and inactive.
