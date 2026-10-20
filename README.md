# Local PDF to invoice

The application lives in **[project](project/README.md)**. It converts shipment PDFs into the shared Excel invoice template using local PaddleOCR and optional local vision, with a durable folder pipeline and read-only dashboard.

- [Full documentation index](project/docs/README.md)
- [Install and run](project/docs/setup.md) · [User guide](project/docs/user-guide.md)
- [Architecture and code](project/docs/architecture.md) · [Project structure](project/docs/project-structure.md)
- [HTTP API](project/docs/api.md) · [OpenAPI JSON](project/docs/openapi.json) · [Python reference](project/docs/code-reference.md)
- [Build and release](project/docs/build.md) · [Operations](project/docs/operations.md) · [Testing](project/docs/testing.md)

Production code is in project/src/foc_extractor and the production CLI scripts. Test/evaluation implementations are under project/tests. Canonical sample/reference paths remain compatible; production bundles exclude tests, fixtures, reports, generated data, caches and environments.

From this repository root:

~~~powershell
project/.venv/Scripts/python.exe project/run_dashboard.py
~~~

The dashboard needs initialized state and does not start the scanner/worker. See setup/operations for the three-process workflow. BD is the validated development scope; production never reads manual expected invoices. Admin controls and unattended startup remain later stages.
