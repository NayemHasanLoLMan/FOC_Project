# Local PDF to Excel invoice

Read shipment PDFs with local PaddleOCR and fill the existing Excel invoice template. Bangladesh is the tested scope. India/Jordan templates, mappings and unique reference documents are retained for later work; they have not been validated by the BD benchmark.

The [continuous folder pipeline and admin dashboard checklist](docs/pipeline_dashboard_plan.md) tracks staged updates. [Stage 1](docs/pipeline_stage1.md) adds configuration and durable job state; [Stage 2](docs/pipeline_stage2.md) adds a continuous folder scanner that queues safe PDF snapshots. It does not convert queued jobs yet. No scanner is left running or installed at startup; the processing worker and dashboard are later stages. Current CLI conversion remains unchanged. Each next stage requires user approval after regression checks.

## Project layout

```text
project/
  main.py                    Convert one PDF
  run_batch.py               Convert a folder of PDFs
  init_pipeline.py           Initialize empty pipeline state; no processing
  scan_incoming.py           Continuously queue stable PDFs; no extraction yet
  pipeline_config.json       Folder-pipeline configuration
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
    pipeline_config.py       Validated configuration and version snapshots
    job_store.py             Durable jobs, attempts and transition events
    folder_intake.py         File readiness, PDF validation and versioned snapshots
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
  incoming/                  Configured default inbox (ignored)
  reports/                   Latest comparison and verification (ignored)
  runtime/                   Local pipeline database/artifacts (ignored)
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

To validate the future folder-worker configuration and initialize its empty database, run `project/.venv/Scripts/python.exe project/init_pipeline.py` from the repository root. Paths in `pipeline_config.json` resolve relative to that file. This command does not watch folders, process PDFs or start a service. See the [Stage 1 report](docs/pipeline_stage1.md).

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

## Folder intake — Stage 2

Run the scanner from the repository root:

```powershell
project/.venv/Scripts/python.exe project/scan_incoming.py
```

It checks the folder configured in `pipeline_config.json` (default `project/incoming`), prints JSON status, and continues until Ctrl+C. `--once` scans once and exits; `--config <path>` selects another configuration. New PDFs need matching observations at least one scan interval apart (default five seconds), so the first scan normally reports waiting files. The next scan occurs after the previous scan finishes plus the configured interval.

The scanner ignores temporary files, symbolic links and subfolders. It checks PDF completion/readability, saves verified original-name snapshots under `runtime/artifacts/inputs`, and queues each source-identity/content version once. Invalid/password-protected/repair-required PDFs remain recorded as rejected; changed bytes are checked again. Missing/locked files do not discard existing snapshots/jobs. A temporary final rename is the preferred producer handoff; no stability heuristic proves a writer has finished.

**This stage only queues PDFs.** Invoice generation from the queue starts with Stage 3, which still requires approval. Existing `main.py` and `run_batch.py` can still convert PDFs directly. See the [Stage 2 acceptance report](docs/pipeline_stage2.md).

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

`templates/BD_template.xlsx` is the shared master for future BD invoices, used by both single-file and batch conversion. It owns fonts, colors, alignment, borders, column widths and the base layout. Red highlights gross/net weights, total value and the customs-purpose note; blue highlights invoice number and destination country, preserving the original convention. Text/descriptions align left, quantities/weights/value align right, and package counts align centrally. The generator inherits these styles when adding goods rows and shifting the total/footer, so no per-invoice styling step is needed.

The master uses consistent Arial typography, neutral section rules, a shaded goods header and total, and A4 portrait printing. The existing invoice sections and data anchors are preserved. Goods rows grow for wrapped descriptions; unused address/net-weight space is reduced. Continuation pages repeat the goods header, company/invoice identification and page count. Internal audit sheets remain available. The presentation change does not alter extraction or valuation rules. See the [template quality checks](reports/template_quality_20261020/RESULTS.md).

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

## Local vision fallback

The installed `qwen3-vl:latest` model is enabled by default in single-file and batch conversion. PaddleOCR remains the first reader. Local vision handles unresolved goods quantity strings, unreadable package numbers with an established package unit, and physical weight cells on an ambiguous packing-list page. Readable integer goods counts and established values are preserved; existing source-context rules handle their units.

Ollama must be running on `127.0.0.1:11434`. The application never downloads a model. Select another installed vision model or disable vision explicitly:

```powershell
project/.venv/Scripts/python.exe project/run_batch.py --local-model qwen3-vl:latest
project/.venv/Scripts/python.exe project/run_batch.py --no-local-vision
```

Weight images include the PDF's KG header and a single physical cell; the model returns only the final numeric weight, excluding a cancelled printed value. A failed page is rechecked by physical cell so a readable but cancelled old number cannot survive alongside a recovered correction. Physical shared cells count once. Gross is populated only from a complete positive finite weight sum; explicit gross declarations retain priority. A failed model reading leaves the field unresolved. Missing net weights and other facts absent from the PDF are not inferred.

Requests allow 4,096 output tokens, an 8,192-token context and a two-hour timeout. Only completed structured answers are accepted. Cache keys include source-image pixels, model digest, prompt, schema and generation settings. Source coordinates/model provenance are retained in weight/package evidence; diagnostics stay outside the printed invoice. When Ollama is unavailable, supported OCR results remain usable and unresolved fields stay empty. The model must still be available to establish its digest when reusing responses.

The first uncached readings are slow on this CPU; better hardware remains a productivity improvement to benchmark later. Cached responses avoid repeating model generation. [Integration QA and current limitations](reports/local_vision_integration_20261020/RESULTS.md) distinguish field completeness, source agreement and reference agreement. Development test results do not guarantee unseen-handwriting accuracy.
