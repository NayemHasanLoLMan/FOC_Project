# Readiness and remaining stages

Current organization checkpoint: 25 October 2026; available-sample acceptance completed 23 October 2026. Bangladesh and opt-in India use the same durable local pipeline, regional templates and one worker. Jordan automatic processing remains disabled. Manual references are QA-only and are never production inputs.

Bangladesh generalization checkpoint, 25 October 2026: seven newly tested PDFs exposed quantity/table, description, package/weight and header-reading gaps. Jordan J4 is paused while these are repaired. B1 is complete: Clear data recoverably clears derived OCR/vision/package/weight results, with isolated development caches and installed models preserved. B2 is complete: checked multiplication and position-backed merged rows recover 7 swatch sets in 5231, all 45 yards in 5233 and all 175 yards in 5234. A retained-OCR replay preserves all 20 original Bangladesh goods results; 501 regression tests passed. These checks isolate parsing behavior and do not claim fresh OCR/model accuracy. B3 is complete: compact ruled tables with separate shipped quantity/unit columns recover 2 shank and 6 rivet die-mould sets from 5231 pages 10–11. All source pages receive a recorded disposition, including unresolved quantities, unclassified pages and excluded pages. The 28-file retained-OCR/source-render replay changes only 5231 goods; 506 regression tests passed. B4 is complete: fiber modifiers and source measurement tolerances normalize without losing PCW/GRS wording; style metadata no longer breaks continuation headings; joined die-mould names, construction-first garments and explicit category notes use the shared parser. The existing bounded annotation reader now supports Bangladesh. The deterministic 28-file replay preserves quantity totals and all original 20 Bangladesh/one India goods results; 512 regression tests passed. Unusable model category readings remain rejected. B5 is implemented: packing controls include declarations above quantity rows and compact-form local totals; local gross labels no longer block the shipment sum. Explicit counts survive conflicting carton IDs, missing source-page coverage blocks partial totals, and vision-corrected weights require a separate literal reading. 5231 now provides 24 source packages/rolls and 36.6 kg; 5233 source readings corroborate 35 + 5 = 40 kg, without inserting an assumed decimal. All 521 tests passed and all 28 B4 goods results remain unchanged in replay. Further model disagreements remain visible rather than forced. B6 is implemented: Bangladesh reuses bounded header vision with source-reading agreement, and silent filename/company-directory header answers are removed. The source crop for 5236 corroborates S/5236/26; source packing recipient/category text stays literal and unsupported addresses/BINs stay blank. All 528 regression tests passed, and all 28 B5 goods results are unchanged in retained-OCR replay. B6 publication completed for all seven new invoices, including the long 5237 quantity attempt. B7 is implemented: ten missing category/unit valuations are covered by reused estimates and two explicit fastener fallback keys; singular/apostrophized garment names now retain garment rates. All 533 tests passed. Pricing replay changes only 5231 (21/23 rows priced, previously 11/23); all non-pricing fields and India prices are unchanged. Bangladesh pricing coverage is 128/131 rows, with the three remaining rows lacking an established quantity/unit; this is coverage, not an accuracy percentage. B8 is implemented: field-validated installed-reader recovery, terminal failure evidence and narrowly bounded corrected-quantity reading. All 546 regression tests passed; retained-source replay changes only 5237 to 200 YDS / USD 40, with all packing/header controls preserved. Two fresh quantity readings agreed in 30.5 seconds; this is a cell benchmark, not full-document throughput. Brief residency improved a repeated image but retained about 3.38 GB of model memory, so production keeps unloading after each call. B9 was subsequently attempted; see the current acceptance status below. Remaining reader failures and broader accuracy checks stay visible; full cold-document acceptance remains pending.

