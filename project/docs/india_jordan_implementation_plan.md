# India and Jordan implementation plan

Planning checkpoint: 23 October 2026. Stages 1–3, [Stage 4A source extraction](india_jordan_stage4.md) and [Stage 4B India valuation](india_jordan_stage4b.md) are complete. India Fixes 1–7 now preserve source prices/amounts, guard currency, recover the sample invoice number from the PDF even under neutral/conflicting filenames, tolerate equivalent date/mark/airport layouts with bounded source readings, retain supported goods context across adjacent tables/pages, verify mapped printed headers before publication, and preserve explicit HS codes through supported continuations. Fix 8 handwriting review retains the printed FABRIC CUTTINGS fallback after three fresh unsuccessful local-reader comparisons; production code is unchanged. Fix 9 confirms existing safe caching eliminates repeat inference; warm sample attempts took 2.2–3.4 seconds with no production code change. The latest full gate remains 421 passing regressions; all 20 Bangladesh parser and valuation results are unchanged. India uses its approved three category rates with cent totals. Jordan layout (Stage 5), Jordan extraction/valuation, regional editing and regional watching remain separate review gates. Obtain approval before starting the next stage.

## Recommended approach

Before beginning the Jordan stage, follow the [India fix checklist](india_fix_checklist.md). It records the post-Stage-4B audit findings, production integration work and final release acceptance. Its final item is Stage 5, subject to user approval; completed implementation stages do not imply that India production readiness has been established.

Extend the existing local pipeline. Keep one launcher, one dashboard, one SQLite job store, one scanner coordinator and one extraction worker. Reuse PaddleOCR, orientation correction, ruled-table recovery, selective Ollama transcription, source snapshots, caches, evidence images, publication/retry and the existing preview/download controls.

Use a small explicit country mapping for Bangladesh, India and Jordan. Do not build another framework or separate applications. Bind the production country to the watched folder and retain it on the job. Check explicit PDF destination information for contradictions; do not silently use a Bangladesh layout for an unsupported or mismatched destination.

Implement India first because its invoice is closest to the Bangladesh layout. Then implement Jordan, which adds per-item weights, origin handling and a longer goods area. Neither country is enabled in the production watcher until its isolated gates pass.

## What was inspected

- Production entry points and country-dependent parts of the parser, pipeline, writer, valuation, queue verification, state/configuration, settings, reset, editing and dashboard.
- All nonempty cells, formulas, merged ranges and print areas in the three existing master workbooks and all five India/Jordan manual reference workbooks.
- PDF structure for all five regional examples: 31 scanned pages, each with an image and no extractable text layer.
- Nine rendered pages: the five first shipment pages, both India packing pages, Jordan 5172's label page and Jordan 5197's final garment page.
- Existing tests and comparison tooling for country-specific coverage. No current full-page OCR cache for these five examples was found under the current source/settings key.

Inventory and formula analysis are retained under `reports/india_jordan_plan_20261022/`. This review did not run fresh OCR/model inference, create production invoices, alter masters, update settings, clear data or stop services. It establishes an implementation plan, not a measured new-country accuracy score.

| Country | Available PDF/reference pairs | PDF pages | Reference goods rows |
|---|---|---:|---|
| India | 26S5196 | 3 | 3 invoice items; one description continues onto another row |
| Jordan | 26S5147, 26S5172, 26S5173, 26S5197 | 10 + 2 + 8 + 8 = 28 | 15, 1, 8 and 17 |

These examples are development fixtures. Production must never read `expected_outputs` or require those workbooks to be present. One India example cannot establish reliability for unseen India shipments.

## Diagnosis of the current code

