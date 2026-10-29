# Readiness and remaining stages

## Factory defaults and pricing rollout â€” 28 October 2026

This rollout follows FOC-AUTOMATION.xlsx, Sheet1. factory_profiles.json contains the approved master with workbook checksum and source rows. Stages 2/2.1 identify the factory across all countries; Stages 3/4/5 apply the supplied static details to confidently matched factories in Bangladesh, India and Jordan during new generation or explicit reprocessing. Stage 5 also applies the approved CHINA-origin rule to automatic Jordan generation. Stage 6 unit pricing is active for new conversions. Existing saved invoices, queues, model settings and the source workbook remain unchanged.

| Stage | Deliverable | State |
|---|---|---|
| 1 | Approved factory master, field ownership and pricing decisions | Complete; user decisions recorded 28 October 2026 |
| 2 | Country-aware factory matching, with explicit EGMCL versus EG2 identity | Complete; shared identification |
| 2.1 | Recipient-address fallback and conflicting-site safeguards | Complete; shared identification |
| 3 | Bangladesh static fields and template; review EGMCL, EG2, GTL, CIPL and PGCL | Complete; Bangladesh defaults enabled |
| 4 | India static fields, identifiers, shipment wording and declarations | Complete; India defaults enabled |
| 5 | Jordan static fields, declarations and agreed origin policy | Complete; Jordan defaults and automatic CHINA-origin rule enabled |
| 6 | Two unit-based pricing rules, agreed cap and rounding | Complete; deployed 28 October 2026; acceptance below |
| 7 | Dashboard field provenance and saved-version behavior | Not started |
| 8 | Per-factory UAT, regression checks and controlled release | Not started |

### Stage 1 data contract

- [x] Import all seven supplied profiles: five Bangladesh factories, one India factory and one Jordan factory.
- [x] Keep consignee name and address separate; preserve address identifiers as text, including leading zeros and the EG2 TIN suffix /Coy-20.
- [x] Normalize No Need / NO NEED to null. For the explicitly supplied static fields, null means omit the printed field; raw PDF evidence must remain retained. A field absent from a profile, such as shipping marks, has no supplied default and continues to use PDF information.
- [x] Import the cover note only for EGMCL and EG2; TIN only for EGMCL, EG2 and CIPL. Preserve the supplied wording and regional declarations.
- [x] Keep Rose and unknown factories unmatched. Do not reuse another factory's details or a previous shipment's answers.
- [x] Approved pricing for Stage 6: USD 0.20 per YDS and USD 0.10 multiplied by quantity in the extracted stated unit for other items. Activated in valuation_rates.json during Stage 6.
- [x] For a confidently matched factory, use the supplied consignee/address/tax details. Do not use PDF addresses as a replacement or fallback for those mastered fields. Preserve original PDF evidence separately; never combine identities from different factories.
- [x] JANCO is not an applicability condition. When the factory matches, use its supplied shipment wording; omit it where the master says No Need. This does not authorize changing exporter headings.
- [x] Cap calculated estimates at USD 80 using proportional reduction of estimated effective rates/line amounts. Keep quantities unchanged and reconcile rounded line values. Preserve explicit PDF prices, line amounts and totals, including values above USD 80; never scale those source values or merely replace a total while leaving incompatible estimated lines. Mixed source/estimate cases must preserve source values and be covered during Stage 6.
- [x] Always use CHINA as the printed origin for automatic Jordan generation, including when the PDF supplies another origin. Record this as an approved business rule, retain original PDF readings in evidence and do not label the substituted value as PDF-extracted. Activated in Stage 5; historical saved invoices and deliberate manual revisions remain preserved.

### Stage 2 identification contract

The shared matcher reads only the first-page shipment heading / consignee and the existing source-parsed consignee. It normalizes punctuation and common legal abbreviations (CO/COMPANY, LTD/LIMITED, PVT/PRIVATE). Factory aliases are kept in the approved master. EG2 accepts explicit EGMCL Unit-2 identity; a generic EGMCL family name can accompany Unit-2, but explicit Unit-1 versus Unit-2 conflicts remain unresolved. Unrecognized EGMCL units are not assigned to the main factory.

