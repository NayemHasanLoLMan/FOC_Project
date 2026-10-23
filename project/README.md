# FOC invoice automation

Convert shipment PDFs into professional Excel invoices using local PaddleOCR and selective Ollama vision. One command starts the folder scanner, worker and dashboard:

```powershell
project/.venv/Scripts/python.exe project/run_system.py
```

Run from the repository root and open http://127.0.0.1:8080/. Bangladesh uses `project/incoming/bangladesh` → `project/output/bangladesh`. India has a separate folder pair enabled through System settings. Jordan is reserved and disabled. Production reads PDFs and maintained settings, never the manual expected invoices.

| Area | Location |
|---|---|
| Backend | `src/foc_extractor/` |
| Web frontend | `frontend/templates/`, `frontend/static/` |
| Blank invoice masters | `templates/` |
| Configuration and approved rates | `pipeline_config.json`, `valuation_rates.json` |
| Current guides and API specification | [docs](docs/README.md) |
| Tests, analysis and Postman | `tests/`, `development/` |
| Test PDFs and manual references | `examples/`, `expected_outputs/` |
| Local production data | `incoming/`, `output/`, `runtime/` |
| Ignored QA evidence / historical archives | `reports/` |

Start with [setup](docs/setup.md), [user guide](docs/user-guide.md), [operations](docs/operations.md) and [configuration](docs/configuration.md). Developers should read [architecture](docs/architecture.md), [code reference](docs/code-reference.md), [HTTP API](docs/api.md), [OpenAPI](docs/openapi.json), [testing](docs/testing.md) and [build](docs/build.md).

The production ZIP excludes tests, manual references, development tools, historical documentation and local data. Build it with `project/tools/build_release.py`; do not remove folders from a live installation to create a deployment.

See [readiness](docs/readiness.md) for verified scope and remaining stages. Existing invoices, evidence and caches retain their recorded paths. Completed milestone notes are archived under `development/archive/`; they are historical evidence, not current operating instructions.