| Finding | Concrete consequence | Smallest appropriate change |
|---|---|---|
| `pipeline._resolve_template` and the consignee directory already know all three countries, but the worker and batch command explicitly supply the BD master | A recognized India/Jordan consignee can still be printed in the BD layout | Pass one explicit region through supported entry points, job metadata, extraction, writing and verification |
| `QueueWorker._verify_workbook` reads BD's row 33 goods area, G/H quantity/unit and F-column total label | A correctly laid out India/Jordan invoice cannot pass the current publication check | Verify against the selected region's actual goods columns and total anchor |
| `attempt_metadata` always fingerprints `BD_template.xlsx`; manual re-rendering also supplies the BD master | Wrong template provenance, and editing can use the wrong layout | Record and reuse the actual selected country/template; keep old attempt metadata readable |
| Configuration contains one incoming/output pair; creating India/Jordan directories does not watch them | Reserved folders are not functioning regional queues | Add enabled regional folder pairs to the existing coordinator, keeping one worker and existing BD settings compatible |
| Runtime folder protection names `expected_output`, but the actual fixture folder is `expected_outputs`; a read-only validation check accepts that folder as output | A user can accidentally select the manual-reference directory for generated files or later clearing | Protect the actual plural path (and retain the legacy alias) before extending folder settings; test that neither can be selected |
| India writer truncates items to six; Jordan truncates to fifteen | A seventh India item is lost; Jordan 5197's 17-row reference already exceeds capacity | Grow the goods area before totals/footer, preserve styles and print all extracted items |
| Jordan blank contains duplicate country, package/weight, goods-header, total and disclaimer sections | Legacy labels can appear among goods, and unrelated headings remain on the invoice | Clean the shared Jordan master once; do not patch each output |
| Jordan writer writes total at row 50, outside the blank's A1:J48 print area | Total may be absent from the printed invoice | Move total/footer dynamically and update print area and repeated table headers |
| India blank has no explicit print area; both regional writers write dates as strings and lack BD's layout safeguards | Inconsistent printing, clipping and date behavior | Use typed dates, controlled wrapping/heights and regional print settings |
| Models have `hs_code`, `weight_kg`, `port_of_discharge` and `shipment_terms`, but the parser does not populate all these regional fields and writers ignore the last two | Existing model properties do not constitute end-to-end support | Add only the missing parsing and mapping to the existing data model |
| Origin is not represented; the current region-specific unresolved logic requests net weight for every non-BD invoice | Jordan origin cannot be handled correctly; missing net weight is reported even though these references do not print it | Add source-backed origin where needed and define applicable fields per template; do not require a nonexistent net-weight field |
| `apply_valuation` deliberately skips India/Jordan | Quantities can be extracted but values remain unpriced | Keep BD rates untouched; introduce separately approved country/category/unit rates |
| Original finding: `edited_data` rejected non-BD invoices; no regional goods controls | India editing addressed by [Fix 11](india_fix11_manual_editing.md); Jordan/per-item weight/origin controls remain future work | Reuse regional editing while preserving country, HS, weight and provenance |
| Existing regional tests mainly ensure BD valuation is not applied to other regions | No positive coverage for regional printing or publication | Add a small regression set for each new boundary and source case |

Do not weaken `_verify_workbook` to get regional invoices published. It must still independently check the printed goods, complete page coverage and source identity.

## Country-specific field contracts

### India

Preserve the reference structure: shipper, export date, consignee/address, IEC/PAN and GST identifiers, shipping marks, carton references, destination, invoice number, packages/G.W., HS code, goods quantity/unit, amount and the three trade-sample declarations. Include port of discharge, shipment terms and an on/about date only when sourced or covered by an expressly approved standing rule.

| Area | Current reference/template anchors | Planned handling |
|---|---|---|
| Header | C9 date; B11 consignee; B12 onward address/identifiers | Extract the labelled consignee block; exclude contact/notify-party duplication; preserve identifiers as text |
| Shipping | H11 marks; H12 destination; I13 cartons | Preserve TGPLFOCTS or the actual supplied mark; do not rewrite all new marks into BD's hyphenated pattern |
| Extra shipment fields | Reference A17/A18 route/on-about, A22 port, A23 terms | Separate shipping route, export date, packing date and Incoterm; never infer CPT from “Freight Prepaid” alone |
| Summary | C25 invoice; B27 packages; G27 gross kg | Prefer the explicit shipment declaration; retain its source |
| Goods | Start row 33; A cartons, B description, E HS, F quantity, G unit, I amount | Preserve the description continuation, printed HS and matching quantity. Expand beyond six rows safely |
| Footer | Total currently I42; declarations A47:A49 | Move consistently with the goods area; avoid duplicate generic disclaimers |

Observed PDF facts: the cover declares seven packages and EST. 106 kg. The fabric packing page provides HS 55132900, six 63-yard entries and a composition/width; the final page contains zipper lengths and three sample-set entries with handwritten annotation. These are suitable tests for existing rotation/table/grouping logic.

Important differences to resolve against PDF evidence:

- Stage 4 close-up verification corrects the initial low-resolution reading: the fabric page says 10/13/2026, matching 13-Oct-26 on the next page. The manual export date is 14-Oct-2026; no next-day adjustment is supported by the PDF. The user approved the latest labelled packing date when no export date exists, with all candidates retained in evidence. Bangladesh's first-date policy remains unchanged.
- Fabric width is printed with an inch mark; the manual description uses a centimetre label. Preserve the source unit; do not copy a conflicting reference unit.
- CPT and the manual on/about date are not established by the inspected cover/packing declarations. Leave unsupported fields blank under the existing PDF-first instruction unless a standing business rule is later approved.
- The manual amount is USD 82.40 using visible reference rates. Those rates are valuation assumptions, not extracted PDF facts. Stage 4B approval establishes India cent totals and rates 0.20/YDS fabric, 0.10/PCS zipper and 0.10/SETS fabric swatches/samples/cuttings. BD whole-dollar totals remain unchanged.

### Jordan

Preserve the distinct Jordan structure: header with EJU1-style marks/carton references, consignee/address, invoice/date, packages/G.W., goods with a KGS column, quantity/unit/value, and the origin/sample-purpose footer. Unit-price helper cells may remain outside the printed A:J area, matching the reference design.

| Area | Current reference anchors | Planned handling |
|---|---|---|
| Header | C9 date; I9 marks; I10 destination; J11 cartons; C11 onward consignee/address | Extract from the correct header blocks; keep the actual recipient and marks |
| Summary | D16 country; C18 invoice; B21 packages; F21 gross kg | Clean incorrect duplicate headings in the blank, then use explicit declarations |
| Goods | Start row 27; A cartons, B description, F kg, G quantity, H unit, I value | Grow safely to 17+ rows; preserve garment type, material, quantity and weight-source relationships |
| Pricing | K rate and L currency helper columns in references | Calculate against each row's own rate; never copy mislinked formulas |
| Footer | Dynamic total in H/I and origin/sample statements below | Keep totals/footer inside print area and avoid copying a default origin |

Cover declarations provide the following source controls: 5147 = 9 packages/120 kg; 5172 = 3/48 kg; 5173 = 6/102 kg; 5197 = 6/71 kg. These should be preferred to an inferred packing-weight sum when legible.

Important differences and limits:

- 5172's packing page is dated 6-Oct-2026 while the reference export date is 7-Oct-2026. Reuse the approved PDF packing-date fallback when no export date exists; a different manual export date is not evidence for adding one day.
- 5172's packing page says 106,400 care labels and 45 kg, while the shipment declaration is 48 kg. The manual goods row uses 48 kg. A packing-item weight is not automatically the shipment gross weight or net weight; retain 45 kg for that supported row and 48 kg for the declared shipment gross, without inventing a tare allocation.
- Shared weight cells may cover multiple rows. Count each physical cell once. Do not divide its weight across goods merely to make row weights equal header gross weight. If an individual row allocation is unsupported, leave that row's weight blank and retain the group evidence in the dashboard.
- 5197's final garment page explicitly shows Vietnam for garment entries, while the manual footer says China. A source-backed origin policy is necessary. Mixed or partly unspecified origins must not become an unsupported shipment-wide China declaration.
- That garment page distinguishes sweatpants/sweatshirts and tops/pants. The manual reference consolidates these differently. Preserve real garment types rather than forcing its two garment rows; a correct PDF-based invoice may have more reference-independent rows.
- 5147 contains eight formulas referring to another row's K rate; seven reference a different numeric rate. Its saved/formula total is USD 26.07, while applying every displayed row's own rate gives USD 22.91. This is a reference formula inconsistency, not an extraction target.
- 5197 also has cross-row rate references, although the referenced numeric rates currently match. Repair the formula pattern in the future master/writer rather than relying on those coincidences.
- Label rates vary substantially across the references (including 0.001, 0.01 and 0.02 per piece). Four examples do not establish a universal label rate. Approve a category/unit policy; do not encode shipment IDs or invent quantity tiers to reproduce these totals.

## Source and business-rule policy

