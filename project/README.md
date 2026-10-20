# Local PDF to Excel invoice

Read shipment PDFs with local PaddleOCR and fill the existing Excel invoice template. Bangladesh is the tested scope. India/Jordan templates, mappings and unique reference documents are retained for later work; they have not been validated by the BD benchmark.

## Project layout

```text
project/
  main.py                    Convert one PDF
  run_batch.py               Convert a folder of PDFs
  requirements.txt           Runtime dependencies
  src/foc_extractor/
    ocr_engine.py            Page OCR, table geometry and caching
    parser.py                Source-grounded shipment and item parsing
    models.py                Shipment and line-item data
    excel_writer.py          Existing template population
    pipeline.py              Shared conversion workflow
    weights.py               Packing weight cells, shared-cell totals and evidence
    packages.py              PDF container totals, physical shared cells and evidence
    local_vision.py          Optional Ollama quantity-cell transcription
  tools/
    compare_invoices.py      Read-only comparison with manual references
    check_outputs.py         Sample coverage, audit and invoice checks
    export_print_samples.ps1 Read-only Excel-to-PDF print check
  tests/                     Parser, OCR, Excel and local-vision tests
  examples/                  BD PDFs; india/ and jordan/ hold other samples
  expected_outputs/          Manual references; evaluation only
  templates/                 Blank BD, India and Jordan invoice templates
  docs/diagnosis.md          Accuracy, known errors and next-stage priorities
  output/                    Generated invoices and batch manifest (ignored)
  reports/                   Latest comparison and verification (ignored)
  .cache/                    Active OCR evidence and local models (ignored)
  .venv/                     Project Python environment (ignored)
```

Source PDFs and manual references have one canonical location. The former root `FOC` copies were deduplicated by file hashes. All unique regional documents were preserved.

## Setup

Use Python 3.12, tested on this Windows PC. Run these commands from the repository root:

```powershell
python -m venv project/.venv
project/.venv/Scripts/python.exe -m pip install -r project/requirements.txt
```

The working environment and the three required OCR models are already installed on this PC. A new installation downloads dependencies/model weights once; document processing runs locally. PaddleOCR is the single supported OCR engine. Obsolete Azure/EasyOCR backends, backend-selection flags and Azure environment setup have been removed.

## Convert PDFs

Process the BD examples into `project/output`:

```powershell
project/.venv/Scripts/python.exe project/run_batch.py
```

Use new production PDFs:

```powershell
project/.venv/Scripts/python.exe project/run_batch.py --input-dir C:/shipments/incoming --output-dir C:/shipments/invoices
```

Convert one document:

```powershell
project/.venv/Scripts/python.exe project/main.py --pdf C:/shipments/incoming/document.pdf
```

Single-file and batch defaults resolve to this project's output/cache folders, regardless of the current directory. `--template` on the single-file command selects an explicit blank template. `--save-json` saves parsed data beside the single-file invoice. All pages are processed unless the diagnostic `--max-pages` option is supplied. `output/run_manifest.json` records each batch success or failure.

OCR caches contain source text, coordinates and table cells. Cache keys include the source bytes and OCR settings. A different `--cache-dir` forces fresh OCR. Parser changes reuse existing OCR evidence. Preserve `.cache/paddlex` to avoid downloading model weights again.

## Verification

```powershell
project/.venv/Scripts/python.exe -m unittest discover -s project/tests -v
project/.venv/Scripts/python.exe project/tools/compare_invoices.py
project/.venv/Scripts/python.exe project/tools/check_outputs.py
```

The comparison writes `reports/accuracy.md` and `reports/accuracy.json`. It reads the actual invoice sheet and checks exact normalized description/quantity/unit tuples. Quantity overlap is a separate diagnostic. Optional `--output-dir`, `--expected-dir`, `--report-dir` and `--baseline-dir` parameters support explicit comparisons. The sample output checker verifies all source pages were processed, audit rows agree with printed invoice cells, missing values remain blank, and no validation prompts appear on the invoice.

For a native Excel print check, with desktop Excel installed:

```powershell
project/tools/export_print_samples.ps1 -Invoices project/output/26S5075-I.xlsx
```

The tool opens the chosen workbooks read-only with macros disabled and exports their first invoice sheets to `reports/print_check`.

The [shared processing flow](docs/processing_flow.md) documents source ownership, conservative fallback and remaining production acceptance gates.

## Extraction rules and limits