Current acceptance status, 26 October 2026: B9 remains open after a cold run exposed transient SQLite-lock restarts and a dropped recipient-column partial address/country. B9.1 adds bounded begin/commit retries without replaying writes; all 552 tests passed. An isolated managed cold invoice with fresh OCR/two fresh model responses survived a deliberate 6.5-second writer lock under up to 94% observed memory use, with stable scanner/worker PIDs and unchanged invoice facts. B9.2 now retains source recipient-column location/country without restoring directory defaults; all 560 tests passed and the 28-file parser comparison changes only 5075/5234 address/country fields, preserving goods and other parsed fields. B9.3 now replaces the fixed Bangladesh Hong Kong/Dhaka/air statement with a source-backed shipment destination; all 563 tests passed, and a 28-case writer replay changes only Bangladesh A18, preserving all other values/styles and India output. Origin/mode extraction is not added. Existing publications remain unchanged; new processing/reprocessing uses the new wording. The updated-package B9 rerun then exposed worker/dashboard SQL read failures during real model loading; the worker restarted and no cold invoice completed. B9.4 adds bounded execute retries to shared read scopes plus native WAL journaling after database validation, retaining transaction safety and requiring patched SQLite 3.51.3+ (this PC: 3.53.1). All 571 regression tests passed, including worker/dashboard contention, pending commits, WAL concurrency, read-only behavior, backup and runtime safety. The retry-only cold probe completed without a restart but had one status-monitor timeout and a stale scanner heartbeat; that evidence is preserved, and the WAL cold probe is separately recorded in reports/b9-4-read-contention. Full B9 acceptance, including sustained-load responsiveness, remains open. Full 27-PDF cold acceptance and independent renamed cold tests must still run from the updated package with fresh derived caches; Jordan J4 remains paused.

## Production pipeline checklist

- [x] Stage 1: configuration, durable job storage and safe initialization.
- [x] Stage 2: stable-file intake, immutable PDF snapshots and duplicate protection.
- [x] Stage 3: worker, safe publication, restart recovery and ownership locks.
- [x] Stage 4: processing evidence, exact model-input images and source-page review.
- [x] Stage 5: local dashboard, status, job details and verified downloads.
- [x] Stage 6: pause/resume, selected retry, save recovery and preserved reprocessing.
- [x] Stage 7: current-user Windows background startup and restart monitoring.
- [ ] Stage 8: coordinated Windows sign-out/reboot acceptance and final deployment rehearsal.

Dynamic settings, versioned editing, invoice preview, canonical download filenames and recoverable Clear data are implemented. Clear data remains exposed on the main local dashboard by the user's choice; review its availability before wider deployment.

## India checklist

- [x] Source prices/currency, PDF-first invoice number and variable-length serials.
- [x] Header/date/marks handling, goods continuations and source-backed HS continuation.
- [x] Printed-header verification before publication.
- [x] Handwriting and runtime reviews: retain readable printed fallback where handwriting cannot be established; reuse exact cached readings without lowering generous vision limits.
- [x] Regional editing, detail pages, valuation coverage review and separate folder processing.
- [x] Fix 15 available-sample release acceptance: 454 tests, dependency checks, 21 original invoices preserved, native Excel print review, real-PDF recovery checks and an extracted-package conversion without reference folders.
- [ ] Fix 10: additional unseen real India PDFs. Only one unique real India shipment is available; synthetic tests and cached runs do not establish future-document accuracy.

Accepted source/reference differences remain: packing date 13-Oct-2026, width 53 inches and declared estimated gross weight 106 kg. Unsupported CPT, discharge port and departure date are not copied from the manual reference. An unreadable handwritten subtype retains the printed FABRIC CUTTINGS description, 3 SETS.

## Jordan and final delivery plan

This checklist supersedes the earlier regional Stage 5-8 numbering. Jordan Stage J1-J8 below is separate from the completed production pipeline stages above. Finish and review one stage before starting the next; ask the user before advancing. Keep a single queue, worker, OCR/vision stack and web application. Do not enable Jordan while a required gate remains open.

### J1 - Source baseline and diagnosis - completed 25 October 2026

- [x] Inventory all four PDF/reference pairs: 5147 (10 pages), 5172 (2), 5173 (8), 5197 (8).
- [x] Record every page's QA concerns, source/reference fingerprints and supported cover controls in the existing development baseline.
- [x] Recheck scans, reference row counts and the master; record the unresolved India recipient on 5173 page 6.
- [x] Add a repeatable development-only readiness command and tests. It probes layout with synthetic rows, without invoking OCR/models, opening live job storage or writing production invoices.
- [x] Verify the defect: a 25-row probe writes only 15 rows; duplicate totals prevent publication verification. The blank master has duplicated destination, goods, total and declaration labels; its print area ends at row 48 while the legacy writer adds its total at row 50.

**Gate/result:** four source contracts cover 28 pages; source/reference files are unchanged; Jordan intake stays disabled. This is a readiness baseline, not a measured extraction accuracy score.

### J2 - Clean Jordan master, dynamic writer and printed-workbook verification - completed 25 October 2026