1. Prefer explicit PDF declarations and readable corrected values. Preserve page/region/cell evidence and the actual method used.
2. Use the existing local model only for unresolved source reading, with retained exact input images and current configurable generation limits. Do not ask it to invent HS classifications, rates, origin, missing weights or shipment terms.
3. Keep sample references exclusively in development QA. Compare differences as: extraction error, formatting error, approved business-rule difference, reference inconsistency or source information unavailable.
4. Keep unknown fields empty on professional invoices. Diagnostics remain in the dashboard/audit; no “validation required” text or mandatory approval is added to invoices.
5. Preserve units: gross-count buttons are not grams; cones are not pieces; printed length/weight units do not change through description cleanup.
6. Prefer existing model fields. Add explicit origin fields only where required to preserve supported per-item/shipment origin, and add structured identifiers only where rendering/editing needs them. Do not build a universal tax-document model.
7. Keep the current BD rate file and rounding behavior unchanged. Add small regional rate files/policies using the same valuation helper and Decimal calculations. Rates, applicable categories and total rounding need approval before that country's valuation is enabled. Proposed default for India/Jordan is two-decimal USD totals, matching their references; this is not yet an approved replacement for the BD rule.

## Eight implementation stages

| Stage | Deliverable | Acceptance before continuing |
|---|---|---|
| 1 — Freeze baseline and field contracts | Snapshot the working BD build/settings/templates/data consistently; create a PDF-grounded field/row checklist for the five new examples and identify source/reference disagreements | Recoverable baseline; existing suite passes; every required field has a source/rule/unavailable classification; no live regional jobs started |
| 2 — Country-aware core | Add validated explicit region selection through CLI/pipeline/job metadata, actual template selection/fingerprints and regional verification. Migrate retained jobs as BD without relocating their files. Correct reference-folder protection. Production watcher remains BD-only | Existing CLI/settings/state remain compatible; BD outputs retain their facts/styles; reference folders cannot be selected as output; invalid/mismatched region cannot silently publish as BD; retry and historical download keep the recorded region |
| 3 — India master and writer | Clean the India master once; map correct columns; typed dates; growing descriptions/goods; total/declarations/print settings; verify printed data using the same regional layout definition | Synthetic 0/1/7/40-item and long-description cases do not truncate or collide; HS remains a text identifier; totals/footer print; no stale values; BD writer unchanged |
| 4 — India extraction and values | Reuse OCR/table parsing; add printed HS, IEC/PAN/GST, width/unit and regional grouping; implement agreed date/source/valuation rules | All three PDF pages accounted for; fabric quantities, zipper total and three sets checked against PDF; unsupported terms/date assumptions remain empty or explicitly approved; no reference files in runtime |
| 5 — Jordan master and writer | Remove duplicate sections; retain distinct KG/quantity/value layout; expand detail area; origin/footer slots; safe row-specific value calculation and print area | Synthetic 0/1/15/17/40-item and multi-page cases pass; no row loss or inherited BD headings; helper prices do not accidentally print; BD and India checks unchanged |
| 6 — Jordan extraction and values | Reuse header/packing parsing; support row/shared weights, garment distinctions and source origin; add approved regional valuation categories | All 28 source pages accounted for; four declaration controls checked; no duplicated weight cells or forced weight allocation; formula/reference differences documented; source rows not forced into reference summaries |
| 7 — Integrate the shared production system | Add per-country enabled incoming/output pairs, persist region at intake, scan enabled folders with one worker, extend existing settings/filter/detail/edit/preview/API/Postman and reset/recovery behavior | Mixed-country queue routes correctly; same basename across countries is safe; old settings and jobs still work; all regional fields survive edits; reset/save/retry/restart retains correct paths/region; BD-only default remains available |
| 8 — Acceptance and controlled activation | Run the full mixed regression and PDF-grounded comparison in isolation; activate India and Jordan separately after approval | Full page/row/value/style checks; fresh OCR and selective-VL cases; unseen/renamed inputs; locked-file/restart/model-unavailable recovery; baseline BD unchanged; operating/build/rollback docs current |

Stage 7 must be delivered as three separately reviewable updates: (7a) folder configuration/intake/durable routing; (7b) dashboard, country-specific editing and API documentation; (7c) Clear data, save/retry and mixed-country recovery checks. Stop for approval between these updates too.

For extraction stages 4 and 6, first finish source fields/quantities, then valuation as a separate reviewed change. Do not mix pricing corrections with OCR changes in the same patch.

## Minimal integration design

