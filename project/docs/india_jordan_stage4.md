# India / Jordan Stage 4A: India source extraction

Historical source-only checkpoint. [Stage 4B](india_jordan_stage4b.md) subsequently adds the approved India valuation; the unpriced results below describe Stage 4A.

Accepted in isolation on 22 October 2026. This stage implements India source extraction only. India valuation remains Stage 4B; Jordan, regional editing and regional automatic watching are not enabled. No dependency, HTTP route, schema or production model-setting change was required.

## Source facts and manual-reference differences

The three-page India PDF 26S5196 was freshly OCRed, processed through the real queue worker and published into an isolated output folder. Conversion was guarded against opening manual reference files; no such access occurred. References were used only for subsequent QA.

| Field | Result and basis |
|---|---|
| Date | 13-Oct-2026, latest labelled packing date when no export date exists, as approved. Both packing pages actually say 2026; the earlier planning read of 2025 was incorrect. The reference's 14-Oct date is unsupported by this PDF. |
| Consignee | Source TRIMETRO GARMENTS INDIA PVT LTD and address; contact/email excluded |
| IEC/PAN; GST | AAJCT7390N; 21AAJCT7390N1ZS, from PDF, preserved as text |
| Shipping marks | Cover TGPLFOCTS; no directory substitution |
| Destination/cartons/packages | CHENNAI, INDIA; T01–T07; 7 packages |
| Gross weight | Explicit estimated 106 kg retained. Packing weights total 105 kg; no forced adjustment. |
| Fabric | 378 YDS; source composition; WIDTH 53 INCHES; HS 55132900 |
| Zipper | 65 PCS, grouping source color/length quantities 5 + 35 + 5 + 15 + 5 |
| Third goods group | Printed FABRIC CUTTINGS, 3 SETS; handwriting not reliably resolved |
| Prices and total | Empty: India valuation is a separate update |
| Port, terms, absent identifiers | Empty unless explicitly sourced; airport is not treated as a discharge port; freight prepaid does not imply CPT |

All three true reference goods quantity/unit groups match after normalizing SET/SETS. One reference description continues onto the next Excel row: counting that continuation as a fourth item gives a misleading accuracy score. The fabric width uses PDF inches rather than the reference's centimetres. Goods/date differences are retained when the source supports them. This single PDF does not establish production-wide accuracy.

The invoice number still uses the existing recognizable-filename fallback S/5196/26. A renamed-source check preserves all other measured facts but leaves the invoice number empty: handwritten invoice-number extraction remains a limitation.

## Handwriting benchmark

The ambiguous note was tested with actual installed local models, using saved crop/response evidence:

| Model/crop | Time | Returned reading | Outcome |
|---|---:|---|---|
| qwen3-vl:latest, whole cell | 252.89 s | FAB SMART ONES / FABSMARTONES | Rejected |
| qwen3-vl:latest, tight word crop at 2× | 241.453 s | FAB SMARTONES | Rejected |
| qwen3.5:4b, same tight crop | 30.437 s | FAB SMATONES | Rejected |

None reliably established FAB SWATCHES. The generated invoice retains the readable printed FABRIC CUTTINGS instead of forcing a reference answer. The alternative model was a private QA comparison, not a production setting change or automatic model cascade. Better hardware may improve speed or permit larger models; it does not guarantee a correct reading.

## Implementation and checks

A small India module handles source-only header/date rules, bounded heading/color continuation, printed HS/width and selective annotation crops. The parser and pipeline reuse existing table extraction, aggregation, vision transport and evidence. India quantity formatting now prints whole numbers without a trailing decimal point. Original OCR text and annotation evidence are retained. Bangladesh directory/date/grouping behavior and both other country writer functions remain unchanged.

- 318 regression tests passed in 68.036 seconds; dashboard JavaScript checks passed.
- All 20 Bangladesh parser results, including diagnostics, match their baseline exactly.
- All 20 retained Bangladesh invoices re-rendered in isolation with identical visible values, styles, dimensions and print settings.
- Real QueueWorker acceptance completed source extraction, region/template verification, publication and ready receipt without reading references.
- Final native Excel export is one page; source identifiers, HS, width, quantities and declarations verified. Final page visually inspected.
- All three master workbooks, current production outputs, input snapshots, evidence and frontend are unchanged. No production invoices were reprocessed.

## Evidence and rollback

Development evidence is under reports/india_jordan_stage4_20261022 and excluded from production bundles. acceptance.log is the final 318-test gate; worker-acceptance.json and worker-acceptance-run contain the final queue result; accepted-print contains its final native PDF/page; bd-preservation.json and bd-parser-before/after.json record Bangladesh comparisons. india-reference-comparison.json records the corrected three-row comparison. verification.json records final service/history/hash and release checks.

The pre-stage4-backup.zip contains a verified matching stopped schema-6 state, source snapshots, artifacts, outputs, masters and backend/frontend. The previous foc-invoice-india-layout-20261022.zip supplies the matching application release. Stop/drain before restoring matching code/data together; never overwrite a live SQLite database. A destructive restore and physical reboot were not performed.

## Next review gate

Approve Stage 4B before adding India valuation. Decide category/unit rates and rounding separately; do not copy the manual invoice amounts or use expected workbooks at runtime. Jordan source/layout implementation and enabling regional inboxes remain later stages.