Only one country-consistent factory is accepted. Multiple factories, conflicting unit qualifiers and recognized foreign-country factories return no selected factory. Rose, unknown parties and country names alone remain unmatched. Filenames, sender/buyer/body references, notify parties and later packing pages do not supply factory identity. Identification itself does not alter fields; the separate Stage 3 application step enables approved Bangladesh overrides after a successful match.

New conversions record a factory_identification processing event with factory_id, status, candidates, header evidence and profile_sha256. This is available through the existing job events API; the user-facing factory display is reserved for Stage 7. Attempt metadata captures factory_profiles_sha256, and a changed master during conversion prevents publication. Historical invoices/receipts do not require a new identification event. Release archives include the master JSON.

Stage 2 acceptance: the full 588-test regression run passed. After additional compact-unit safeguards, 67 focused identification, queue, pipeline, evidence and release checks passed. A read-only replay of ten retained Bangladesh OCR records identified nine known-factory shipments and correctly left Rose unmatched. All 40 protected source/receipt/invoice-data files and the saved production settings were unchanged. This is matching on retained OCR plus synthetic coverage for other factories, not a fresh OCR accuracy claim.

### Factory-header review and address fallback rule - 28 October 2026

Source folder: `C:/Users/Hasan.Mahmood/Downloads/FOC/FOC`. This review uses the PDF recipient headings, not the manually prepared Excel files. Fresh first-page header OCR is evaluated against the existing Stage 2 matcher; it does not regenerate invoices or activate static defaults. Diagnostic images and raw readings are retained outside production in the Codex visualization workspace under `foc_factory_review_20261028`.

All 25 PDFs were checked with fresh orientation/deskew and 250-DPI upper-left header OCR, without reusing stored OCR/vision answers. The existing matcher selected all 24 approved-profile shipments correctly and left the unlisted Rose shipment unknown. This is 96% approved-profile coverage of these samples, not an invoice-accuracy score or unseen-document acceptance. Source fingerprints remained unchanged. The production dashboard remained available with ten completed jobs and zero running, queued or failed jobs during the check.

| Profile | Reviewed PDFs (26S prefix and -D.pdf suffix) | Count |
|---|---|---:|
| EGMCL | 5166, 5183, 5193, 5195 | 4 |
| EG2 | 5157, 5158 | 2 |
| GTL | 5184, 5188, 5189, 5190, 8185 | 5 |
| CIPL | 5186, 5187, 5194 | 3 |
| PGCL | 5169, 5170, 5177, 5191, 5192 | 5 |
| INDIA | 5196 | 1 |
| JORDAN | 5147, 5172, 5173, 5197 | 4 |
| No approved profile: THE ROSE DRESSES LTD | 5075 | 1 |

These sample identifiers document review coverage only. No expected-output workbook, filename lookup or per-shipment answer was used by the factory matcher. All approved profiles in this set had readable name/code evidence, so the review does not establish address-only fallback accuracy.

The identification rule is:

1. Use the shipment cover's labelled CONSIGNEE column. For a packing-list-only document, use its TO heading or factory heading above PACKING LIST. The literal top-left corner alone is not sufficient: cover pages start with ALPHA START LTD, the exporter, and JANCO is in the adjacent agent column.
2. Match a normalized complete factory name or approved factory code. Ignore punctuation, common legal abbreviations and trailing FOC/FABRIC/GMT category labels. Keep EGMCL 2 / EGMCL UNIT 2 distinct from generic EGMCL. Unrecognized unit numbers must not be assigned to the main factory.
3. If the name/code is unreadable or incomplete, the active fallback requires all distinctive address clues in the table below, inside that same recipient block, and exactly one country-consistent profile. Shared city/country text such as Savar, Dhaka or Bangladesh is insufficient. A specific factory name conflicting with another factory's address remains unresolved; a generic family name may be refined by a consistent unit/address. When OCR geometry is available, use the consignee column rather than text flattened across the adjacent agent column.
4. If the recipient block is still unreadable, leave factory identity unresolved. A factory-specific bounded vision reader is deferred; this change introduces no additional model requests. Any future reader must transcribe only the visible recipient block and run the same matching checks, without inventing the factory or its address.
5. Ignore shipper, agent, notify-party, buyer, sender and goods-table mentions. Later packing pages cannot override an established shipment-cover factory. The country folder is a consistency check, not identity evidence. BIN/TIN/GST may corroborate a match but are not the sole key because source identifiers can differ from the current approved master.
6. A successful identity selects the supplied master profile for later static-field stages. The PDF address is identification evidence; it does not replace the approved printed master address. Unknown factories retain source extraction without receiving another factory's static details.

