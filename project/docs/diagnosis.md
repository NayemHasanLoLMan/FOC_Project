# BD diagnosis and next improvement priorities

Updated after project cleanup on 19 October 2026. The current commands are in `../README.md`; generated evidence is in `../reports/`. Cleanup preserved the evaluated invoice data and all unique input/reference/template contents.

The pipeline uses free local PaddleOCR, the shared table/parser logic and the existing BD Excel template. All 20 BD example PDFs (66 pages) were processed and their invoices regenerated in `project/output`. Expected workbooks remain evaluation inputs only. This improves the measured result substantially, but it does **not yet reproduce the manually prepared invoices reliably enough to claim production accuracy**.

## Measured results

The comparison reads the actual invoice worksheets. A successful item requires the description, quantity and unit to match after the evaluator's existing limited normalization. The evaluator was not loosened for this upgrade.

The BD sample set contains 20 PDFs, 20 generated invoices and 20 manual references, with 18 matched pairs containing 75 expected item rows. Additional India/Jordan samples are stored separately and are not part of these scores. References `26S5176-I.xlsx` and `26S5185-I.xlsx` have no same-identifier source/output. Sources `26S5177-D.pdf` and `26S8185-D.pdf` remain unpaired. No filename alias was introduced to improve the score.

| Measurement | Previous output | Current local default |
|---|---:|---:|
| Exact expected items recovered | 21/75 = 28.0% | **43/75 = 57.3%** |
| Exact generated item precision, paired files | 21/134 = 15.7% | **43/97 = 44.3%** |
| Item F1 | 20.1% | **50.0%** |
| Quantity/unit overlap, ignoring descriptions | 42/75 = 56.0% | **58/75 = 77.3%** |
| Complete matching item lists | 2/18 | **5/18** |
| Matching totals by unit | 7/18 | **12/18** |
| Files with zero exact item matches | 9/18 | **4/18** |
| Invoices matching all scored fields and items | 0/18 | **0/18** |

Exact item recall increased by 29.3 percentage points. There are still **32 missing or mismatched expected tuples** and **54 generated tuples without an exact reference match** in the paired files. The latter include split rows and different wording as well as genuine errors; they are not all invented goods. Quantity overlap and matching totals do not establish correct goods allocation.

Across all 20 outputs, there are 107 item rows, including four with an unresolved quantity or unit. The paired subset contains 97 rows, including three incomplete rows. These denominators must remain separate.

The prior 21/75 result included an Ollama-assisted correction on one invoice. The new complete batch used **no Ollama assistance**. These are development-set results; there is no untouched production holdout in this repository.

### Shipment fields

| Field | Previous agreement | Current agreement | Current limitation |
|---|---:|---:|---|
| Invoice number | 18/18 | 16/18 | Two conflicting identifiers left blank; no nonblank mismatch |
| Shipping marks | 18/18 | 18/18 | Includes existing directory inference; not pure OCR accuracy |
| Consignee name | 14/18 | 14/18 | Four differences, including factory-unit and abbreviation differences |
| Package count | 8/18 | 12/18 | Six blank; no nonblank mismatch |
| Gross shipment weight | 7/18 | 7/18 | Eleven blank; detail weights do not prove a complete gross total |
| Declared value | 0/18 | 0/18 | Eighteen blank; no supported valuation rule |
| Fixed export date | 0/8 | 0/8 | Eight blank; ten volatile TODAY() references excluded |

Invoice identifiers can still fall back to the existing filename convention when the document contains no usable identifier. That inference is recorded outside the printed invoice. If a readable identifier conflicts with the filename, or multiple source identifiers conflict, the identifier remains empty. This deliberately avoids silently replacing an uncertain reading with a filename-derived answer.

## What changed and why

1. **Use the source image resolution.** All 66 sample pages are scanned 300-DPI images; none contains native text. The new local default reads at 300 DPI, classifies page orientation and records the deskew transform. Later crops use exactly that transform.
2. **Recover table geometry before interpreting goods.** Existing OpenCV rules now handle slightly leaning borders. Long-line detection recovers columns missed by morphological filtering, including the difficult 12-page document. This prevents item details and quantity columns being flattened into a single text stream.
3. **Reread unresolved quantity cells with the same OCR model.** Readings must have a positive quantity and a source-consistent unit. Known complete values are preserved. No blanket S-to-5, O-to-0 or similar quantity substitution was added.
4. **Keep material context carefully.** Repeated sender labels no longer automatically erase a merged material heading. New senders and explicit new products still end that context. Header units can supply an explicit unit for numeric-only cells; otherwise the unit stays blank.
5. **Normalize compositions without inventing them.** Explicit percentage tokens tolerate narrow I/O recognition errors, fibers followed immediately by construction numbers are readable, and labelled shrinkage percentages are excluded from composition totals. Cotton descriptions omit BCI qualifiers for the existing invoice composition style; RECYCLE POLYESTER becomes RECYCLED POLYESTER. Original wording remains in OCR evidence. Unknown fibers and invalid composition totals are not forced into a known blend.
6. **Avoid extra goods from annotations.** Footer totals, packing instructions and repeated handwritten notes outside established tables no longer become arbitrary additional rows when goods have already been parsed. An unlabelled final numeric row that equals preceding same-unit goods is treated conservatively as a possible total and excluded, with an audit warning.
7. **Preserve the professional invoice display.** Unknown fields stay empty. No validation or intervention text is printed. Decimal quantities now display their available precision; values such as 8.125 G are no longer displayed as 8 G. Addresses have a usable merged width, carton ranges wrap, and quantities align with their descriptions. Continuation pages repeat the goods-column headings, avoiding the full address block on every page.

