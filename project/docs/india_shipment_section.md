# India reusable shipment section

23 October 2026. Presentation-only follow-up to the [invoice layout review](invoice_layout_review.md). The India master and writer now always show the shipment section; future generated invoices inherit it automatically.

| Line | Current behavior |
|---|---|
| SHIPMENT FROM … TO … BY … | Labels remain visible. TO uses the existing extracted destination city in red. Origin and transport-method slots remain blank because there are no separate mapped source fields for them yet |
| ON/ABT. | Label remains visible; departure date is blank. Packing-list date is not treated as departure date |
| COUNTRY OF ULTIMATE DESTINATION | Existing extracted country and its established formatting are preserved |
| PORT OF DISCHARGE | Visible label; explicit extracted port appears in red, otherwise the value is blank |
| SHIPMENT TERMS | Visible label; explicit extracted terms appear in red, otherwise the value is blank |

The current sample therefore shows CHENNAI, INDIA as destination, country INDIA and the packing date 13-Oct-2026 in the existing top date field. It does not gain a Hong Kong departure origin, AIR method, 14-Oct departure date, discharge port or CPT default from this template update. Origin/method/departure extraction remains separate future work; the template alone cannot populate those slots. No new extraction model call, data field, API, setting or dependency was introduced.

Labels are black, supplied shipment values red, and yellow fill is omitted. Lines wrap across the existing invoice width and remain above the unchanged customs invoice/package/gross/goods sections. The established goods table, declarations, print bounds and continuation headings remain intact. Blank labels are presentation text, not missing-value warnings.

Publication verification now checks these visible lines, including supplied values, stale-value removal, literal text, visibility and print bounds. Empty rich-text runs caused an initial Excel opening failure even though openpyxl could read the workbook. Rendering now writes plain text for empty fields and creates only nonempty rich-text runs for supplied values. A regression check covers this native-format issue.

## Verification and review files

Evidence: `reports/india_shipment_section_20261023/`.

- Existing 20 Bangladesh invoices and the India sample re-rendered in isolated review folders and passed publication checks. All populated cell values/types/formats were preserved except India's four intentional shipment display cells A17/A18/A22/A23.
- Bangladesh/Jordan masters and writer functions are unchanged. No parser, valuation, model configuration, schema, folder routing, frontend or region activation change.
- Final regression results: `final-full-tests.log`. Native Excel previews: `print/`. Preservation and release manifests are recorded alongside them.
- Real India review workbook: `review/india/26S5196-I.xlsx`. `supported-values-demo.xlsx` is a synthetic port/terms rendering test, not PDF-derived data and not a published invoice.
- Existing production history and historical invoice downloads are preserved. New invoices use the updated master; this does not rewrite previous publications.

The main service is stopped/drained before the verified backup and restarted after checks. Rollback: stop/drain and restore `excel_writer.py`, `workbook_verification.py` and `INDIA_template.xlsx` from `pre-shipment-backup.zip`; restart. No database restoration or migration is required for this presentation rollback.

Additional unseen India PDF validation remains pending, and India/Jordan automatic watching remains disabled. This does not advance the regional rollout stage.