- [x] Remove duplicated sections once in the master, keeping the Jordan structure and distinct KG, quantity/unit and value columns.
- [x] Reuse the established invoice fonts, red emphasis, goods borders, aligned numbers and clean total treatment. Keep unsupported fields blank and intervention text off the invoice.
- [x] Replace the 15-row cap with dynamic rows, wrapped descriptions and moving totals/declarations/print bounds; retain a readable multi-page layout rather than shrinking a large invoice onto one page.
- [x] Clear sample/stale values; write dates as dates and values as numeric cells; use literal text for identifiers and unsafe formula-like source strings.
- [x] Make the independent verifier check Jordan headers, all goods, total, visibility and print bounds. Replace the existing synthetic verifier workaround with actual master/writer tests.
- [x] Exercise empty/one/15/17/25+ goods, long addresses/descriptions, blank versus zero weights/values, and native Excel print.

**Gate:** no row loss, duplicated totals, clipped goods or stale text; actual writer output passes verification; Bangladesh/India regression checks pass. Jordan remains disabled.

Completion evidence: 473 tests passed in 128.778 seconds. Native Excel printed the blank master and empty/short/long-text invoices on one page; all 60 synthetic goods printed across three pages with repeated headings and one total. The 25-row readiness probe now preserves 25 rows and passes independent verification. All 21 existing jobs/invoices and 164 protected files other than the intentionally updated Jordan master are unchanged. Fresh Jordan extraction is deferred to J3-J6.

### J3 - Jordan header and page identity

- [x] Reuse existing OCR orientation, header geometry, handwriting fallback and source evidence for consignee/address, invoice number, shipping marks and destination.
- [x] Apply the approved date policy: explicit export date first, otherwise latest labelled packing date. Never copy reference dates or use TODAY().
- [x] Check all pages and preserve source-page identity and readable handwritten corrections; do not let an inner-page recipient silently reroute a shipment.
- [x] Approved 25 October 2026: include all pages and use the shipment cover destination. Preserve conflicting recipients as evidence; never silently remove their goods or reroute the file.

**Gate:** source-backed headers checked against all four PDFs; unreadable or unsupported fields blank; the page-conflict policy has an explicit outcome before activation.

Completed 25 October 2026: fresh local OCR covered all 28 pages, and all 32 checked header fields across four PDFs were established from source. Local qwen3-vl and the existing qwen3.5 fallback read bounded handwritten references and unclear dates; exact crops, raw answers and final cached replays are retained under reports/jordan-j3. Cover signature dates do not count as packing dates, and automatic Jordan identification follows the same source-only policy. Shipment 5173 page 6 remains included with its conflicting India recipient recorded. This is header acceptance only; goods, weight, valuation and unseen-document accuracy remain separate gates. Jordan intake stays disabled. Next: J4, after approval.

### J4 - Goods, units, grouping and origins

- [ ] Extract all packing pages using the existing table/cell pipeline. Separate descriptions from internal references and irrelevant text.
- [ ] Preserve fabric composition, knit/woven distinctions and garment types; group only compatible rows, retaining source references.
- [ ] Keep CONES, YDS, PCS, SETS and gross-count button units distinct. Preserve a supplied quantity when its unit is missing; do not borrow the reference's unit.
- [ ] Distinguish primary sample/card quantities from contained pieces, bags or yardage. Do not add both.
- [ ] Preserve explicit mixed origins and missing origins. Add only the minimal item-origin field and its affected writer/audit/editor support if the existing data model cannot represent the source; never print a blanket China footer for mixed/unknown origins.
- [ ] Use targeted local vision for unresolved cells with the existing configurable limits; retain exact crops and outcomes for review.

**Gate:** every source goods row is accounted for as extracted, deliberately grouped or unresolved with evidence in the dashboard; no forced reference row count or invented unit/origin.

### J5 - Package and weight reconciliation

- [ ] Prefer explicit shipment package ranges/counts and gross declarations; keep them independent of per-item packing weights.
- [ ] Reuse the approved PDF package counting and corrected weight-sum rules only when a higher-priority shipment declaration is absent.
- [ ] Count shared physical weight cells once; distinguish net from gross and avoid allocating a shared weight arbitrarily to each goods row.
- [ ] Keep unsupported item KG blank; exclude net weight that conflicts with supported gross, following the approved source-first policy.

**Gate:** cover controls 9/120, 3/48, 6/102 and 6/71 (packages/kg) are checked as source declarations, not production lookup values. Packing details reconcile by their own source semantics; no artificial equality to shipment gross.

### J6 - Jordan valuation