The existing writer, template selection and parser were reused. During project cleanup, obsolete Azure/EasyOCR backends, their CLI flags and their four backend-specific tests were removed. PaddleOCR is the single OCR path. Ollama remains optional. Failed experiment packages, unused models and duplicated caches were deleted; the installed project environment and three active models were retained.

## Local options actually tried

| Option | Evidence on this PC | Decision |
|---|---|---|
| Existing EasyOCR at higher resolution | A two-page 300-DPI trial took about 363 seconds and still read multiple 50-yard values as letters | Increasing resolution alone did not solve the problem |
| Full PP-StructureV3 | Initialized, then exited without a usable result in the trial | Not selected; the underlying failure cause was not established |
| Lightweight PaddleOCR | Fresh page OCR completed for all 20 PDFs; improved quantity readings and the final comparison above | Selected as the default local reader |
| Installed Ollama vision model | Earlier targeted crop trials took about 64–88 seconds each and included both useful readings and misses | Optional targeted fallback; not needed for the measured default batch |

This is the best result established by these local trials, not proof that every free model has been benchmarked. The remaining errors show that a larger model alone would not resolve missing business information or invoice grouping policy.

## Why the remaining items differ

Full per-file expected/missing/extra lists and field differences are in `../reports/accuracy.md`, with machine-readable evidence in `../reports/accuracy.json`.

| Area | Evidence | Next simple improvement |
|---|---|---|
| 5193: 11/19 expected items still differ | Several handwritten item labels are garbled; units are missing on a trim-card block; garment descriptions are scattered across cells | Reread the unresolved item/description cells only, retaining their coordinates and source text; establish explicit item-name mappings |
| 5189: 4/5 still differ | Lace quantities are present but a multi-quantity merged description cannot be allocated confidently; a color line is used instead of FELT PATCH | Repair merged-cell associations and carry the explicit product heading across continuation rows |
| 5192: 3/4 still differ | A single OCR box spans item and quantity columns, placing “2 GROSS” beside the item instead of in its quantity cell | Reread cells with text boxes crossing column boundaries; preserve multiple quantity/unit pairs |
| 5166, 5183 and 5195 | Most quantities are recovered; some material/color continuation rows still retain full detail wording | Tighten context boundaries using the table's physical merged regions, without guessing fibers |
| 5187 and 5190 | Correct quantity totals, but garment/gender wording differs from the manual summary | Define a small general garment-description convention using only explicit source evidence |
| 5157 and 5186 | Source detail wording differs from the manual FABRIC SWATCHES grouping; handwriting is weak | Use a short approved vocabulary and targeted label rereads, not a rule that every PCS fabric row is a swatch |
| 5194 | Quantity totals now match; one fabric-type field is not established and one row was recovered as a color description | Reread the missing fabric-type/product heading and associate it with its existing quantity |

Files 5193, 5189 and 5192 account for **18 of the 32** remaining expected-tuple mismatches. They are useful diagnosis targets because they expose general structural problems. The runtime contains no branches for those filenames.

Some strict mismatches should remain source-faithful: the source shows 8.125 G where a reference uses 8.12; another source shows 98% cotton/2% spandex where the reference says 90%/2%; the source spelling POLYAMIDE differs from a reference typo. These are not reasons to alter the extracted facts to match a workbook.

## Production independence and verification

- **47 active regression tests pass** in the isolated project environment. Dependency checking reports no broken requirements.
- All 20 workbooks pass page-coverage, merged-cell, invoice/audit parity and empty-field checks. Their main sheets contain no DRAFT, REVIEW REQUIRED, validation or human-intervention prompts.
- A fresh one-page OCR run used an anonymously renamed PDF, the blank template and copied application code in an isolated folder. A filesystem audit hook rejected reference-folder access. It generated three items (5, 5 and 8 SETS) and read S/5075/26 from the PDF. The measured run took about one minute including model startup. This proves that run did not need expected workbooks or filename recognition; it remains a known sample, not an unseen accuracy test. Evidence: `../reports/production_smoke.json`.
- Three final invoice sheets were opened read-only in installed Microsoft Excel and exported to PDF. Their print layout was inspected after correcting clipped addresses, rounded decimal quantities and continuation-page spacing. The checked outputs were 5075, 5166 and 5193; their final prints contain one, two and two pages respectively. This is not a visual inspection of all 20 outputs.

The earliest complete local candidate matched only 22/75 items. Geometry and shared parser fixes increased that to 43/75. This is why the next investment should target row associations and a small source-grounded item vocabulary before adding another general model or document framework.

## Run new PDFs

From the repository root:

```powershell
project/.venv/Scripts/python.exe project/run_batch.py --input-dir C:/shipments/incoming --output-dir C:/shipments/invoices
```

Only the input PDFs, installed local models, application code and blank template are required. The default cache contains OCR evidence, not expected answers. New PDF bytes receive new OCR results. Expected workbooks are read only when the separate evaluator is explicitly run.

## Recommended next step

Keep the current local architecture. First fix cross-column OCR boxes and physical merged-cell continuation, then add a small explicit vocabulary for swatches, cards, trims and garments. Evaluate those changes on an untouched set of new BD PDFs. Separately establish the rules for customs valuation, consignee factory units, package grouping and export dates; absent facts should continue to remain blank. No defensible percentage improvement on unseen PDFs can be promised before that evaluation.

Remaining limits: only this BD development set was benchmarked; India/Jordan and production load were not tested. The unlabelled-total safeguard is conservative and can exclude an ambiguous last row. OCR spelling and handwritten classification errors still appear in the generated invoices, so professional formatting does not establish production completeness.
