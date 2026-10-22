# India / Jordan Stage 1 — baseline and source contracts

Completed 22 October 2026. This stage freezes the current implementation and defines development checks. It changes documentation only; no parser, writer, template, valuation, routing, schema, setting or frontend behavior changed. India and Jordan remain disabled in the production watcher.

## Preservation and verification

- Main dashboard before/after: 20 completed attempts/jobs, zero failures, zero queued/running/waiting jobs; queue remains unpaused. Scanner, worker and web are running after restart on port 8080.
- Used the existing current-user startup stop/start commands. The idle service exited before copying state/artifacts/output; no job was cancelled, reset or reprocessed.
- `python -m unittest discover -s project/tests -q`: **284 tests passed**, 74.974 seconds. Logged locked-folder/disk-unavailable errors were deliberately injected recovery tests, not live pipeline failures.
- `node project/tests/test_dashboard_status.js`: passed.
- SQLite integrity check: `ok`; backup manifest records 20 completed jobs.
- Source ZIP manifest and matching-data ZIP contents were verified. The matching-data archive contains 186 files, including state, retained input snapshots, attempt evidence, input PDFs, published outputs and existing QA scripts/tests. Lock files are deliberately excluded.
- Production source, frontend, configuration, rates, templates and output preservation are checked against the archived hashes. SQLite heartbeat/log bytes naturally change after restart; they are not treated as immutable output.

Evidence is in `reports/india_jordan_stage1_20261022/`: `production-baseline.zip`, `matching-data-and-qa.zip`, `baseline_manifest.json`, `verification.json`, the `bd-comparison/` report and page images. The earlier planning inventory/reference formula analysis remains in `reports/india_jordan_plan_20261022/`.

## Bangladesh comparison checkpoint

The existing read-only comparison tool examined 20 generated and 20 manual workbooks. It paired 18 by its current identifiers and found 58/75 exact goods matches (77.3% reference recall), 58/82 generated rows matching (70.7% precision), and 65/75 quantity/unit overlaps. No incomplete generated goods rows were found in the paired files.

Two generated names, `26S5177-I.xlsx` and `26S8185-I.xlsx`, were unpaired against reference names `26S5176-I.xlsx` and `26S5185-I.xlsx`. These references exist: this is an unpaired-identifier result, not proof that conversion omitted two invoices. No alias was added merely to improve this score.

| Scored field | Exact matches |
|---|---:|
| Invoice number | 18/18 |
| Shipping marks | 18/18 |
| Consignee | 16/18 |
| Packages | 14/18 |
| Gross kg | 12/18 |
| Value | 14/18 |
| Scored date | 1/8 |

These are strict manual-reference differences frozen before regional changes. They include approved PDF-first differences and are not all extraction defects. Formula/TODAY reference handling and unpaired cases limit this tool. They do not establish an overall production accuracy percentage. No Bangladesh invoice was regenerated during this stage.

## Source classification rules

Each field below is classified **source** (legible PDF evidence), **rule** (calculation or approved policy), **unavailable** (no sufficient source; keep empty), or **conflict** (retain candidates and evidence; do not silently force the reference). Page numbers are physical PDF pages. These are QA contracts, not runtime lookup tables. Production must not load this report or any manual reference.

| Field | India 5196 | Jordan 5147 / 5172 / 5173 / 5197 | Handling |
|---|---|---|---|
| Shipper/contact | Source: cover | Source: covers | Use labelled cover block; distinguish notify-party/recipient blocks |
| Consignee/address | Source: cover, TRIMETRO GARMENTS INDIA | Source: covers, EPIC DESIGNERS LIMITED JORDAN | Preserve actual cover address; page-recipient conflicts remain evidence |
| Country/destination airport | Source: India / Chennai | Source: Jordan / Amman | Region bound to approved inbox; never infer origin from destination |
| Marks | Source: TGPLFOCTS | Source: EJU1FOCTS | Preserve actual text; do not impose BD punctuation |
| Customs invoice number | Source: handwritten S/5196/26 | Source: handwritten S/5147/26, S/5172/26, S/5173/26, S/5197/26 | Use source reading; no filename-specific corrections |
| Carton range | Source: T01–T07 | Source: J01–J09 / J01–J03 / J04–J09 / J01–J06 | Range is identity evidence, not a per-item carton allocation |
| Outer packages | Source: 7 | Source: 9 / 3 / 6 / 6 | Prefer explicit consignment declaration; do not add all internal packing-page counts |
| Shipment gross kg | Source: EST. 106 | Source: APP. 120 / 48 / 102 / 71 | Keep estimated declaration distinct from packing-item sums |
| Export date | Unavailable as an explicit export date | Unavailable as explicit export dates | Existing rule: packing date fallback; no automatic next-day adjustment |
| Packing date | Conflict: p2 13-Oct-2025, p3 13-Oct-2026 | Source: 29-Sep-2026 / 6-Oct-2026 / 6-Oct-2026 / 13-Oct-2026 | India conflicting-year selection remains a Stage 4 decision; no current-date/filename repair |
| IEC/PAN/GST | Source: AAJCT7390N / AAJCT7390N / 21AAJCT7390N1ZS | Unavailable in these source covers | Treat identifiers as text, not numbers |
| Other tax IDs/TIN/BIN/cover note | Unavailable beyond explicitly printed IDs | Unavailable in reviewed pages | Keep empty; do not import from manual reference or consignee defaults |
| Port of discharge | Source destination Chennai; mapping to invoice port is a rule | Source destination Amman; no separate required reference port slot | Do not confuse destination airport with an origin/route declaration |
| Incoterm/on-about date | Unavailable: reference CPT/on-about not supported by PDFs | Unavailable | Freight prepaid alone is insufficient evidence for CPT |
| Description/quantity/unit | Source: p2–3 below | Source: all packing pages below | Preserve garment type, composition, unit and row links; group only compatible items |
| HS code | Source: fabric 55132900; other goods unavailable | Unavailable: blank columns/no supplied codes | Preserve printed string; do not classify/invent customs codes |
| Per-item/shared weight | Source: p2 six 17 kg entries; p3 shared 3 kg | Source: page-specific kg/net/gross/shared cells below | Shared physical cell counted once; do not invent individual shares |
| Net shipment weight | Unavailable | Unavailable as a whole-shipment net declaration; 5147 p3 has item net weights | Not an applicable mandatory invoice field; do not substitute gross |
| Origin | Unavailable | Source/partial/mixed; see below | Do not fill shipment origin from default China; retain item associations |
| Unit prices/amounts | Unavailable in PDF | Unavailable in PDFs | Rule pending separate regional rate/rounding approval; reference values are QA context only |
| Invoice total | Rule: sum calculated lines after rate approval | Same | Use each row's own rate; no copied cross-row formula; BD rounding remains unchanged |
| Sample/condition footer | Rule: template declarations; sample purpose in packing pages | Source: garment NON-MUTILATED where printed; other template declarations are rules | Do not label every garment condition/origin without source or approved standing rule |

