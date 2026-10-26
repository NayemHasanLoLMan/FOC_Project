# FOC invoice automation

Local shipment PDF → Excel invoice automation with PaddleOCR, selective Ollama vision, a durable folder queue and an admin dashboard. Bangladesh and opt-in India are implemented. Jordan is the next regional implementation; its watched folder remains disabled.

## Start

From the repository root, run the entire system with one command:

```powershell
project/.venv/Scripts/python.exe project/run_system.py
```

Open http://127.0.0.1:8080/. Drop PDFs into the configured country inbox. The scanner waits for a stable file, the worker creates the invoice and the dashboard provides View, Edit, Preview Excel and Download. Closing the browser does not stop processing. Ctrl+C waits for the active invoice before shutdown. If Windows background startup is already running, use that instance instead of starting a second one; see [operations](project/docs/operations.md#windows-background-operation).

| Country | Default incoming folder | Default output folder | Status |
|---|---|---|---|
| Bangladesh | `project/incoming/bangladesh/` | `project/output/bangladesh/` | Enabled |
| India | `project/incoming/india/` | `project/output/india/` | Opt-in through System settings |
| Jordan | `project/incoming/jordan/` | `project/output/jordan/` | Reserved; disabled |

Production uses PDFs and maintained configuration/rates; it never reads manual expected invoices. Unsupported information stays blank on professional invoices. Existing published files and evidence are preserved when creating new versions.

## Install

Supported baseline: Windows x64 and Python 3.12 with **SQLite 3.51.3 or newer** (check the Python build's bundled SQLite). The current tested runtime uses SQLite 3.53.1. Patched SQLite is required before enabling concurrent WAL state; earlier versions have a documented [WAL-reset defect](https://sqlite.org/wal.html#walresetbug). From the repository/release root:

```powershell
py -3.12 -m venv project/.venv
project/.venv/Scripts/python.exe -c "import sqlite3; print(sqlite3.sqlite_version); assert sqlite3.sqlite_version_info >= (3, 51, 3)"
project/.venv/Scripts/python.exe -m pip install -r project/requirements-lock.txt
project/.venv/Scripts/python.exe -m pip check
```

The lock is a working Windows dependency snapshot, not an offline wheel bundle or hash-enforced lock. Use a separate environment and rerun acceptance before changing dependencies. Excel is not required to generate invoices or run the dashboard; it is used for native print-layout QA. No Azure subscription or paid service is required.

PaddleOCR uses PP-OCRv5 mobile detection, English recognition and page orientation. First initialization may download models; subsequent runs reuse `project/.cache/paddlex/`. Provision models and verify a real PDF before assuming offline readiness.

Install Ollama using its [Windows instructions](https://docs.ollama.com/windows). Its local API is expected at 127.0.0.1:11434. Check installed models and provision the primary reader if needed:

```powershell
ollama list
ollama pull qwen3-vl:latest
```

The application never downloads Ollama models. A mutable latest tag can change digest; revalidate after changing it. The optional India header fallback uses installed `qwen3.5:4b` only after an invalid primary reading; provision it explicitly if wanted. OCR-only mode is available through System settings. Model limits and folder precedence are in [configuration](project/docs/configuration.md).

The single launcher initializes state and starts all components; no frontend build or separate web command is required. For first-document checks use dedicated test folders. Reboot, fully offline installation and fresh-machine acceptance remain pending; see [roadmap](project/docs/roadmap.md).

## Repository

```text
README.md                         Single entry point and installation guide
project/
  run_system.py                   Normal combined launcher
  main.py, run_batch.py            Direct single/batch conversion
  init_pipeline.py                 State initialization/migration
  scan_incoming.py, run_worker.py  Maintenance component commands
  run_dashboard.py                 Standalone web server
  src/foc_extractor/               Production Python backend
  frontend/templates/, static/    Production HTML, CSS and JavaScript
  templates/                      Blank Bangladesh, India and Jordan masters
  pipeline_config.json            Base folder/model configuration
  valuation_rates.json            Approved regional estimation rates
  requirements*.txt               Direct constraints and working dependency pins
  docs/                           Six focused guides plus OpenAPI
  tests/                          Regression tests
  development/analysis/           Comparison, print QA and preservation baseline
  development/postman/            API collection and local environment
  examples/, expected_outputs/    Canonical test PDFs and manual references
  tools/build_release.py          Development-only source release builder
  incoming/, output/, runtime/    Local production documents, queue and evidence
  .cache/, .venv/                 Local models/cache and installed environment
  reports/, dist/                 Ignored verification results and current release
```

The stable backend/frontend and command paths are intentional: saved attempts and the Windows task retain absolute paths. Tests, tools, fixtures and local data are excluded from the production ZIP. Retain input/output/state/evidence together; these are not disposable development files.

## Documentation

| Guide | Purpose |
|---|---|
| [Operations](project/docs/operations.md) | Dashboard use, editing, preview, clear/reprocess, startup, backup and troubleshooting |
| [Configuration](project/docs/configuration.md) | Folder/model settings, source rules, templates, rates and precedence |
| [Architecture](project/docs/architecture.md) | Backend/frontend responsibilities, Python interfaces, schema and evidence |
| [API](project/docs/api.md) · [OpenAPI](project/docs/openapi.json) | HTTP contracts and Postman usage |
| [Development](project/docs/development.md) | Test/analysis commands, contribution rules, build, install, upgrade and rollback |
| [Roadmap](project/docs/roadmap.md) | Current acceptance, remaining gates and the staged Jordan plan/source checklist |
