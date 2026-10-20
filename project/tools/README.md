# Development and release tools

No file in this folder is required by a running production application.

- build_release.py: standard-library production ZIP builder.
- compare_invoices.py, check_outputs.py, export_print_samples.ps1: legacy evaluation entry points; implementations now live in tests/evaluation.

Existing tool command paths and Python comparison imports remain compatible. Production builds exclude this entire folder and all tests, fixture PDFs, manual references, reports, local models, environments and runtime data. See [build and release](../docs/build.md).
