# Command-line reference

Run from the repository/release root using project/.venv/Scripts/python.exe. --help is supported by the six production commands. Paths below are relative to project unless noted.

| Script | Purpose / options |
|---|---|
| main.py | One PDF; required --pdf PATH. Optional --template, --output-dir, --cache-dir, --save-json, --max-pages, --local-model, --no-local-vision |
| run_batch.py | Each top-level *.pdf in --input-dir; optional --output-dir, --cache-dir, --max-pages, --local-model, --no-local-vision |
| init_pipeline.py | Validate --config and create/migrate durable state; never starts extraction |
| scan_incoming.py | Continuously accept stable PDFs; --config, --once |
| run_worker.py | Continuously consume queue; --config, mutually exclusive --once or --drain |
| run_dashboard.py | Read-only localhost web server; --config, --port (default 8080, range 1–65535) |

main.py/run_batch.py output defaults to project/output and cache to project/.cache/ocr. Model defaults to qwen3-vl:latest. --no-local-vision overrides the model to None. max-pages must be positive; it is diagnostic, not a way to produce a complete shipment invoice. The managed worker does not expose page truncation.

Batch defaults to project/examples for the development checkout and writes output/run_manifest.json. Its glob is top-level and case-sensitive according to pathlib/platform behavior; continuous intake explicitly handles PDF extensions case-insensitively and checks temporary/link/hidden names. Batch/direct commands bypass queue history and managed collision versioning.

Worker --once retries prepared saves and processes at most one new job. --drain handles the current backlog, then exits after an idle pass; it does not wait continuously for new arrivals. Both exit with code 1 if failed/interrupted/waiting-to-save job states remain. A continuous worker normally stays alive after a per-PDF converter failure. Database/ownership/heartbeat failures stop it.

Scanner --once records one readiness observation, usually waiting on the first arrival. A later observation after the interval can queue it. Continuous scans sleep for the configured interval after completing the prior scan. Rejections are recorded in JSON/status; a scan containing rejected inputs does not necessarily exit nonzero.

Ctrl+C stops scanner/dashboard. Worker Ctrl+C requests shutdown after the current conversion finishes; this can wait through the existing model timeout. Forced termination is recovered on restart under native lock ownership rules.

## Examples

~~~powershell
project/.venv/Scripts/python.exe project/main.py --pdf C:/shipments/incoming/new.pdf --save-json
project/.venv/Scripts/python.exe project/run_batch.py --input-dir C:/shipments/incoming --output-dir C:/shipments/invoices
project/.venv/Scripts/python.exe project/init_pipeline.py --config C:/shipments/pipeline_config.json
project/.venv/Scripts/python.exe project/scan_incoming.py --config C:/shipments/pipeline_config.json
project/.venv/Scripts/python.exe project/run_worker.py --config C:/shipments/pipeline_config.json
project/.venv/Scripts/python.exe project/run_dashboard.py --config C:/shipments/pipeline_config.json --port 8081
~~~

Defaults for the four managed commands select project/pipeline_config.json regardless of current directory. A custom file must provide all six keys. The dashboard requires an initialized schema-3 database and never migrates it.

## Exit and output conventions

Successful one-shot commands normally return 0. Argument validation uses argparse code 2. Batch reports each written/failed source and exits 1 if any source failed. A direct conversion prints its output path; an uncaught conversion/configuration error exits nonzero. Scanner/worker print JSON lifecycle/count status, while underlying OCR/model diagnostics can also appear on stdout; do not treat the whole stream as one JSON document.

Development commands are documented in [testing](testing.md) and [build](build.md). They are not included in production archives.