- [ ] Inventory category/unit combinations after goods stabilise; preserve explicit source currency, unit prices and amounts first.
- [ ] Present any uncovered Jordan category/unit rates and total-rounding policy for approval. Reuse approved existing rates only where their category/unit meaning is valid; do not silently assume Bangladesh/India policy applies.
- [ ] Calculate each amount from its own row's quantity and rate; keep gross count separate from grams, and cones separate from metres.
- [ ] Test Decimal rounding, zero/blank values, unsupported currency and partial valuation. Keep unresolved values blank rather than manufacturing a complete total.

**Gate:** approved rates cover supported source items; line/total calculations agree under the approved policy. Reference formulas that link to other rows are not copied. Existing Bangladesh whole-dollar and India cent rules are unchanged.

### J7 - Dashboard, settings and isolated Jordan routing

- [ ] Reuse immutable job country, shared intake/output root and jordan child folders; preserve legacy settings and earlier output locations.
- [ ] Add Jordan-specific editable fields, correct read-only invoice presentation, origins/units and Excel preview; keep OCR/vision explanations and exact image evidence.
- [ ] Exercise enable/disable, all-country filters, deduplication, pause/resume, retries, versioned edits, locked outputs and recovery across mixed-country jobs.
- [ ] Implement the currently locked Jordan setting only after isolated tests pass. Keep its default disabled; ask before enabling production intake.

**Gate:** changing Jordan controls cannot change Bangladesh/India routes, data, settings or invoice appearance; existing queued jobs retain their country and publication destination.

### J8 - Four-file acceptance and regional release

- [ ] Process all four PDFs into isolated QA output/state folders; distinguish fresh OCR/vision from exact-cache reuse and record model/settings/duration.
- [ ] Compare every header, goods/quantity/unit, source-backed origin, package/weight, valuation and actual Excel/printed layout. Classify differences as extraction errors, source ambiguity, intentional grouping, approved estimates or incorrect/unsupported reference values.
- [ ] Use separate completeness and field/item correctness counts with denominators. Do not present reference exact-string matching as universal future-document accuracy.
- [ ] Rehearse interrupted jobs, locked publication, restart recovery, duplicate arrivals, manual edits and recoverable reset without overwriting unrelated invoices.
- [ ] Check all regressions, production file preservation and an extracted release conversion without examples/manual references/development tools. Update the existing guides, API/OpenAPI/Postman only where contracts changed.

**Gate:** all four sample outcomes are documented with no unexplained lost source rows; accepted limitations are explicit; package and recovery checks pass. New unseen Jordan/India PDFs remain a separate pending validation task until available.

### P9 - Final production deployment and handover

- [ ] Rehearse installation and offline model/OCR provisioning on a clean target environment, with dependency/model versions recorded and folder permissions checked.
- [ ] Validate backup and restore of database, settings, templates/rates, input snapshots, evidence and publications together. Document upgrade rollback and disk/evidence retention in operations.md; no automatic deletion without an agreed policy.
- [ ] Review the development Clear data control before wider deployment, preserving its current availability until the user chooses otherwise. Keep the dashboard loopback-only; a shared/network deployment needs separate authentication/access design.
- [ ] Coordinate real Windows sign-out/reboot/startup acceptance with the user and confirm queued/in-progress recovery and no duplicate outputs. Do not reboot the PC during an ordinary coding stage.
- [ ] Check physical print if required, folder monitoring/availability, failure visibility and the single-command launch/runbook. Record measured local inference limits; do not promise throughput before hardware testing.
- [ ] Deliver one verified release, one current roadmap and the existing focused guides. Mark complete only after the deployment/recovery gates pass; keep unseen-document accuracy and future hardware improvements visible as limits.

**Gate:** the user can install, start, monitor, correct, recover, back up and upgrade the product using the documented workflow. Sample acceptance alone does not close clean-machine/reboot/unseen-document checks.

## Evidence and limits

The retained acceptance summary is in ignored `project/reports/verification.json`. Superseded QA runs and historical archives were removed after retaining the useful source contracts and preservation baseline; they are not dependencies.

New invoices use current masters; existing publications retain their saved appearance. No universal invoice accuracy percentage is established. Fresh-machine/offline provisioning, a physical printer and actual reboot acceptance remain unverified. New PDFs can still require long hardware-bound local inference.

## Jordan source-page checklist for implementation

These are development QA controls from the all-page source review, not runtime answers. Recheck the relevant PDF/crop when implementing each rule. Preserve source/reference differences; do not force the manual row count, weights or formulas.