```text
incoming/bangladesh -> queued job: BD     -> BD master     -> output/bangladesh
incoming/india      -> queued job: INDIA  -> India master  -> output/india
incoming/jordan     -> queued job: JORDAN -> Jordan master -> output/jordan
                              |
                    same existing worker
                    same evidence and dashboard
```

- Keep a three-entry mapping for template path, writer/verification coordinates, applicable fields and valuation policy. Avoid auto-discovering arbitrary templates or dynamic plugin loading.
- Reuse `FOCData`/`LineItem`; do not create three parallel versions of the parser or three databases/services.
- Add an additive job-region migration and retain immutable attempt configuration/template evidence. Preserve source-identity/content deduplication inside each region's non-overlapping watched folder. Deliberately reassigning a folder to another country must not reinterpret existing jobs or reuse incompatible intake observations.
- Keep state and artifact directories fixed, as they are now. Extend runtime settings compatibly for regional folder pairs/enabled countries; keep the existing seven settings and existing API callers readable. Global model/scan/vision limits remain global initially.
- Folder settings changes apply only between operations. Previously queued snapshots and completed downloads retain their recorded paths, even after an output folder change.
- Preserve single-worker locking and current long vision allowances. Multi-country support is routing, not a reason to start multiple GPU workers or replace SQLite.
- Reuse existing manual editing and preview. Add applicable HS/identifier/origin/weight fields without clearing unsupported fields during an unrelated edit. Do not apply BD's whole-dollar rounding to new countries by accident.
- Clear data must archive all affected enabled regional output/evidence consistently and rediscover each enabled inbox once, retaining its region. Keep confirmation/idempotency, busy-operation refusal, rollback and alternate-volume archive behavior. A region-only reset is optional future scope, not required for first integration.

## QA and release rules

- Use the existing BD result as a preservation baseline, including source-supported fields, goods quantities, valuation, template styles, download names, evidence and editing/reset behavior. Byte-for-byte XLSX equality is not the only comparison because generated document metadata can change.
- Check the printed worksheet independently of the JSON/audit; verify all source pages and items, not just a successful file save. Compare quantity totals separately for each unit. Compare identifier strings exactly, preserving leading zeros.
- Inspect each new country's rendering, print area, wrapping, growth, total/footer placement, red highlighting and professional appearance. Matching a manual workbook's unsupported value or faulty formula is not a success criterion.
- Add focused tests at risky boundaries: region routing/migration, row overflow, table-column interpretation, shared weights, origin, calculation/rounding, editing preservation and mixed-country recovery. Reuse the existing test harness and comparison tool.
- Run new-country tests in isolated state/output/cache namespaces; do not clear or repurpose the current main queue during development. Warm-cache and fresh-inference results are recorded separately.
- Before live activation, remove/deny access to manual-reference folders in the test deployment and prove conversion still works. References are never a production dependency.
- Preserve a versioned rollback bundle and matching database/artifact/output backup. Enable one new country at a time. A failed gate is fixed before moving on; it does not justify relaxing publication checks.
- The earlier production pipeline's final Stage 8/reboot acceptance remains outstanding and is not completed by this regional plan. Any sign-out/reboot still needs separate coordination.

## Decisions to settle at the appropriate stage

1. India date rule is settled: use an explicit export date first, otherwise the latest labelled packing date. Stage 4 confirms both sample packing dates are actually 13-Oct-2026; the earlier 2025 reading was an analysis error, not a source conflict.
2. India: whether CPT/on-about fields have a standing source outside these PDFs. Without one, they stay blank.
3. India rates/cent rounding are approved and implemented in Stage 4B. Jordan rates and rounding still need approval; label subtypes/rates need particular attention.
4. Jordan: agree presentation for mixed/partial origin and unallocated shared weights. Default is source-supported values only; unsupported individual weights/origin declarations stay blank.
5. Jordan 5173 page 6 names the India consignee despite the Jordan cover. Resolve this page's inclusion explicitly before extraction activation. Do not silently discard it or reroute the entire shipment. Stage 1 also confirms mixed/partial origins in 5147 (China/Bangladesh) and 5197 (China/HK/Vietnam), and sample-card quantities distinct from their contents.

No extra dependency, paid cloud service, OCR/model replacement, second web app, external queue, multi-worker execution or specimen-specific correction is proposed. Fresh regional accuracy, all-page visual QA and unseen-document reliability remain to be measured during the gated implementation.






