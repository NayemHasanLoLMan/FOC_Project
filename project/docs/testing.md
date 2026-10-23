# Testing and evaluation

All automated tests are in tests/test_*.py. Evaluation implementations live under development/analysis/. Use these canonical paths; obsolete tools/ forwarding files are archived.

## Commands

~~~powershell
project/.venv/Scripts/python.exe -m unittest discover -s project/tests -q
project/.venv/Scripts/python.exe -m unittest discover -s project/tests -p test_dashboard.py -v
project/.venv/Scripts/python.exe project/development/analysis/compare_invoices.py
project/.venv/Scripts/python.exe project/development/analysis/check_outputs.py
~~~

compare_invoices.py accepts --output-dir, --expected-dir, --report-dir and optional --baseline-dir. Defaults preserve project/output, expected_outputs and reports. It reads invoice values rather than trusting audit rows. Comparison writes accuracy.json/accuracy.md under the report directory, not the invoices.

check_outputs.py checks the canonical development outputs against examples and their audit/page coverage, merged-cell overlap, #REF errors, total position and prohibited printed warning text. It writes reports/validation.json. It does not generate invoices.

For optional native Excel print QA:

~~~powershell
& project/development/analysis/export_print_samples.ps1 -Invoices project/output/bangladesh/26S5166-I.xlsx,project/output/bangladesh/26S5193-I.xlsx
~~~

The script starts its own hidden Excel instance, opens workbooks read-only, exports the first worksheet to PDF and closes that instance. It requires Windows and installed Excel; it does not close the user's existing Excel application. Default PDFs go to project/reports/print_check.

## Test ownership

Parser/source-goods/number tests cover supported extraction rules. OCR tests cover geometry/cache behavior with controlled readers. Weight/package/vision tests cover physical cells and fallback acceptance. Writer tests verify workbook facts/styles and literal source strings. Valuation tests verify source quantity preservation, rule matching and rounding.

State/intake/worker tests cover schema migration, ownership, duplicates, partial input, process locks, crash checkpoints, publication races, blocked saves and recovery. Evidence tests cover exact PNG bytes, model/cache distinction, rejected/failed calls, provenance and safe previews. Dashboard tests cover read-only behavior, routes/filters/downloads, stale health, concurrency, security boundaries and plain-language explanations.

The suite largely uses isolated temporary directories and controlled OCR/model responses. It is not a full fresh-model benchmark. Canonical PDFs/manual Excel references stay in examples/ and expected_outputs/ to keep existing tools/reports stable; India has one verified real shipment; unseen India PDFs and Jordan acceptance remain pending.

## Meaningful real-PDF acceptance

1. Use an isolated config with distinct incoming/output/state/artifact folders; never point tests at production state.
2. Keep original PDF names. Scan twice after the readiness interval, or run the continuous scanner.
3. Drain the queue while polling the dashboard. Check full source page coverage, source hashes, goods completeness, supported fields and all file/evidence links.
4. Restart the worker and verify no duplicate attempts/output overwrites.
5. Compare invoice values/styles/print settings with the prior baseline. Use manual references only for evaluation.
6. Evaluate unseen and renamed PDFs with fresh OCR/model inference before a production accuracy claim.

Do not alter canonical expected workbooks or tune shipment-specific answers to improve a score. PDF-correct differences may be valid. Strict goods recall/precision, field matches, coverage and print layout measure different things; there is no single proven universal invoice accuracy percentage.

The latest available-sample release gate passed 454 tests and preserved all 21 original production invoices (20 Bangladesh, one India). Older goods-match percentages are historical milestones, not a current universal accuracy score. See [readiness](readiness.md).

Generated reports contain shipment text/images and remain ignored. Historical verification scripts in reports are QA artifacts, not production modules or supported application entry points.

Stage 6 tests cover pause during active conversion, restart persistence, concurrent request replay, stale/foreign attempts, preserved output versions, save-only recovery while paused, schema migration, JSON/Origin/CSRF protection and read-only GET behavior.