| Profile | Primary identity | Required address clues (all must be present) |
|---|---|---|
| EGMCL | EPIC GARMENTS MANUFACTURING CO. LTD. / EGMCL | ADAMJEE EPZ + SIDDHIRGANJ |
| EG2 | EGMCL 2 / EGMCL UNIT 2 / approved UNIT-2 legal name | DEPZ EXTENSION AREA + GONOK BARI |
| GTL | GREEN TEXTILE LIMITED / GTL | NIJHURI + BARAID + BHALUKA |
| CIPL | COSMOPOLITAN INDUSTRIES (PVT.) LIMITED / CIPL | KHEJUR BAGAN + BARA ASHULIA |
| PGCL | PEARL GARMENTS CO. LTD. / PGCL | POLASHBARI + NABINAGAR |
| INDIA | TRIMETRO GARMENTS INDIA PVT LTD / TGPL | KALIBETI MOUZA + JANKIA + ODISHA |
| JORDAN | EPIC DESIGNERS LTD JORDAN / approved EPIC DESIGNERS alias / EJU1 | AD DULAYL + ZARQA |

Address spelling normalization must preserve meaningful site/unit differences. In this source set, EG2 is established by the clear EGMCL 2 headings; its address-only fallback is supplied by the approved master and needs a real address-only PDF for acceptance. GTL's source BIN ends in 0104 whereas the approved master ends in 1302: that discrepancy must not defeat its clear name/site match. Rose is readable but has no approved master profile; Savar/Dhaka cannot turn it into another Bangladesh factory.

Stage 2.1 adds address_match phrases to the same approved master and name/address match evidence to the existing processing event. Each signature needs at least two distinct, nonempty phrases that exist in its supplied master address; every configured phrase must match inside a single recipient block. A changed master retains the existing publication guard. Address matching identifies the factory; the separate defaults step applies the approved regional fields through Stages 3/4/5. No filename or shipment-number mapping in this review is a production rule.

Stage 2.1 acceptance: 101 focused regional parsing, factory, queue, evidence and release checks passed. Replay preserved all 25 reviewed header results (24 known-profile matches, Rose unknown). Removing the factory-name line from each of the 13 shipment-cover text blocks still produced the correct identity through address evidence. Those masked-name checks reuse the fresh header readings and do not measure new OCR/vision or unseen-PDF accuracy. EG2's address-only rule has synthetic coverage because its available examples identify the factory by code. Existing templates, rates and printed factory master values are unchanged.

Deployment check: the idle service was stopped gracefully and restarted with Windows automatic startup re-enabled. Dashboard, scanner and worker are healthy; all ten existing invoice previews and downloads returned HTTP 200. The 40 protected source/receipt/invoice-data files, saved settings and printed master values remain unchanged. No historical invoice was reprocessed.

### Ownership and release gates

Invoice number, dates, goods, quantities, cartons, packages and weights remain PDF-derived. The workbook supplies no shipping-mark defaults. Matched Bangladesh/India invoices use the supplied master shipment wording; no departure date, discharge port or Incoterm is invented. Factory matching must use the shipment heading/consignee and explicit unit/site identifiers; sender/buyer mentions, filenames and a country folder alone are not sufficient proof of a factory.

Use factory_profiles.json as the deployed factory-data snapshot and the existing valuation_rates.json for activated pricing. Do not maintain two independently editable versions of the same rule or read the Downloads workbook during every conversion. Stage 1 introduced no production hook. Stage 2 adds identification and evidence; Stages 3/4/5 enable the regional static fields and Jordan origin rule. Stage 6 activates the shared unit-rate policy.

