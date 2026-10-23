# India reference comparison and shared goods-table update

23 October 2026. Additional unseen India PDFs are unavailable, so India checklist Fix 10 remains pending. This update compares the existing sample with the manual reference and improves Bangladesh/India goods presentation. It does not change extraction, valuation, model settings, routing, editing or regional activation.

Follow-up: the [India shipment section](india_shipment_section.md) now keeps the route/departure/port/terms labels visible, with existing destination/port/terms data where available. The comparison below records the earlier layout; the unsupported facts remain blank under the same PDF-only policy.

Bangladesh total follow-up (23 October): removed the grey fill and top/double-bottom rules from master cells F40:I40 to match India's clean total presentation. The bold label, bold red USD amount, numeric value/format, alignment and merged amount area are unchanged. The existing writer already carries the master style through expanded goods rows, so no production Python change was necessary. Checks and isolated previews are retained in `reports/bd_total_style_20261023/`; historical publications are preserved and future invoices inherit the master change.

## India: what is present and what differs

The comparison reads the entire first sheet of both workbooks, including cached formula results in the reference. Evidence: `reports/invoice_layout_20261023/india-reference-cells.json`. Expected invoices are used only by development QA, never by production conversion.

| Section | Generated result / comparison with manual reference |
|---|---|
| Shipper, address, phone/fax and document title | Present; same content, with merged presentation cells |
| Invoice number | S/5196/26; matches |
| Date | 13-Oct-2026 from the approved latest labelled packing-date rule; reference has 14-Oct. Preserve PDF value |
| Consignee and address | Present; matches apart from spacing |
| IEC/PAN and GST | AAJCT7390N and 21AAJCT7390N1ZS; present, matching and highlighted red |
| Shipping marks and destination | TGPLFOCTS and CHENNAI, INDIA; present and matching |
| Carton references | T01-T07 in the shipping block and goods table; present and matching. Reference uses a formula link; generated value is literal |
| Destination country | INDIA; present and matching |
| Shipment route sentence | Not printed in the India master. The PDF identifies air shipment and destination, but does not supply a labelled departure airport; the Hong Kong shipper address alone is not a verified flight origin. The reference's fixed route sentence is not introduced as a default |
| ON/ABT departure line | Blank; no supported departure date. Packing date is not automatically a departure date |
| Port of discharge | Blank; reference says CHENNAI, INDIA. A destination airport is not automatically a declared discharge port. User confirmed PDF-only values |
| Shipment terms | Blank; reference says CPT. Freight-prepaid text does not establish the CPT Incoterm. User confirmed PDF-only values |
| Packages / gross weight | 7 / 106 kg; both match. Explicit estimated gross is retained; no forced packing-weight reconciliation |
| Fabric | 378 YDS, HS 55132900, USD 75.60; matches. Composition is retained. PDF width is 53 inches; reference says 53 cm. Keep source unit |
| Zipper | 65 PCS, USD 6.50; matches, with normalized wording/case |
| Fabric cuttings | 3 SETS, USD 0.30; quantity/value match reference's “Fab Swatches”. Keep readable printed description. Unresolved handwritten subtype remains under Fix 8's documented fallback |
| Total | USD 82.40; equals reference's cached formula result. No valuation change |
| Declarations | All three trade-sample/customs declarations present once; one wrapped block rather than three separate rows |
| Net weight | Not printed; no supported source value or requirement introduced |
| Contact person, booking and freight instructions | PDF logistics details are not part of this reference invoice layout; their omission is not a missing expected invoice field |

No goods group, quantity, HS code, line amount or total is missing in this sample. This is a sample comparison, not a general accuracy percentage. Unsupported shipment information stays blank by the user's explicit instruction.

## Reusable layout change

Both masters and the existing openpyxl writer now use the same restrained light-grey header and thin table rules. Borders follow logical columns, not individual merged description cells. Text wraps and stays left aligned; quantities and India amounts align right, with units beside quantities. Existing red/blue highlights, identifiers, number formats and formulas/literal-text safety are preserved.

Bangladesh retains carton / description / quantity. India retains carton / description / HS / quantity / amount. India is wider because it carries two extra fields; its columns are not forced into Bangladesh's narrower layout. Totals and regional declarations retain their established positions and behavior. Blank reserved rows do not create miniature empty grid rows after populated goods. Table headings repeat on continuation pages; expanded rows inherit the style automatically.

This uses a formatted invoice table, not a filterable Excel data table: the established merged presentation cells are preserved. No new runtime dependency is introduced.

## Verification and deployment boundary

- Both updated masters preserve every populated cell value, type and number format.
- Twenty Bangladesh invoices and one India invoice re-rendered in isolated `reports/invoice_layout_20261023/review/` folders pass publication verification and preserve every sheet's populated cell values, data types and number formats against their previous outputs.
- Dedicated style checks cover 0, 1, 9 and 40 items in both regions, including dynamic growth, merged descriptions, red cartons, totals and repeated headings.
- Native Excel print checks cover both real review invoices and 40-item synthetic examples. Each real invoice is one page. Long synthetic descriptions occupy three pages; all goods, repeated headings, totals and declarations must remain readable.
- Full regression, preservation and build results are retained beside the review files. The service is stopped/drained and backed up before editing production code/masters, then restarted after verification.

Existing published invoices, attempts and source evidence are preserved. The new design applies automatically to newly generated invoices; review copies show how retained shipments look with it. This update does not rewrite historical downloads. India/Jordan automatic watching remains disabled.

Rollback: stop/drain the service and restore `src/foc_extractor/excel_writer.py` plus the two matching masters from `reports/invoice_layout_20261023/pre-layout-backup.zip`; restart afterward. No database migration is involved. Do not overwrite the live database for a style rollback.

Next: review these layouts, then continue the India checklist one task at a time. Unseen-PDF acceptance remains pending until additional source PDFs are available.