## Page and goods checklist

All 31 pages are accounted for visually: nine from the planning checkpoint and the remaining 22 in this stage (5197 p8 was also reviewed again). All are scans without an extractable text layer. This is human source review, not a completed OCR/model extraction benchmark. Numeric controls below must be verified again against the source crop when implementing parser tests; these notes must not become production overrides.

### India 26S5196 — three pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: invoice/consignee/IDs/marks; seven packages; T01–T07; EST.106 kg | Preserve separate shipper, consignee and notify-party blocks |
| 2 | Six rows of 63 YDS = 378 YDS; 57% cotton / 35% linen / 6% polyamide / 2% elastane woven fabric; width 53 inches; HS 55132900; six 17 kg entries | Rotation; shared composition across six rolls; preserve inch mark; printed date 2025 conflicts with next page |
| 3 | Zippers 5+5+35+5+15 = 65 PCS with lengths 15–19 cm; three sample entries of 1 SET each; shared 3 kg / one package; handwritten FAB SWATCHES annotation | Quantity-column pairing; retain annotation evidence; group three compatible sample sets only after category reading is supported |

Source packing kg sum 105 differs from estimated cover gross 106. Do not force equality. Reference fabric width says cm while source says inches. Reference export date 14-Oct-2026 is not a supplied next-day rule.

### Jordan 26S5147 — ten pages

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
| 6 | 100% cotton woven fabric, handwritten SAMPLES replacing hanger; quantity1 with no unit; HS N/A; 0.2 kg / 1 package | **Destination conflict:** page says TGPL-FOC / TRIMETRO GARMENTS INDIA PRIVATE LIMITED, while cover and other pages are Jordan. Preserve candidate evidence; do not silently reroute entire file or silently discard this page. Resolve page inclusion before Stage6 activation |
| 7 | Fabric card with handwritten SAMPLES, 1 PC, 0.02 kg / 1 pack; date6-Oct-26 | Preserve card category and tiny weight; origin unavailable |
| 8 | CO label, 20 PCS, 0.1 kg / 1 package | CO label is product text, not a country declaration; no origin supplied |

No general rejection or automatic page-exclusion rule was introduced. This conflict becomes an explicit isolated test case when routing/extraction is implemented. The eight-row manual summary is comparison context only.

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

## Recovering the baseline

The two ZIPs form one recovery point. Keep them private: the data archive includes customer PDFs, invoice data and local settings. Hashes detect accidental changes; the archives are not encrypted or signed.

1. Stop the current system with `project/.venv/Scripts/python.exe project/run_system.py --startup stop`; confirm the worker has drained and the background process exited. Do not overwrite an active database or output tree.
2. Restore the production ZIP into a **new** directory. Its application tree is under `foc-invoice/project/`; verify every packaged file using `foc-invoice/BUILD_MANIFEST.json` before use.
3. Restore matching-data archive members under its `project/` prefix into the corresponding restored project. Verify against `baseline_manifest.json` before opening the database. Do not mix a later database with older artifacts/output.
4. On this PC, retain the matching installed Python environment and local OCR/Ollama model files. They are excluded from ZIPs. On another machine, follow setup/build dependency provisioning, then test separately. Absolute managed paths in saved settings need deliberate checking if the deployment location changes.
5. Validate SQLite integrity, completed counts and artifact/output hashes; start with the same approved configuration and confirm web/scanner/worker state. Keep the newer stopped installation/data separately until recovery has passed.

Archive extraction/individual hashes and database integrity were verified; a destructive restore over the live installation was deliberately not performed. This is a recoverable matching backup, not a claim of fresh-machine or reboot certification.

## Gate and next stage

Stage1 is complete: consistent baseline, existing regressions green, all pages reviewed, applicable fields classified, source/reference conflicts recorded, production still BD-only. No fresh India/Jordan OCR/VL inference or invoice generation was run; regional extraction accuracy remains unmeasured.

Next, subject to review: Stage2 adds explicit country identity/template provenance and verification, protects both `expected_outputs` and its legacy singular alias from output selection, and preserves old jobs/settings. It does not enable regional watching or change goods/pricing rules. Date, origin, mismatched-page inclusion and regional rates remain recorded decisions for the extraction/valuation stages.