Each later stage requires its own review before advancing. Existing invoices are preserved; profile updates must affect new generation or explicit reprocessing, and manual invoice edits must not be overwritten silently by defaults. Future attempt records must capture the selected profile/version using existing audit/evidence mechanisms. Review Excel preview and print layout, missing-field notes and amount reconciliation as well as parsed data.

### Stage 3 Bangladesh defaults and layout acceptance

- [x] At Stage 3 activation, master status was approved with defaults_regions set to BD only; Stage 4 extends it to India. Apply the seven supplied fields to EGMCL, EG2, GTL, CIPL and PGCL: consignee, address/BIN, destination country, TIN, import cover note, shipment_text and remarks. Null optional master fields explicitly omit conflicting source values; unknown/conflicting factories retain source extraction. Shipping marks, dates, invoice number, goods, quantities, cartons, packages, weights and valuation are unaffected.
- [x] Preserve original parsed values in field_source events with method approved_factory_master, original_value, selected factory, source row, omission/replacement action and profile checksum. The master must remain unchanged between identification and application and through publication. Do not describe master values as PDF-extracted.
- [x] Reuse the existing Bangladesh workbook structure and shared writer. Print the supplied shipment line and declarations with wrapped rows, red BIN/TIN/cover-note text, existing goods borders and total styling. Bangladesh still omits net weight. The binary blank template is unchanged; future invoices receive the behavior through the shared writer.
- [x] Store shipment_text and remarks in generated invoice data. Null retains historical template behavior; an explicit empty string omits that wording. Manual editing reconstructs stored values without reapplying the latest master. Existing invoices and manually saved versions are not regenerated automatically.
- [x] Publication verification checks the stored Bangladesh shipment line, consignee/address/BIN, country, TIN, cover note and declarations against the printed cells, including grown goods areas. The browser preview renders the same workbook values.
- [x] Full regression: 601 tests passed. Ten isolated saved-data replays changed only approved static fields/related warnings for nine matched shipments and left Rose unchanged. Goods, dates, quantities, weights, totals and source marks remained unchanged. Five factory layouts passed workbook/preview checks and native Excel PDF print review; EG2 used an explicitly synthetic nine-row layout sample because no complete saved production result was available for that factory. The 25 reviewed header matches and 13 masked-name cover-address checks remain unchanged.

Acceptance artifacts remain outside the repository under stage3_bd_review in the conversation visualization workspace. This validates profile application and formatting; it is not a fresh full-OCR/vision accuracy measurement. Stage 4 was subsequently approved and is recorded below.

Stage 3 deployment: 74 final focused checks passed after adding the explicit-omission print test and documentation. The production service was restarted and Windows automatic startup re-enabled. Dashboard, scanner and worker are healthy; all ten retained previews/downloads returned HTTP 200. All 40 protected source/receipt/invoice-data files, saved settings and supplied master business values remain unchanged. New generation or explicit reprocessing receives the Bangladesh defaults; no historical invoice was regenerated.

### Stage 4 India defaults and layout acceptance

- [x] Extend the same generation-only defaults step and defaults_regions to BD and INDIA. Confident Trimetro / TGPL matches use the supplied consignee, complete address including IEC/PAN/GST, destination country, shipment wording and declarations. TIN and import cover note are explicitly omitted per the master. Unknown/conflicting India factories retain source extraction; Jordan defaults remain inactive. Original parsed values and profile provenance use the existing audit events and publication guards.
- [x] Reuse the India template/writer. Print SHIPMENT FROM HONG KONG TO CHENNAI BY AIR with Chennai in red, preserve red tax identifiers and use the stored three-line declaration below the total. No packing date becomes a departure date, and the shipment city does not supply discharge port or CPT. Dates, goods, source quantities/HS codes/weights, shipping marks, existing prices and totals are unaffected.
- [x] Preserve historical null wording behavior, explicit omissions, saved declarations and manual field changes. Defaults are applied during generation, not during manual editing. Verify shipment, tax-address cells and declarations against stored data after goods growth; corrupted values block publication.
- [x] Regression: 606 tests passed. The existing 25-header replay and 13 masked-name address checks remain unchanged. Ten Bangladesh saved-data replays exactly match their Stage 3 results. The fresh three-page India PDF check started with an empty derived OCR cache and used no vision; comparing defaults off/on changed only the address, country casing, shipment_text, remarks and associated warnings. Goods, dates, quantities, weights and valuation matched the same fresh-OCR baseline. This isolates defaults behavior and is not an end-to-end OCR/vision accuracy claim.
- [x] Browser-preview/workbook checks passed for the real sample and a synthetic 40-row layout. Native Excel print review showed the real sample on one page and all 40 synthetic rows across two pages, with repeated table headings, readable identifiers, totals and declarations. Existing templates, rates, saved settings, the source PDF and all 40 protected production files remain unchanged.

