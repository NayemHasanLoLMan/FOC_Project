# Tests and development evaluation

This entire directory is development-only and is excluded from production builds.

- test_*.py: automated regression tests using Python unittest.
- ../development/postman/: importable API collection and local environment.
- ../examples/: canonical test PDFs, kept at their existing paths for compatibility.
- ../expected_outputs/: manual reference invoices, evaluation only.
- ../reports/: generated test reports and isolated acceptance runs; never ship these as production inputs.

From the repository root:

~~~powershell
project/.venv/Scripts/python.exe -m unittest discover -s project/tests -q
project/.venv/Scripts/python.exe project/development/analysis/compare_invoices.py
project/.venv/Scripts/python.exe project/development/analysis/check_outputs.py
~~~

Run analysis commands from project/development/analysis/. Production code does not import this package. See [testing](../docs/testing.md) for scope, fixtures and interpretation of reference scores.
