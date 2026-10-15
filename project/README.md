# BD PDF to customs invoice

Extract shipment and packing-list PDFs into the existing `templates/BD_template.xlsx` design. The current improvement and regression scope is Bangladesh. India/Jordan mappings remain legacy paths and have not been validated by this BD run.

The extraction path never reads `expected_outputs` or `FOC`. Those manually prepared workbooks are used only by the separate evaluator. There are no per-invoice corrections or filename aliases in extraction. New input documents use the same rules.

## Run

Use Python 3.10+ and install the existing dependencies in `requirements.txt`. EasyOCR uses its local English model; initial setup may download the model if it is absent. Azure requires the environment variables shown in `.env.example`.

```powershell
python project/run_all_samples.py --backend easyocr
python project/verify_extraction.py
python -m unittest discover -s project/tests -v
```

Batch defaults are resolved relative to the project, regardless of the working directory. PDFs are read from `examples`, invoices are written to `output`, and the evaluator writes `reports/accuracy.md` and `reports/accuracy.json`. `output/run_manifest.json` distinguishes written files from failures. The previous outputs for this development comparison are preserved under `reports/baseline`.

For new production files:

```powershell
python project/run_all_samples.py --input-dir C:/shipments/incoming --output-dir C:/shipments/invoices --backend easyocr
```

For one document:

```powershell
python project/main.py --pdf C:/shipments/incoming/document.pdf --template project/templates/BD_template.xlsx --output-dir project/output --backend easyocr --cache-dir project/.cache/ocr
```

All pages are processed by default. `--max-pages` is an explicit diagnostic limit for local OCR and produces an incomplete-coverage warning. Do not use it for production invoices. The legacy Azure path currently analyzes the whole document.

## How extraction works

1. EasyOCR reads the correctly oriented, deskewed page. Existing OpenCV detects table grid lines. Quantity, package and weight cells receive focused OCR rereads.
2. The parser identifies columns by headers, separates administrative fields from goods, retains quantities with their units, and aggregates equivalent material/unit rows.
3. Explicit shipment totals take priority over carton inference. Conflicts are recorded rather than silently resolved. Known consignee aliases can normalize names and supply directory shipping marks, with a warning for inferred marks. Addresses are read from labelled source blocks rather than blindly assigning one factory's address to every unit.
4. The BD writer grows the item area and moves totals/footer. Every extracted item is written to the invoice and the audit sheet. Dates and amounts use typed Excel values.

OCR caches are keyed by source bytes, backend, model, page limit and extraction settings. Page checkpoints make interrupted local runs resumable. The cache contains OCR text, coordinates and table cells, not expected answers. To force fresh OCR, choose a new `--cache-dir`. Parsed outputs are regenerated from cached OCR, so parser changes do not require another OCR run.

## Missing data and review

Missing dates, goods, weights or declared values are not replaced with invented defaults. An ambiguous slash date remains blank. A filename-derived invoice identifier is explicitly warned. Packing-list weight may differ from gross shipment weight and is labelled for review. Declared value stays blank/review-required unless established from the source; the former universal USD 40/1 fallback is removed.

Outputs with warnings are visibly marked **DRAFT - REVIEW REQUIRED**. Review `Extraction_Audit` before using them. A written Excel file is not an accuracy PASS. Raw OCR evidence lives in the cache; `--save-json` on the single-file command exports parsed data, not raw OCR.

## Measuring accuracy

The evaluator inspects the main invoice sheet, not just its audit. It checks business fields and exact normalized description/quantity/unit tuples, preserves missing/extra items, checks audit-to-invoice parity, and reports unmatched reference coverage. It uses same-name matches first, then a unique extracted invoice identifier; it never silently aliases sample filenames.

`TODAY()` reference dates are excluded from fixed-date scoring. Source-versus-manual-reference differences are not automatically corrected. In particular, customs valuations, factory master data and manually summarized descriptions require approved rules when absent or different in the PDF.

These examples are a development set. Their results do not establish accuracy on unseen documents. Keep a separate, untouched BD holdout set for production acceptance.

CLI arguments are the active configuration. The legacy `config/project.yaml` is not read by this implementation. No new dependencies or extraction service have been introduced.
