# Local PDF to invoice

The application lives in **[project](project/README.md)**. It converts shipment PDFs into the shared Excel invoice template using local PaddleOCR and optional local vision, with a durable folder pipeline and local admin dashboard.

- [Full documentation index](project/docs/README.md)
- [Install and run](project/docs/setup.md) · [User guide](project/docs/user-guide.md)
- [Architecture and code](project/docs/architecture.md) · [Project structure](project/docs/project-structure.md)
- [HTTP API](project/docs/api.md) · [OpenAPI JSON](project/docs/openapi.json) · [Python reference](project/docs/code-reference.md)
- [Build and release](project/docs/build.md) · [Operations](project/docs/operations.md) · [Testing](project/docs/testing.md)

Production code is in project/src/foc_extractor and the production CLI scripts. Frontend assets are in project/frontend. Unit tests are in project/tests; analysis and Postman files are in project/development. Canonical sample/reference paths remain compatible; production bundles exclude tests, fixtures, reports, generated data, caches and environments.

From this repository root:

~~~powershell
project/.venv/Scripts/python.exe project/run_system.py
~~~

This single command initializes state and starts scanner, worker and dashboard together. Open http://127.0.0.1:8080/ and drop PDFs into project/incoming/bangladesh. Ctrl+C waits for the current invoice before shutting down. Bangladesh remains the established baseline. India now supports opt-in separate input/output folders through System, with one real sample verified and unseen-PDF validation pending. Jordan intake stays disabled. Production never reads manual expected invoices. Stages 1–7 are implemented, including guarded controls and current-user background startup. Final Stage 8 acceptance remains pending. Clear data archives generated files and automatically recreates invoices from remaining inbox PDFs.