- Production conversion reads PDFs, blank templates, maintained company information and approved valuation rates. It never reads `expected_outputs` or evaluation reports.
- BD estimates use the editable [valuation rates](valuation_rates.json): USD 0.20/YDS for recognized fabric and the approved product/unit rates for trims and garments. Quantities stay source-derived; confirmed small-button G means GROSS. Line amounts round to cents; the complete total rounds to whole USD (half up). Explicit source values take priority. Unknown rows or incomplete page processing leave the estimated shipment total empty. Integer counts of explicitly named cards may infer PCS, recorded in the audit; other unknown units stay empty. The invoice keeps its total-only layout; unit prices/line amounts are in Extracted_Items. General sample/garment rates cover recognizable categories without inventing exact subtypes. The shared mould default is USD 0.72/set, revised from USD 10/set using the explicit Rose reference rate; this cannot reproduce the earlier mixed-shipment mould estimate. These rates are development-calibrated assumptions, not market prices. See the [valuation results](reports/valuation_expanded_20261019/RESULTS.md) for coverage and reference differences.
- Explicit export/shipment dates take priority. When there is no explicit export-date label, use the first packing-list page with a labelled date; later enclosures may have different dates. Numeric packing-list dates use month/day/year, matching these source forms. Invalid dates or conflicting dates on that selected page stay empty. Explicit numeric export dates remain ambiguous unless their day/month order is clear. No current-date or next-day assumption is used.
- Explicit declared gross weights take priority. Under the approved fallback rule, a complete packing-list weight sum fills G.W. without an added packaging allowance or rounding. Local PaddleOCR rereads weight cells and counts shared physical cells once; unreadable, conflicting, missing or incomplete weight evidence leaves the total blank. Source-keyed weight evidence is cached under `.cache/ocr/weights`. Weight is never used to invent an outer-carton count. Other unavailable values remain empty.
- Explicit items and source compositions drive grouping. Source-context FAB annotations may supply a broad FABRIC SAMPLES category without asserting an unreadable subtype. Numbered garments split only when inline quantities conserve the declared total. Matching complete garment notes immediately below the last table row can refine that item; unrelated page text cannot create goods. BCI cotton uses the existing invoice's cotton naming convention; RECYCLE POLYESTER is standardized to RECYCLED POLYESTER. Original text stays in OCR evidence. Invalid blends and unknown fibers are not forced into a known composition.
- Invoice numbers use best-effort selection: prefer a PDF reading matching the invoice-style filename; otherwise use the most repeated PDF reading (first on ties). A lone reading may use a same-length filename within two character substitutions. With no PDF number, use the invoice-style filename. Disagreement no longer clears the number; selection is recorded internally. With no recognizable number in either source, keep it empty. See the [invoice-number results](reports/invoice_number_fix_20261020/RESULTS.md).
- The BD goods-table C/NO column lists shipment carton ranges on separate lines. When no range exists, an established package count supplies the PKGS label (a bare count in Rose's format). Package totals prefer an explicit shipment total, then carton ranges, then distinct explicit carton IDs or readable package entries across all pages. Shared physical cells count once; equal numbers on different pages remain separate unless the same explicit carton ID repeats. Packs, cartons, boxes, rolls and bags are counted as declared containers. Local PaddleOCR rereads package cells, including clipped columns. An unreadable declared count leaves the total empty; no consolidation is inferred from weights. These PDF container counts may differ from the manual outer-carton total. See the [package-count results](reports/package_count_fix_20261020/RESULTS.md).
- Consignee addresses and BINs come from the labelled source block first. When absent, identified companies use the existing maintained directory, including a separate EPIC Unit-2 profile; the fallback is recorded internally. Unknown companies/units do not receive another factory's address. Keep this company directory current when factory details change; expected workbooks are never read during conversion.
- The printed invoice contains no DRAFT, REVIEW REQUIRED, validation prompts or human-intervention text. Diagnostics stay outside it. Source strings are literal Excel text, and workbook saves replace the destination only after a temporary workbook is written successfully.

The current BD development set has **58/75 strict expected-item matches (77.3%)**, with **70.7% generated-item precision (58/82 paired generated rows)**. Strict differences include source-correct GROSS units/precision, sample wording, and manually grouped or conflicting quantities. The [PDF-priority verification](reports/pdf_priority_20261019/RESULTS.md) records the evidence and reference exceptions. All **89/89 resulting goods rows** have quantities, units and prices, with calculated totals in **20/20 outputs**. Grouping reduced row count while preserving source quantity totals and row references. Fourteen of 18 paired totals equal the manual values; 17 of 18 paired totals are within USD 1. 5193 now uses the source-counted trim cards and separate kids jacket/dress; its total is USD 69 versus manual USD 80. Context-inferred units and approximate names are recorded internally. These results do not establish accuracy on unseen PDFs. See [the diagnosis](docs/diagnosis.md) for the remaining structural and business-rule gaps. See the [current repair checklist](reports/carton_fix_20261019/CHECKLIST.md) for completed fixes, current metrics and the next task.

## Optional Ollama

An already installed **vision-capable** Ollama model can transcribe unresolved quantity cells:

```powershell
project/.venv/Scripts/python.exe project/run_batch.py --local-model qwen3.5:4b
```

Ollama must be running on `127.0.0.1:11434`. The application never downloads an Ollama model. Only located, unresolved quantity crops are submitted; known quantities are preserved. Responses must be positive quantities with a source-consistent unit. Invalid or timed-out readings leave the existing result intact. Requests are bounded to 7,200 seconds (two hours), allow up to 4,096 output tokens with an 8,192-token context, and are cached by model digest, prompt and crop. This optional path was not used for the current full-batch accuracy score.

Local vision is a promising fallback for difficult handwriting. The installed Qwen3-VL read the confirmed package digit in the development probe, but its CPU-only run took 24 minutes 40 seconds and exhausted the old 96-token limit before returning final JSON. The output limit is now 512 tokens. A new isolated-package test returned valid JSON with 1 PKS in 3m 34s, but combined readings and an isolated corrected-weight test still exhausted the limit without final output. Practical productivity will require better hardware and a benchmark with GPU offload, or a faster model. Hardware speed does not establish extraction accuracy. Package-cell vision remains a tested research direction, not an integrated production fallback. See the [local-vision findings and hardware note](reports/package_handwriting_20261020/RESULTS.md).

Latest [512-token validation results](reports/vision_validation_512_20261020/RESULTS.md): the package-cell control works, but corrected-weight extraction is not reliable yet. Better hardware addresses productivity; repetitive reasoning and final-output reliability require separate improvements.

Latest [corrected-weight capability test](reports/weight_vision_4096_20261020/RESULTS.md): all five reviewed corrections returned correct final numbers (25, 12, 8.5, 8.5 and 10 kg) with isolated cells, their PDF KG headers and a numeric-only prompt. The transport now allows 4,096 output tokens, an 8,192-token context and two hours. All successful readings used fewer than 512 tokens; prompt/context clarity matters. This weight fallback is not integrated into production yet, and unseen accuracy remains unmeasured. Earlier 512-token failures above are historical benchmark results.
