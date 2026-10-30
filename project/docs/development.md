# Development, testing and release

Production code and folder ownership are mapped once in the [root README](../../README.md#repository). Application modules must not import tests, tools, development fixtures or manual references. Keep frontend assets in frontend/, backend modules in src/foc_extractor/, tests in tests/ and analysis/Postman in development/. The seven production command paths remain stable.

## Change policy

Use the smallest shared change: skip unnecessary features, reuse existing helpers, prefer standard-library/native/installed capabilities, and add minimal clear logic with a meaningful focused test. Search all callers before changing an interface. Preserve direct, batch, queued and web behavior. Keep security checks, error handling and recovery guarantees.

Update API narrative, OpenAPI, Postman and route tests together when contracts change. Put each instruction in its owning guide rather than adding another README/milestone document. Do not change dependencies, OCR models or production settings as part of unrelated cleanup.

Never encode shipment-specific answers or use expected invoices as production lookups. Prefer PDF-supported facts and approved valuation policies. Preserve source units, identifier leading zeros, source attribution and readable corrections. Keep unsupported fields empty; do not print intervention/validation prompts on invoices. Pause/stop safely before runtime code changes; application fingerprints require a worker restart after changes.

## Git workflow

Keep `main` ready to run. Start each change from an up-to-date `main` and use a short-lived branch:

```powershell
git switch main
git pull --ff-only origin main
git switch -c codex/describe-the-change
```

Commit or stash existing work before switching branches. Keep each commit focused and use a descriptive message such as `fix: preserve invoice number leading zeros`, `docs: clarify offline setup` or `chore: tidy Git ignore rules`; avoid messages such as `update`.

Before committing, run the checks relevant to the change from the next section. Review `git status --short` and `git diff`, then stage only the intended files with `git add <path>`. Inspect `git diff --cached` and run `git diff --cached --check` before `git commit`. Confirm that new PDFs/workbooks are approved regression fixtures, not private shipment documents. Ignore rules do not remove files already tracked by Git.

Publish the branch with `git push -u origin HEAD` and open a pull request into `main`. Describe the problem, changed behavior, checks run and any remaining limitations. After merging, switch to `main`, pull with `--ff-only`, and delete the local topic branch with `git branch -d <branch>` once Git confirms it is merged. Keep shared history intact; do not force-push `main` or rewrite old commits merely to rename them.

The root `.gitattributes` normalizes text in Git and marks PDF/XLSX/ZIP files as binary. The `.gitignore` keeps local environments, caches, runtime data, generated output, Office lock files and environment secrets out of new commits; `.env.example` may be tracked only with placeholder values.

## Regression and analysis

From the repository root:

```powershell
project/.venv/Scripts/python.exe -m pip check
project/.venv/Scripts/python.exe -m unittest discover -s project/tests -q
project/.venv/Scripts/python.exe project/development/analysis/compare_invoices.py
project/.venv/Scripts/python.exe project/development/analysis/check_outputs.py
```

Tests use unittest, temporary directories and controlled model/OCR responses. They cover parsing, goods/weight/package cells, money/rounding, workbook values/styles, queue/schema/recovery/publication, retained images, browser contracts and protected commands. They are not a fresh-model accuracy benchmark. JavaScript syntax and browser behavior should also be checked when changing frontend code.

Analysis tools have one implementation each. compare_invoices.py reads actual workbook values and accepts --output-dir, --expected-dir, --report-dir and --baseline-dir; it writes accuracy.json/accuracy.md outside invoices. check_outputs.py checks canonical development outputs for coverage, incomplete data, merged cells, formula errors and prohibited invoice warnings; it writes reports/validation.json. These tools require existing appropriate outputs; never overwrite production to obtain a test result.

Canonical sample PDFs and manual reference workbooks stay in examples/ and expected_outputs/. development/analysis/baseline.json retains the verified 20-shipment BD parser/valuation snapshots and one India valued result for future preservation comparisons. It is development evidence, never imported by production. Fixtures/reference differences do not establish one universal accuracy score.

The same baseline contains Jordan source contracts for four shipments and 28 page checks. Run `project/.venv/Scripts/python.exe project/development/analysis/jordan_readiness.py` to verify source/reference fingerprints and page coverage, inspect duplicate master labels and probe dynamic writer capacity with 25 synthetic goods. It writes reports/jordan-readiness/readiness.json (or --report), uses only temporary probe workbooks, and never invokes OCR/models or opens live jobs. Reported master/writer defects are pending work, not a passing extraction acceptance. The staged implementation and business decisions belong in [roadmap](roadmap.md#jordan-and-final-delivery-plan).

Optional native print QA requires Windows/Excel:

```powershell
& project/development/analysis/export_print_samples.ps1 -Invoices project/output/bangladesh/26S5166-I.xlsx
```

The script opens its own hidden Excel instance, reads workbooks without updating links/macros, exports the first sheet and closes its own instance. It does not close the user's Excel. Default exports go to reports/print_check.

For real-PDF acceptance, use dedicated input/output/state/artifact directories. Observe every source page and goods row; verify images, download hashes, units, source-supported fields and actual printed layout. Check retry/restart/publication without overwrites. Distinguish fresh inference from exact-cache reuse and synthetic probes from unseen real shipments. A successful save or --help output is not extraction acceptance. Current limits and next stages are in [roadmap](roadmap.md).

## Build the production source ZIP

```powershell
project/.venv/Scripts/python.exe project/tools/build_release.py
Get-FileHash project/dist/foc-invoice.zip -Algorithm SHA256
```

The standard-library builder creates a source archive, not an executable, installer, container or wheel. It refuses to replace an existing ZIP; remove an obsolete build deliberately or pass --output with a different path. There is no frontend compilation or CDN dependency.

The allowlist packages the single root README, seven CLI files, src Python modules, frontend HTML/CSS/JS, blank XLSX masters, current documentation/OpenAPI, base configuration/rates and requirements. It excludes tests, tools, development, examples, manual references, reports, incoming/output/runtime, models/caches, .venv, .git, secrets and bytecode.

Archive paths begin foc-invoice/. BUILD_MANIFEST.json records application/version/format and SHA-256 for every packaged file; it does not hash itself. Verify names/hashes and reject unsafe extraction paths before deployment. Tests check complete manifest coverage, excluded boundaries, independent runtime imports and packaged documentation links. The ZIP is not signed or a byte-for-byte reproducible-build claim.

## Install or upgrade a release

Extract into a new directory instead of overlaying a running installation:

```powershell
Expand-Archive -LiteralPath project/dist/foc-invoice.zip -DestinationPath C:/deployments/invoice-next
Set-Location C:/deployments/invoice-next/foc-invoice
py -3.12 -m venv project/.venv
project/.venv/Scripts/python.exe -m pip install -r project/requirements-lock.txt
project/.venv/Scripts/python.exe -m pip check
project/.venv/Scripts/python.exe project/run_system.py --help
```

Follow [installation/model provisioning](../../README.md#install), [configuration](configuration.md) and [operations](operations.md). Run an isolated real-document smoke check before activating managed folders. Direct batch conversion needs --input-dir because production bundles intentionally omit examples. Release packages do not include customer PDFs, live state, models or dependencies.

Before upgrading, stop intake, let current processing finish and stop the system. Back up matching code/dependency versions, state, snapshots/artifacts and every regional output as one consistent set. Current schema is 6; older builds cannot safely open newer schemas. Initialize migrations deliberately, retain recorded absolute paths, and smoke-test recovery. To roll back, stop again and restore a matching code/schema/artifact/output set; changing configuration alone cannot relocate historical files. See [backup and restore](operations.md#backup-and-restore).

## Offline dependency provisioning

On a machine matching target Windows/Python/architecture:

```powershell
project/.venv/Scripts/python.exe -m pip download -r project/requirements-lock.txt --dest C:/provisioning/invoice-wheels
```

On the target, install with --no-index --find-links C:/provisioning/invoice-wheels using the same lock. Provision PaddleOCR and Ollama models separately under the intended account. Wheel coverage and a fully offline fresh-machine installation have not yet been accepted merely by building a ZIP.

## Local data and housekeeping

Only disposable generated QA fixtures/runs belong under reports/. Retain a compact current verification report and useful regression logs; do not keep every intermediate experiment, copied release or duplicate PDF tree indefinitely. Customer files and caches belong to incoming/output/runtime/.cache, not source folders. Preserve Clear data recovery archives under runtime/cleared until deliberately managed under a retention policy.

The optional --development launcher recreates development/runtime on demand; its old isolated test history is disposable once the workspace is stopped and confirmed unreferenced. A clean production deployment does not require development folders. A working development checkout keeps tests and canonical regional samples for regression/Jordan implementation. Never delete a configured/recorded path just because its directory name looks temporary.

Do not commit private documents, generated invoices, caches/models, runtime databases, reports, release ZIPs, environments or secrets. Keep requirements.txt as direct constraints and requirements-lock.txt as the validated dependency snapshot. Update them deliberately after isolated acceptance. Coordinate reboot/sign-out with the user; cleaning or building does not authorize a reboot.
