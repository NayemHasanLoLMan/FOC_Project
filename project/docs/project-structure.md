# Project structure and separation

Commands in these guides run from the repository root. The deployable application lives under project/.

~~~text
README.md                         Repository entry point
project/
  main.py, run_batch.py            Production direct-conversion commands
  init_pipeline.py                 Production state initialization/migration
  scan_incoming.py, run_worker.py  Production intake/processing commands
  run_dashboard.py                 Production local web server
  src/foc_extractor/               Production Python code, HTML, CSS and JavaScript
  templates/                      Blank invoice templates; production inputs
  pipeline_config.json            Folder/worker configuration; production input
  valuation_rates.json            Approved approximate rates; production input
  requirements.txt                Supported direct dependency constraints
  requirements-lock.txt           Working Windows/Python environment pins
  docs/                           Current manuals, API specification and historical notes
  tests/
    test_*.py                     Automated regression tests
    evaluation/                   Reference comparison, output and print QA implementations
  tools/
    build_release.py              Development-only production bundle builder
    compare_invoices.py           Legacy evaluation compatibility entry point
    check_outputs.py              Legacy evaluation compatibility entry point
    export_print_samples.ps1      Legacy evaluation compatibility entry point
  examples/                       Canonical test PDFs, including regional subfolders
  expected_outputs/               Manually prepared reference invoices; test-only
  reports/                        Ignored QA reports and isolated test runs
  incoming/, output/              Ignored production arrivals/generated workbooks
  runtime/                        Ignored queue database and retained job artifacts
  .cache/                         Ignored source evidence and local OCR model files
  .venv/                          Ignored machine-specific Python environment
  dist/                           Ignored production ZIPs
~~~

All unit/evaluation implementation code is under tests/. The three old evaluation paths under tools/ forward to the new implementations so existing commands and Python comparison imports still work. Native Excel print export also forwards to the same separated implementation. The build tool itself is development tooling, not application runtime.

Production depends on src, production CLI files, blank templates, rates, configuration and installed dependencies/models. No production module imports tests or evaluation tools. Source PDFs, manual reference invoices and generated QA reports never become runtime truth.

Canonical fixture paths remain examples/ and expected_outputs/. Moving them would break saved historical reports and established commands without improving runtime separation. The build allowlist excludes both folders, all tests/tools and all machine-local directories. Test fixtures are not copied into a release.

Runtime/evidence paths are deliberately not reorganized: SQLite attempts and receipts record those absolute paths and hashes. Existing caches, snapshots, invoices and dashboard demonstration jobs are preserved.

The production archive preserves the same repository-style command layout under foc-invoice/project/. It contains no environment, models, customer documents, live database or prior outputs. See [build](build.md) for the exact allowlist and verification.
