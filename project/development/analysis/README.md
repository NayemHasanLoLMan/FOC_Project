# Analysis tools

Run from the repository root:

~~~powershell
project/.venv/Scripts/python.exe project/development/analysis/compare_invoices.py
project/.venv/Scripts/python.exe project/development/analysis/check_outputs.py
& project/development/analysis/export_print_samples.ps1 -Invoices project/output/bangladesh/26S5166-I.xlsx
~~~

These tools read generated workbooks and development fixtures. They never supply production extraction answers. Comparison accepts --output-dir, --expected-dir, --report-dir and --baseline-dir. Output checks write project/reports/validation.json; print QA needs installed Excel. Existing tools/ commands remain compatibility entry points; the redundant tests/evaluation/ forwarding layer was removed.

See [testing](../../docs/testing.md) for coverage and interpretation.