Stage 4 review files are outside the repository under stage4_india_review in the conversation visualization workspace. Only one unique real India shipment is available; unseen-PDF UAT remains open. Stage 5 was subsequently approved and is recorded below.

Stage 4 deployment: 51 final focused defaults, India/manual-edit, preview, Jordan-writer and release checks passed after documentation updates. Production was restarted with Windows automatic startup enabled. Dashboard, scanner and worker are healthy; all ten existing previews/downloads returned HTTP 200, with ten completed and zero failed jobs. No saved invoice or production setting was changed or reprocessed. Future matched India generation or explicit reprocessing uses the approved static profile.

### Stage 5 Jordan defaults and regional origin acceptance

- [x] Extend defaults_regions to BD, INDIA and JORDAN. Confident Epic Designers / EJU1 matches use the approved consignee, Ad Dulayl/Zarqa address, destination country and two customs declarations. TIN, import cover note and shipment wording are explicitly omitted per the master. Unknown/conflicting recipients do not receive another factory's details. Raw header readings and profile provenance remain in the existing evidence events.
- [x] Apply CHINA to every item during automatic Jordan generation/reprocessing after source parsing and packing reconciliation. This is the approved regional rule, including missing/explicit different origins and unmatched factories; it is not a factory-identification signal. Do not merge goods after substituting origins. Preserve descriptions, quantities, units, source references, weights, currency, prices and totals. Per-item field_source events retain original_value, item index, source page/references, policy jordan_always_china, method approved_regional_rule and master checksum; an unmatched factory keeps factory_id null.
- [x] Reuse the existing Jordan template/writer, separate KG/quantity/unit/value columns and per-item origin line. Print stored declarations below the grown total; verify them and the stored origins independently of the extracted-items sheet. Null remarks retain historical declarations and explicit empty remarks omit them. Existing invoices and manual saves do not reapply the current master or origin policy; deliberate manual revisions remain preserved.
- [x] Initial focused rule/layout checks: 50 passed, including mixed and missing source origins, unknown-factory behavior, origin-policy/version guards, pipeline ordering, 40-row growth and manual-origin preservation. The fresh two-page Jordan PDF comparison started with an empty derived OCR cache and no vision calls. Enabling defaults changed only approved static values, item origins and related warnings; all other goods fields, dates, cartons, quantities, weights, currency and valuation matched its fresh-OCR baseline. Ten Bangladesh data replays and the India output exactly matched their preceding stages. The 25 reviewed header results and 13 masked-name address checks are unchanged.
- [x] Workbook/browser-preview checks and native Excel print review passed. The real sample printed on one page; the synthetic 40-row layout printed on two pages, retaining all 40 goods/origin lines, repeated table headings, totals and declarations. Original PDFs, the three blank templates, rates, saved settings and the 40 protected production files were not rewritten.
- [x] The full test run exposed Excel's temporary owner file being included by the release builder. Exclude names beginning ~$ from the archive without closing Excel or deleting its owner file. A deterministic isolated owner-file fixture and 38 focused release/Jordan checks passed after the fix.

Stage 5 review files are outside the repository under stage5_jordan_review in the conversation visualization workspace. The fresh OCR-only comparison validates these rules and formatting, not full OCR/vision accuracy across all unseen Jordan PDFs. Stage 6 (the approved unit-based rates, estimate-only USD 80 cap and rounding) requires the next user approval.