### Jordan 26S5147— ten pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: 9 packages, J01–J09, APP.120 kg, invoice S/5147/26 | Declared shipment gross remains independent of item kg |
| 2 | Eight knit fabric rows: 5,15,16,5,10,10,10,12.5 YDS; compositions 100% cotton, 60/40 cotton/polyester and 70/30 cotton/polyester; COO China; shared and individual 2 kg cells | Preserve row composition links; do not multiply shared 2 kg by its row count; handwritten box notes are evidence, not automatically extra packages |
| 3 | Thread TEX24 15 CONES and TEX27/402 15 CONES (5000 metres/cone); buttons 1 GRS and 3 GRS; net kg 2.3,3.2,0.02,0.1; shared gross 6 kg / 1 carton | Net/gross distinction; cones stay cones; GRS means gross count, not grams; no automatic metre conversion |
| 4 | Elastic trim card 1 PC, China, 0.5 kg, 1 package | Card is a goods item; program/reference code is not goods text |
| 5 | Black elastic 30 YDS / 0.5 kg; handwritten fabric swatches over bulk dye-lot cutting 60 PCS / 1 kg; each packing entry says 1 pack | Separate row units; handwritten category; no forced consolidation to outer shipment count |
| 6 | Labels 36+24+60 PCS; QC seal cord 60 PCS; hangtag 60 PCS; white elastics 30+15+15 YDS; interlining 30 YDS; COO China; one shared handwritten 3.5 kg / package | Label/cord/hangtag distinctions; group compatible elastics without swallowing interlining; shared kg once |
| 7 | Fabric swatches annotation; 88% polyester / 12% spandex knit, 1 quantity with no unit printed; China; 1 kg / 1 pack | Quantity source exists but unit is unavailable; do not silently supply PC/YDS/SET from reference |
| 8 | Women's 67% rayon / 28% nylon / 5% spandex knit pants, 2 PCS, NON-MUTILATED, COO Bangladesh, 1 kg / 1 package | Preserve Bangladesh origin and garment type |
| 9 | Eight women's 100% cotton knit fleece garments, each 1 PC: crew, hoodie, full-zip hoodie, half-zip hoodie, straight-leg pants, jogger, straight-leg pants, barrel sweatpants; China; shared 5 kg / 1 package | Eight source garments; aggregate only equivalent types; shared weight cannot be allocated by copying manual row kg |
| 10 | Five men's 88% recycled polyester / 12% spandex knit garments, each 1 PC: short-sleeve tee, long-sleeve tee, short-sleeve polo, long polo, tank top; shared 2 kg / 1 pack; COO not supplied | Handwritten NON-MUTILATED and tee correction; preserve distinct garment types and missing origin |

Dates on packing sheets consistently indicate 29-Sep-2026 (some omit the year). Source origins are mixed/partial, including China and Bangladesh. The manual 15-row summary loses distinctions; its exact row count is not the target. Its cross-row rate formulas produce 26.07 whereas applying each displayed row's own rate gives 22.91. Neither value is extracted pricing.

### Jordan 26S5172 — two pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: 3 packages, J01–J03, APP.48 kg, S/5172/26 | Gross control 48 kg |
| 2 | Care labels 106,400 PCS; packing weight 45 kg; 3 cartons; dated 6-Oct-2026 | Read quantity without decimal loss; item kg 45 is not header gross 48; no separate origin/HS supplied |

Reference date 7-Oct-2026 and row kg 48 are not extraction targets. Approved PDF-date fallback gives 6-Oct-2026 when no export date exists.

### Jordan 26S5173 — eight pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: 6 packages, J04–J09, APP.102 kg, S/5173/26 | Shipment declaration takes priority over incompatible packing totals |
| 2 | Knit fabric: 60/40 cotton/polyester 30+30+30 YDS, 100% cotton 37 YDS, 70/30 cotton/polyester 21 YDS; kg 15,15,15,15,5; five rolls; China | Group composition-compatible rows; source kg sum65, not manual allocated fabric kg |
| 3 | Woven fabric 55% cotton / 45% recycled polyester, 2 YDS, 1 kg, 1 pack | Preserve woven/knit distinction; width 53 inches; origin unavailable |
| 4 | Heat-seal size labels with COO, 200 PCS (M100/S100); 0.5 kg / 1 package | The phrase with COO describes labels; it does not establish a country of origin |
| 5 | Black elastics 30+15+15 YDS; black interlining 30 YDS; China; shared 3 kg / 1 package | Elastic total60 YDS distinct from interlining30 YDS; no invented kg split |
| 6 | 100% cotton woven fabric, handwritten SAMPLES replacing hanger; quantity1 with no unit; HS N/A; 0.2 kg / 1 package | **Destination conflict:** page says TGPL-FOC / TRIMETRO GARMENTS INDIA PRIVATE LIMITED, while cover and other pages are Jordan. Approved policy: include its goods, retain the recipient conflict as evidence, and use the shipment cover destination |
| 7 | Fabric card with handwritten SAMPLES, 1 PC, 0.02 kg / 1 pack; date6-Oct-26 | Preserve card category and tiny weight; origin unavailable |
| 8 | CO label, 20 PCS, 0.1 kg / 1 package | CO label is product text, not a country declaration; no origin supplied |

