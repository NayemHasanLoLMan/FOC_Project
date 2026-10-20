# Local PDF to invoice

The application lives in **[project](project/README.md)**. It converts shipment PDFs into the supplied Excel invoice templates using local PaddleOCR.

- `project/src/foc_extractor/` — OCR, parsing and invoice generation
- `project/tools/` — comparison and output checks
- `project/tests/` — regression tests
- `project/examples/` — source PDFs
- `project/expected_outputs/` — manually prepared test references
- `project/templates/` — blank invoice templates
- `project/output/` — generated invoices
- `project/docs/diagnosis.md` — measured accuracy and the next improvement priorities

Run from this repository root:

```powershell
project/.venv/Scripts/python.exe project/run_batch.py
```

See the application README for setup, production input folders and verification commands. Manual reference workbooks are used only by the evaluation tools.