Stage 5 release acceptance: after the Excel owner-file packaging fix, the full 613-test regression rerun passed. Production was restarted with Windows automatic startup enabled. Dashboard, scanner and worker are healthy; all ten historical previews/downloads returned HTTP 200, with ten completed and zero failed jobs. No existing invoice was reprocessed or overwritten, and saved processing settings remain unchanged. Approved Jordan defaults and the regional CHINA-origin policy now apply to new generation or explicit reprocessing.

Deployment update, 27 October 2026: the saved Jordan goods, packing, rates, editing and intake implementation has been restored. Jordan now supports activation through the shared System settings. Historical stage notes below describe earlier checkpoints; fresh-document accuracy and human UAT remain separate acceptance work.

Current organization checkpoint: 25 October 2026; available-sample acceptance completed 23 October 2026. Bangladesh and opt-in India use the same durable local pipeline, regional templates and one worker. Jordan automatic processing remains disabled. Manual references are QA-only and are never production inputs.

Bangladesh generalization checkpoint, 25 October 2026: seven newly tested PDFs exposed quantity/table, description, package/weight and header-reading gaps. Jordan J4 is paused while these are repaired. B1 is complete: Clear data recoverably clears derived OCR/vision/package/weight results, with isolated development caches and installed models preserved. B2 is complete: checked multiplication and position-backed merged rows recover 7 swatch sets in 5231, all 45 yards in 5233 and all 175 yards in 5234. A retained-OCR replay preserves all 20 original Bangladesh goods results; 501 regression tests passed. These checks isolate parsing behavior and do not claim fresh OCR/model accuracy. B3 is complete: compact ruled tables with separate shipped quantity/unit columns recover 2 shank and 6 rivet die-mould sets from 5231 pages 10â€“11. All source pages receive a recorded disposition, including unresolved quantities, unclassified pages and excluded pages. The 28-file retained-OCR/source-render replay changes only 5231 goods; 506 regression tests passed. B4 is complete: fiber modifiers and source measurement tolerances normalize without losing PCW/GRS wording; style metadata no longer breaks continuation headings; joined die-mould names, construction-first garments and explicit category notes use the shared parser. The existing bounded annotation reader now supports Bangladesh. The deterministic 28-file replay preserves quantity totals and all original 20 Bangladesh/one India goods results; 512 regression tests passed. Unusable model category readings remain rejected. B5 is implemented: packing controls include declarations above quantity rows and compact-form local totals; local gross labels no longer block the shipment sum. Explicit counts survive conflicting carton IDs, missing source-page coverage blocks partial totals, and vision-corrected weights require a separate literal reading. 5231 now provides 24 source packages/rolls and 36.6 kg; 5233 source readings corroborate 35 + 5 = 40 kg, without inserting an assumed decimal. All 521 tests passed and all 28 B4 goods results remain unchanged in replay. Further model disagreements remain visible rather than forced. B6 is implemented: Bangladesh reuses bounded header vision with source-reading agreement, and silent filename/company-directory header answers are removed. The source crop for 5236 corroborates S/5236/26; source packing recipient/category text stays literal and unsupported addresses/BINs stay blank. All 528 regression tests passed, and all 28 B5 goods results are unchanged in retained-OCR replay. B6 publication completed for all seven new invoices, including the long 5237 quantity attempt. B7 is implemented: ten missing category/unit valuations are covered by reused estimates and two explicit fastener fallback keys; singular/apostrophized garment names now retain garment rates. All 533 tests passed. Pricing replay changes only 5231 (21/23 rows priced, previously 11/23); all non-pricing fields and India prices are unchanged. Bangladesh pricing coverage is 128/131 rows, with the three remaining rows lacking an established quantity/unit; this is coverage, not an accuracy percentage. B8 is implemented: field-validated installed-reader recovery, terminal failure evidence and narrowly bounded corrected-quantity reading. All 546 regression tests passed; retained-source replay changes only 5237 to 200 YDS / USD 40, with all packing/header controls preserved. Two fresh quantity readings agreed in 30.5 seconds; this is a cell benchmark, not full-document throughput. Brief residency improved a repeated image but retained about 3.38 GB of model memory, so production keeps unloading after each call. B9 was subsequently attempted; see the current acceptance status below. Remaining reader failures and broader accuracy checks stay visible; full cold-document acceptance remains pending.

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