The approved general rule includes every page and keeps the shipment cover destination; the conflicting recipient is an explicit isolated test case, rather than an automatic page exclusion. The eight-row manual summary is comparison context only.

### Jordan 26S5197 — eight pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: 6 packages, J01–J06, APP.71 kg, S/5197/26 | Use cover gross71; do not force item sum to equal it |
| 2 | 89% polyester / 11% spandex woven fabric30 YDS; China; 10 kg / 1 box | Preserve composition and unit |
| 3 | 60/40 cotton/polyester single jersey20 YDS and 96/4 viscose/spandex rib10 YDS share6 kg/1 carton; 47/46/7 tencel/recycled polyester/elastane50 YDS/20kg; 77/17/6 recycled polyester/rayon/spandex55 YDS/18kg and35 YDS/11.5kg; COO China | Three distinct compositions plus jersey/rib; do not assign6kg twice; latter compatible fabric can group90 YDS/29.5kg |
| 4 | Plastic snap button die mould2 SET (2PCS); China; 0.3 kg / 1 pack | Use primary supplied2SET; parenthetical pieces are not another quantity to add |
| 5 | Fabric swatch card30 SET; COO HK; 1 kg / 1 package | Preserve set unit and explicit HK origin |
| 6 | Trims card18 PCS and fabric swatch24 PCS share1 kg/1 package; cloud/scrub group fabric swatch2 PCS, label sample card1 PC (main/size/COO labels50each), another trim card1 PC (main/hangtag/string50each), elastic sample1 PC (50YDS), interlining sample2 PCS (15YDSx2 bags), shared4kg/1package; China | Distinguish outer sample/card quantity from contained pieces/yardage; do not double count both; retain printed detail for review |
| 7 | Fabric card1 PC/0.02kg/1pack; horn button1 GROSS and invisible zipper5 PCS share0.2kg/1pack; origin not supplied | Gross-count button; shared kg once; no manufactured row allocation |
| 8 | Knit sweatpant1 PC + sweatshirt1 PC share1.5kg/1package; woven tops2PCS + pants1PC + tops1PC share1.5kg/1package; all explicitly Vietnam, NON-MUTILATED | Keep sweatpant/sweatshirt distinct; compatible tops may group3PCS, separate pants1PC; no blanket China footer or arbitrary0.5kg per garment |

This file has explicit China, HK and Vietnam origins, plus rows with unavailable origin. The manual China footer is unsupported for the complete consignment. Source-driven garment grouping may produce more than the manual17 goods rows; the writer must support growth regardless.

## Jordan layout contract

Preserve the distinct KG, quantity/unit and value columns; helper rate/currency cells may stay outside the print area. Clean duplicated country/header/goods/total/declaration blocks in the master once, then expand the goods area and print bounds dynamically.

| Area | Current reference anchors | Planned handling |
|---|---|---|
| Header | C9 date; I9 marks; I10 destination; I11:J11 cartons (label H11); C11 onward consignee/address | Extract from the correct header blocks; keep the actual recipient and marks |
| Summary | D16 country; C18 invoice; B21 packages; F21 gross kg | Clean incorrect duplicate headings in the blank, then use explicit declarations |
| Goods | Start row 27; A cartons, B description, F kg, G quantity, H unit, I value | Dynamic rows now support 60 tested goods; preserve garment type, material, quantity and weight-source relationships |
| Pricing | K rate and L currency helper columns in references | Calculate against each row's own rate; never copy mislinked formulas |
| Footer | Dynamic total in H/I:J at row 35 plus overflow; sample statements below | Keep totals/footer inside print area and avoid copying a default origin |

Rates and origin handling still require decisions at the extraction stage. Page 6 of 5173 follows the approved include-all-pages/cover-destination policy. Sample/card quantities must not be added to their contents. Each value uses its own row rate; reference formula mistakes and default China footers are not rules.
