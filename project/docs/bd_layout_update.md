# Country folders and Bangladesh invoice layout - 21 October 2026

The normal command is unchanged:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py
~~~

Default production folders now are:

~~~text
project/
  incoming/
    bangladesh/    Active PDF inbox
    india/         Reserved
    jordan/        Reserved
  output/
    bangladesh/    Active generated Excel invoices and batch manifest
    india/         Reserved
    jordan/        Reserved
~~~

Initialization and the launcher create these directories. The Bangladesh worker scans only incoming/bangladesh. PDFs in India/Jordan folders cannot enter that queue. Their templates remain retained but processing is not enabled/validated by this update. Explicit custom configuration paths remain supported; historical demo configurations retain their existing report-directory paths.

main.py and run_batch.py now default to output/bangladesh, as do the canonical evaluation tools. Explicit --output-dir remains authoritative. The shared Python pipeline's omitted output_dir uses output/bangladesh relative to its working directory.

## Invoice behavior

- BIN lines print consistently as BIN : identifier, without enclosing brackets. Digits, leading zeros and hyphens are preserved; the BIN line is red.
- Shipping-mark C/NO values and goods carton references are red. The C/NO label stays black using Excel rich text; the stored visible text remains the same.
- Labelled PDF TINs print in red above the customs-purpose footer, preserving meaningful suffixes such as /CIRCLE-50. Material descriptions such as copper tin 3 do not qualify as TINs. Conflicting identifiers stay blank.
- A PDF-provided import open cover note prints in red above the customs invoice number, with wrapping. It is never taken from the expected workbook or inferred from a consignee.
- Bangladesh net weight is not extracted, printed, added to its audit sheet, listed as missing, or shown in the latest BD detail header. The shared net-weight model/helper remains for other regions.

These are reusable parser/writer rules for future PDFs, with no shipment-ID answers or manual per-invoice formatting patch. The stable blank templates were preserved byte-for-byte: dynamic labels/optional rows and rich-text color belong to the shared writer because their positions depend on each invoice.

The user explicitly selected PDF-only TIN/cover-note values. Eight of the 20 test PDFs provide usable labelled TINs in extracted source text. No current test PDF provides a usable import cover note in that text, so all real invoice notes stay empty. Some manually prepared references contain those values despite their absence from available PDF text. Nothing was copied from those references. A separate synthetic note was used only in a QA report workbook to verify placement/wrapping.

## Preservation and verification

| Check | Result |
|---|---|
| Complete suite | 233 passed |
| Existing examples regenerated | 20 invoices / 66 pages / 89 goods rows |
| Core invoice facts | Goods, quantities, dates, consignee, shipping marks, package totals, gross weight and valuation unchanged |
| Net weight omission | All 20 BD outputs and audits omit it |
| Optional tax metadata | 8 source-backed TINs, 0 fabricated cover notes |
| Region isolation | Bangladesh scanner ignores India/Jordan sibling PDFs |
| Native Excel print QA | 5166: 1 page; 5193: 2 pages; synthetic cover note: 1 page; rendered and visually inspected |
| Source-dependent fields | Tested on unknown filenames, long goods tables, labelled/conflicting TINs, suffixes and missing notes |
| Demo queue refresh | 20 explicit Stage 6 reprocesses; all completed, 40 total historical/current attempts, earlier invoices retained |
| Existing/new download links | Passed; detail shows TIN and omits BD net weight |

The former 20 standalone test workbooks and batch manifest were moved without overwriting to project/reports/bd_layout_20261021/previous_flat_output, with hashes checked before/after. Regenerated outputs are in output/bangladesh. Immutable queue snapshots, recorded historical paths, previous managed outputs and manual reference workbooks were preserved. Excel owner-lock files are not moved or processed.

Default production state remains empty; the browser's existing demonstration queue uses its explicitly selected Stage 5 report configuration. It was restarted through the same single-command launcher. No new startup service/task or Stage 7 work was enabled.

QA evidence is in project/reports/bd_layout_20261021: verification.json, metadata_coverage.json, output_relocation.json, comparison/ and print_check/. Legacy manual-reference goods scores remain 58/75 recall and 58/82 precision; this update does not claim better goods accuracy. The BD evaluator no longer treats net weight as a required comparison field.

Limitations: India/Jordan processing and fresh unseen-document accuracy were not validated. Source OCR/model caches were reused; limited narrow OCR still initializes installed models. The optional cover-note extraction is unit-tested and print-tested but current real PDFs do not exercise a positive note case. Missing source information remains empty under the approved rule.