Historical extraction-stage notes below retain the original source-only origin requirements. The approved factory rollout's Stage 5 above supersedes those printing rules: raw origins remain in evidence, while automatic Jordan invoices print CHINA. It does not change the earlier source-page inclusion, quantities or packing contracts.

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

### Jordan 26S5147â€” ten pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: 9 packages, J01â€“J09, APP.120 kg, invoice S/5147/26 | Declared shipment gross remains independent of item kg |
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

### Jordan 26S5172 â€” two pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: 3 packages, J01â€“J03, APP.48 kg, S/5172/26 | Gross control 48 kg |
| 2 | Care labels 106,400 PCS; packing weight 45 kg; 3 cartons; dated 6-Oct-2026 | Read quantity without decimal loss; item kg 45 is not header gross 48; no separate origin/HS supplied |

Reference date 7-Oct-2026 and row kg 48 are not extraction targets. Approved PDF-date fallback gives 6-Oct-2026 when no export date exists.

### Jordan 26S5173 â€” eight pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: 6 packages, J04â€“J09, APP.102 kg, S/5173/26 | Shipment declaration takes priority over incompatible packing totals |
| 2 | Knit fabric: 60/40 cotton/polyester 30+30+30 YDS, 100% cotton 37 YDS, 70/30 cotton/polyester 21 YDS; kg 15,15,15,15,5; five rolls; China | Group composition-compatible rows; source kg sum65, not manual allocated fabric kg |
| 3 | Woven fabric 55% cotton / 45% recycled polyester, 2 YDS, 1 kg, 1 pack | Preserve woven/knit distinction; width 53 inches; origin unavailable |
| 4 | Heat-seal size labels with COO, 200 PCS (M100/S100); 0.5 kg / 1 package | The phrase with COO describes labels; it does not establish a country of origin |
| 5 | Black elastics 30+15+15 YDS; black interlining 30 YDS; China; shared 3 kg / 1 package | Elastic total60 YDS distinct from interlining30 YDS; no invented kg split |
| 6 | 100% cotton woven fabric, handwritten SAMPLES replacing hanger; quantity1 with no unit; HS N/A; 0.2 kg / 1 package | **Destination conflict:** page says TGPL-FOC / TRIMETRO GARMENTS INDIA PRIVATE LIMITED, while cover and other pages are Jordan. Approved policy: include its goods, retain the recipient conflict as evidence, and use the shipment cover destination |
| 7 | Fabric card with handwritten SAMPLES, 1 PC, 0.02 kg / 1 pack; date6-Oct-26 | Preserve card category and tiny weight; origin unavailable |
| 8 | CO label, 20 PCS, 0.1 kg / 1 package | CO label is product text, not a country declaration; no origin supplied |

The approved general rule includes every page and keeps the shipment cover destination; the conflicting recipient is an explicit isolated test case, rather than an automatic page exclusion. The eight-row manual summary is comparison context only.

### Jordan 26S5197 â€” eight pages

| Page | Source rows / controls | Required check |
|---|---|---|
| 1 | Cover: 6 packages, J01â€“J06, APP.71 kg, S/5197/26 | Use cover gross71; do not force item sum to equal it |
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

### Template review corrections and Stage 6 — 28 October 2026

- [x] Keep the standard Bangladesh C/NO, description and quantity goods table for every factory, including Rose. Per user clarification, do not add unit-price or line-value columns.
- [x] Improve carton-range readability, consistent company heading and A4 settings; retain readable multi-page flow and keep the closing block together where it would otherwise split.
- [x] Print a common Jordan origin once near the footer; preserve mixed/partial per-item origins and source evidence.
- [x] Hide technical sheets/helper columns, retaining all evidence and historical verification compatibility.
- [x] Replace obsolete category/regional price tables with two approved unit estimates and the USD 80 estimate-only cap. Protect source rates/amounts/totals and quantities; deterministic cent allocation and total-rounding evidence.
- [x] Keep missing source quantities/units blank and disallow incomplete calculated totals; preserve deliberate manual revisions.
- [ ] Stage 7: user-facing factory/default/pricing provenance display.
- [ ] Stage 8: human UAT, unseen PDFs, actual workstation/printer acceptance and final sign-off.

