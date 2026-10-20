# Shared PDF-to-invoice processing flow

Scope: new shipment PDFs using the supported packing-list structure and the existing BD invoice template. This is a shared source-grounded process, not a claim to understand every PDF layout or unreadable scan. BD estimates use the approved approximate USD rates.

```mermaid
flowchart TD
    A[Shipment PDF] --> B[Read all pages: local PaddleOCR and source-keyed cache]
    B --> C[Orient pages and retain words, confidence and coordinates]
    C --> D[Recover table boundaries: retry slight slopes and partial-width body rows]
    D --> E[Identify description, ITEM, QTY, weight and package columns]
    E --> F[Read source rows and pair each product with its quantity and unit]
    F --> G[Restore supported continuations and split entries]
    G --> H[Normalize product names and group only compatible items]
    H --> I[Apply supported date, consignee, carton and weight rules]
    I --> V[Apply approved product and unit rates; round complete total to whole USD]
    V --> J[Fill existing invoice template; unsupported fields stay empty]
    J --> K[Save workbook atomically and record batch result]
    K --> L[Development QA: source checks, comparison and native print review]
    D --> M[No established table bounds]
    M --> N[Keep unresolved goods out of unrestricted OCR fallback]
    N --> J
```

## Ownership of facts

- The PDF supplies shipment facts. An identified company may use the existing maintained address/BIN directory when the PDF lacks them. A company profile must not supply another factory's details.
- OCR preserves coordinates. Physical tables and labelled columns take priority over whole-page text. Slightly sloping ruled lines and body rules spanning only the right part of the table are retried only when ordinary horizontal-boundary recovery fails.
- If QTY and WEIGHT labels are joined, the neighboring column must actually contain recognizable quantity/unit entries before it is accepted as QTY. Kilogram weights are not goods quantities.
- Product/quantity pairs split across ITEM and QTY must have source corroboration. Per-item weight factors and style numbers are not promoted to goods quantities.
- Percentage fragments may join when they establish a complete valid blend without crossing a sender/quantity boundary. Wrapped sender fragments and a later fabric classification can refine the current material group.
- Construction/shrinkage tokens such as 3x3% are distinguished from fiber percentages. A declared STRETCH component is retained literally; it is not silently replaced with a guessed fiber. Different compositions and units remain separate.
- Existing aggregation groups normalized description, unit, HS code and unit price; source row references are retained. Quantity totals must be checked against source rows when grouping changes.

## Conservative behavior

- When OCR words exist but no table bounds are established, unrestricted page text is not used to create goods. A blank is preferable to a footer total, packaging count or staff note presented as an item.
- Existing fallback for bounded unparsed regions remains in the code and is not a universal guarantee of correct classification. Unseen layouts still require evaluation.
- Source-context FAB/FAP/FAR annotations can establish a broad FABRIC SAMPLES category, preserving source units rather than claiming an unreadable subtype. A unique WOVEN/KNIT merged-column value can refine earlier material rows.
- Unnamed columns introduced by pictures are included only when their table headers are blank. Numbered garments split only when independently read inline quantities agree with the declared total. A complete matching garment annotation immediately below the final row is bounded to its description span and cannot create an extra item.
- Integer quantities of explicitly named countable cards can infer PCS; this is recorded internally as context inference, not literal source text. Other unreadable quantity/unit fields remain unresolved. Invoice identifiers now use the approved best-effort policy: PDF/filename exact agreement, otherwise most frequent PDF reading (first on ties), with close-filename correction for a single reading and filename fallback when no PDF number exists. No recognized number in either source still leaves a blank. Selection is internally recorded; misleading or removed filename support can affect the result, so renamed/unseen production files still need acceptance testing.
- A printed garment title can be used even if a handwritten composition cannot be established. Fiber-adjacent OCR glyph repairs and matching garment notes are retained with diagnostics; when a percentage remains unreadable, a supported cotton-fabric description can be used without inventing that percentage. No expected-workbook value may fill that gap.
- Dates follow explicit export/shipment dates first, then the approved first dated packing-page rule. ON/ABT dates are not invented from a packing date.
- Gross weight uses an explicit declaration first, otherwise the approved complete corrected packing-weight sum, counting shared cells once with no arbitrary allowance/rounding. Unreadable corrections leave the total blank. Explicit net greater than known gross leaves net blank.
- Package totals use an explicit shipment total first, then established carton ranges; otherwise count distinct explicit carton IDs or sum PDF package entries across all pages. Shared physical cells and repeated OCR of the same cell count once. Equal counts on different pages are separate unless an explicit carton ID repeats. Packs, cartons, boxes, rolls and bags are containers under this rule; this does not establish consolidated outer cartons. Unreadable declared counts leave the total empty. Gross weight and page count never establish a package count. Source-keyed package evidence is cached under `.cache/ocr/packages`.
- Shipment-specific commercial notes cannot be derived from examples. Missing commercial inputs stay empty.
- BD valuation reads the approved rates in `valuation_rates.json`. Match both product and unit; never replace source quantities with example quantities. Only the six confirmed small-button categories interpret G as GROSS. Unsupported products/units remain unpriced. Existing declared source values take priority.
- General sample-piece and garment rates may price a broad category while its exact description remains unresolved. Specific category rates take priority; fabric-sample/handloom context takes priority over garment words in booking text. Missing source units remain missing. Rates are nominal assumptions calibrated against development references, never shipment-ID rules. The revised common mould rate is USD 0.72/set; see the [expanded valuation report](../reports/valuation_expanded_20261019/RESULTS.md).
- Multiply with Decimal, round each line to cents, then round the sum to whole USD (half up). Populate an estimated shipment total only when every extracted row is priced and all known PDF pages were processed. This does not prove every source row was extracted. Unit rates and line amounts use the existing Extracted_Items sheet; the invoice retains its total-only layout.

