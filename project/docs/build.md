# Build, verify and release

## What “build” produces

This Python application has no frontend compilation, container, native installer or single-file executable. The supported build is a **production source ZIP** with an SHA-256 manifest. It preserves the existing command layout and runs with a separately installed Python environment, dependencies and local model files.

Build tooling is development-only. Use a development checkout to test/build; an extracted production bundle does not include tests/tools/development/fixtures. No paid/cloud service is needed for generation.

## Validate the source checkout

From the repository root:

~~~powershell
project/.venv/Scripts/python.exe -m pip check
project/.venv/Scripts/python.exe -m unittest discover -s project/tests -q
project/.venv/Scripts/python.exe project/development/analysis/compare_invoices.py
project/.venv/Scripts/python.exe project/development/analysis/check_outputs.py
~~~

The last two require existing development outputs. Generate them in an isolated QA run if necessary; do not overwrite production invoices to run a release check. Also run the real-PDF/print/unseen acceptance appropriate to the change. Syntax/help smoke tests alone do not establish OCR accuracy.

## Create the artifact

~~~powershell
project/.venv/Scripts/python.exe project/tools/build_release.py
~~~

Default output is project/dist/foc-invoice.zip. The builder refuses to overwrite an existing artifact. For another build:

~~~powershell
project/.venv/Scripts/python.exe project/tools/build_release.py --output project/dist/foc-invoice-next.zip
Get-FileHash project/dist/foc-invoice-next.zip -Algorithm SHA256
~~~

The explicit allowlist contains the root/project README, seven production CLI files, backend src/**/*.py and frontend HTML/CSS/JavaScript files, blank .xlsx templates, current configuration/rates, requirements/lock and .md/.json documentation. It excludes tests, tools, development, test PDFs, manual expected workbooks, reports, runtime databases/artifacts, incoming/output, caches, models, .venv, .git, secrets and bytecode.

Archive layout begins foc-invoice/project/. BUILD_MANIFEST.json at foc-invoice/ records application/version/build format and every packaged file's relative path/hash. The manifest does not hash itself. Source file bytes are preserved. The ZIP is not signed, not a dependency installer and not a byte-for-byte reproducible-build claim.

## Verify and install

Extract to a **new** directory rather than over a running checkout:

~~~powershell
Expand-Archive -LiteralPath project/dist/foc-invoice-next.zip -DestinationPath C:/deployments/invoice-next
Set-Location C:/deployments/invoice-next/foc-invoice
py -3.12 -m venv project/.venv
project/.venv/Scripts/python.exe -m pip install -r project/requirements-lock.txt
project/.venv/Scripts/python.exe -m pip check
project/.venv/Scripts/python.exe project/main.py --help
project/.venv/Scripts/python.exe project/run_dashboard.py --help
~~~

Verify packaged file hashes against BUILD_MANIFEST.json before deploying. A development regression test checks that the manifest covers the archive and runtime imports do not depend on tests/tools. Configure real directories, provision models and follow [setup](setup.md) / [operations](operations.md).

Batch defaults point to examples only in the source checkout; production bundles intentionally omit examples. Always pass --input-dir for production batch use.

## Optional dependency provisioning for offline installation

On a machine matching the target Windows/Python/architecture:

~~~powershell
project/.venv/Scripts/python.exe -m pip download -r project/requirements-lock.txt --dest C:/provisioning/invoice-wheels
~~~

Transfer the wheels separately and install on the target:

~~~powershell
project/.venv/Scripts/python.exe -m pip install --no-index --find-links C:/provisioning/invoice-wheels -r project/requirements-lock.txt
~~~

This only provisions Python dependencies. PaddleOCR and Ollama model files must also be provisioned and verified separately under the intended user account. The source ZIP excludes them. Package availability/wheel coverage and a fully offline fresh-machine install have not been proven merely by building a ZIP.

## Upgrade and rollback

Stop scanner and dashboard; let the worker finish its current conversion and stop. Back up SQLite plus snapshots/attempt artifacts/output as one unit. Install the next source/dependency environment side by side. Reuse original absolute managed data paths only after checking compatibility and permissions. Run initialization deliberately if a schema migration is required; the dashboard will not migrate.

Smoke-test an isolated queue, then start all components with the same approved configuration. Do not carry development demo configurations or manual references into a production inbox.

For rollback, stop components and restore a matching application/environment and consistent state/artifact/output backup. Do not run older code against an unsupported migrated schema. The current organization change does not change schema 3.

## Verified scope

The organization/build update is checked with the existing suite, legacy/canonical evaluator parity, protected-file hashes and an extracted-bundle CLI/conversion/dashboard smoke test using the installed environment. It is not a clean-machine dependency install, native executable certification, physical power-loss test or unattended-startup release. See the latest organization QA report for exact results.