The review's missing India/Jordan header values came from OCR-only controlled copies, not missing template slots; the existing bounded vision readers remain enabled in production. Filename-mismatched manual examples are not automatic source aliases. Legacy reference TODAY formulas, extra sheets and broken print areas were not copied into production.

Stage 6 acceptance: an earlier full 600-test run passed. The final expanded run exercised 602 tests with one reset-fixture setup error during development; the complete reset module subsequently passed all 25 tests against frozen code. Final focused writer, pricing, metadata and edit checks passed all 57 tests. Historical access passed 40 routes (detail/edit/preview/download for ten saved invoices), both in the upgraded app and through the restarted live server. All 40 protected production artifacts and all 130 reference/source files retained their hashes. New and historical layouts pass independent publication verification; no integrity guards were disabled.

Native Excel checked 16 layout/stress exports on A4, including 40-row regional probes. The 5249 invoice now fits on one page without reducing the body font. Rose now follows the standard Bangladesh goods table per user clarification; uniform Jordan origin appears once. Excel's A4-to-Letter paper mapping was the cause of the earlier native-export discrepancy; the QA export tool temporarily disables that preference and restores it afterward. Blank master binaries and manually prepared source examples were preserved; the central writer applies these presentation rules to every new generation.

Source-hash-verified retained OCR plus new isolated local-vision requests recovered India S/5196/26 with packing date 13-Oct-2026, and Jordan S/5172/26 with date 6-Oct-2026. The Jordan date crop visibly says 6-Oct-26; 7-Oct in its manual example is not copied. Its packing table also explicitly says 45 kg, so item KG remains 45 rather than copying the manual example's 48. These were OCR-only review-copy limitations or intentional source/reference differences, not missing template slots. India header checks took about 635 seconds and Jordan number/date checks about 950 seconds under concurrent QA load; Ollama reported an 8.8B Q4 model on CPU with zero VRAM allocation. This is bounded header verification, not a fresh end-to-end accuracy score for all 65 PDFs.

The existing Windows startup task was restarted with matching code/rates, the paused queue was restored to running, and scanner/worker health was confirmed. Existing completed invoices were not repriced or regenerated. New PDFs and explicit Reprocess actions use Stage 6; human UAT and unseen-document acceptance remain Stage 8.

User layout correction — 28 October 2026: removed the special Rose pricing-column branch. All Bangladesh invoices keep their standard goods table and invoice-level total. Pricing calculations, hidden evidence and India/Jordan reference columns remain unchanged. Existing affected invoices receive a format-only saved revision through the normal publication path; historical versions are preserved.

Correction acceptance: the active invoice finished normally before deployment. Twenty isolated regional layout cases and 45 focused regression tests passed. The saved Rose invoice (job 88) received a verified format-only revision; every invoice data field except internal warning text matched the prior version, including all items and the total. Its preview and the historical download both passed. The queue resumed and the next waiting PDF started normally.

### Rose default extension — 28 October 2026

The user supplied Rose's consignee/address/BIN and three-line mould/export-contract remarks. ROSE is now an approved eighth identity/profile, with user-instruction provenance rather than a claimed workbook row. Only those supplied display fields are overridden; other PDF fields and the seven existing full profiles keep their behavior. The standard Bangladesh goods table remains unchanged. Historical notes that Rose was unmatched describe the earlier rollout, before this approval.

Rose acceptance: 72 targeted factory/default/edit/layout/packaging tests passed. A native A4 preview printed every supplied address/BIN and remark line on one page with the standard Bangladesh goods table. The current PDF finished before deployment. Rose job 88 was saved as a new revision with only the supplied consignee/address/remarks changed; all goods, dates, weights, prices and total were verified unchanged. The new preview/edit page and historical download passed, and queued processing resumed.