## Production and evaluation are separate

Production conversion reads PDFs, the blank template, maintained company information, approved valuation rates and optional source-keyed OCR/model caches. It never reads expected_outputs or QA reports. The manual workbooks are evaluated only by the comparison tool after generation, and source-correct differences must be recorded rather than forced to match.

The current writer still includes internal audit/item sheets in the workbook. Professional customer-only export, remaining print clipping/continuation identity, and applicable company notes are unfinished work; this document does not mark them complete.

## Acceptance before calling this production-ready

1. Keep previous source-supported dates, addresses/BINs, identifiers, cartons and weights stable when repairing goods.
2. Check table quantities against source pages; detect duplicate source ownership and cross-unit mistakes.
3. Inspect actual Excel print output, including continuation pages and missing-field handling.
4. Measure new unseen PDFs and renamed inputs, including fresh OCR, not only cached development examples.
5. Keep unsupported annotations, carton consolidations and commercial details empty until a general source-supported rule works.

Current measured results and unresolved work are linked from [the repair checklist](../reports/carton_fix_20261019/CHECKLIST.md). Unit tests and page coverage support engineering reliability; they do not establish unseen-document accuracy.

Latest source evidence and remaining reference differences: [PDF-priority verification](../reports/pdf_priority_20261019/RESULTS.md). All 20 totals now populate; this does not establish full invoice or unseen-file accuracy.

Invoice-number policy was relaxed on 20 October 2026 at the user's request: [results and decision rules](../reports/invoice_number_fix_20261020/RESULTS.md). Both prior blanks are filled; 18/18 paired numbers match and 109 tests pass. This is development-set evidence, not a production accuracy guarantee.

Package counting updated 20 October 2026: [results and per-page evidence](../reports/package_count_fix_20261020/RESULTS.md). Four missing totals filled; 19/20 package counts present, with 5188 blocked by a handwritten number. All 121 tests pass; existing goods and other invoice fields are unchanged.

## Integrated local vision

Single-file and batch conversion default to the installed Qwen3-VL model; `--no-local-vision` selects the original OCR-only path. The local model is a bounded fallback for uncertain quantity strings, missing numbers beside known package units, and ambiguous packing-list weight pages. It is not used to invent unsupported shipment facts or prices.

All cells on an ambiguous weight page are checked as distinct physical cells, with the PDF KG header supplied. This preserves the cancellation context and avoids retaining a cancelled printed number that OCR happened to read cleanly. A continuous blue brace may group the initial OCR region; vision recovery follows the physical row rules and still counts physically merged cells once. Only a completed positive finite numeric answer can contribute to a complete weight sum. Explicit gross declarations keep priority.

Goods quantities keep their existing legible units and integer counts; partial/completed quantity-unit readings are checked against source units. Package vision cannot change a legible roll/bag/package kind. No validation or human-intervention wording is added to invoices. Model errors leave unresolved data empty while retaining supported OCR fields.

One shared local transport caches completed structured results by crop, prompt, schema, settings and installed model digest. Weight and package evidence retain source coordinates and model provenance. Historical OCR caches stay separate from vision evidence, and an OCR-only control run must preserve the established outputs.

The generation allowance is 4,096 tokens / 8,192 context, with a two-hour HTTP timeout. Qwen may still generate reasoning despite think=false; only the final structured answer is accepted. Hardware upgrades can address throughput; unseen accuracy and correction-trigger coverage still need evaluation. A correction entirely missed by ordinary OCR may not trigger this fallback.

Latest [production integration QA](../reports/local_vision_integration_20261020/RESULTS.md). The earlier [five-cell capability benchmark](../reports/weight_vision_4096_20261020/RESULTS.md) established that isolated cells plus their KG headers can produce correct final numbers without shipment-specific rules. Production conversion never reads these reports or manual expected invoices.
