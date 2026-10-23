# Production and development boundaries

Create a production ZIP using [build.md](build.md). It is safer than deleting folders from a working installation: the allowlist packages only runtime inputs and documentation.

| Keep in production | Purpose |
|---|---|
| src/foc_extractor/ and seven project CLI files | Backend and commands |
| frontend/templates/ and frontend/static/ | Dashboard pages and assets |
| templates/, pipeline_config.json, valuation_rates.json | Blank invoice formats and processing settings |
| requirements.txt, requirements-lock.txt, docs/, README files | Installation and operating reference |

| Development only; excluded from ZIP | Purpose |
|---|---|
| tests/ | Automated regression tests |
| development/ | Analysis implementations and Postman examples |
| tools/ | Production ZIP builder |
| examples/, expected_outputs/ | Test PDFs and manual reference workbooks |
| reports/ | Generated QA evidence and isolated demonstration runs |
| dist/ | Previously generated release archives |

A clean deployment does not require development folders. After removing them, unit tests, evaluators and rebuilding the ZIP are unavailable, while the seven production commands remain usable. Batch conversion needs an explicit --input-dir because its historical default is examples/.

The active installation uses runtime/state and runtime/artifacts, not reports. Nevertheless, inspect the actual configuration, scheduled task and database references before cleaning any installation: historical/custom deployments may differ. Saved state records absolute paths to evidence and invoices. Never move referenced files as a folder tidy-up. Completed QA runs are archived only after reference and hash verification; current production data stays at its original paths.

incoming/, output/, runtime/, .cache/ and .venv/ are machine-local, excluded from the source ZIP, but are not disposable test code. They contain active documents, queue state, OCR/model caches or the installed runtime. Preserve managed state/artifacts/output together. Models and dependencies must be provisioned separately on a new machine; see [operations](operations.md).

The frontend was moved out of the backend with its bytes unchanged. Backend imports and CLI locations stay stable. Flask resolves frontend paths from the application root and keeps /dashboard_static/ URLs. Evaluation has one implementation under development/analysis/. Retired tools/ forwarding files are preserved in the development archive.
