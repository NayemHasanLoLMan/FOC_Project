# Project structure and separation

Commands in these guides run from the repository root. The deployable application lives under project/.

~~~text
README.md                         Repository entry point
project/
  run_system.py                   Start scanner, worker and dashboard together
  main.py, run_batch.py            Production direct-conversion commands
  init_pipeline.py                 Production state initialization/migration
  scan_incoming.py, run_worker.py  Production intake/processing commands
  run_dashboard.py                 Production local web server
  src/foc_extractor/               Production backend Python code
  frontend/templates/             Dashboard HTML
  frontend/static/                Dashboard CSS and JavaScript
  development/analysis/           Development-only comparison/output/print tools
  development/postman/            Postman collection and local environment
  templates/                      Blank invoice templates; production inputs
  pipeline_config.json            Folder/worker configuration; production input
  valuation_rates.json            Approved approximate rates; production input
  requirements.txt                Supported direct dependency constraints
  requirements-lock.txt           Working Windows/Python environment pins
  docs/                           Current manuals and API specification
  tests/
    test_*.py                     Automated regression tests
  tools/
    build_release.py              Development-only production bundle builder
  examples/                       Canonical test PDFs, including regional subfolders
  expected_outputs/               Manually prepared reference invoices; test-only
  reports/                        Ignored QA reports and isolated test runs
  incoming/, output/              Ignored production arrivals/generated workbooks
  runtime/                        Ignored queue database and retained job artifacts
  .cache/                         Ignored source evidence and local OCR model files
  .venv/                          Ignored machine-specific Python environment
  dist/                           Ignored production ZIPs
~~~

Unit tests live under tests/; analysis implementations live under development/analysis/. Retired evaluation forwarding files are archived; use the canonical development/analysis/ commands. Completed documentation and old QA runs are archived outside the production tree. The build tool itself is development tooling, not application runtime.

Production depends on src, frontend, production CLI files, blank templates, rates, configuration and installed dependencies/models. No production module imports tests or evaluation tools. Source PDFs, manual reference invoices and generated QA reports never become runtime truth.

Canonical fixture paths remain examples/ and expected_outputs/. Moving them would break saved historical reports and established commands without improving runtime separation. The build allowlist excludes both folders, all tests/tools/development and all machine-local directories. Test fixtures are not copied into a release.

Runtime/evidence paths are deliberately not reorganized: SQLite attempts and receipts record those absolute paths and hashes. Existing caches, snapshots, invoices and dashboard demonstration jobs are preserved.

The production archive preserves the same repository-style command layout under foc-invoice/project/. It contains no environment, models, customer documents, live database or prior outputs. See [build](build.md) for the exact allowlist and verification.

See [safe removal boundaries](deployment-boundaries.md) and Postman instructions (`project/development/postman/README.md` in the development checkout).

The default managed inputs/outputs are incoming/bangladesh and output/bangladesh. Both parents also contain reserved india and jordan folders; Bangladesh and opt-in India processing are active. Jordan remains disabled.
