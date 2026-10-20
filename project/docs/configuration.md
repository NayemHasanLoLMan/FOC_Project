# Configuration reference

The default file is project/pipeline_config.json. Each pipeline CLI accepts --config. Paths resolve against the configuration file's folder, independently of the process working directory.

~~~json
{
  "incoming_dir": "incoming",
  "output_dir": "output",
  "state_dir": "runtime/state",
  "artifact_dir": "runtime/artifacts",
  "scan_interval_seconds": 5,
  "local_model": "qwen3-vl:latest"
}
~~~

| Key | Type | Meaning |
|---|---|---|
| incoming_dir | Nonempty directory path | Non-recursive PDF inbox |
| output_dir | Nonempty directory path | Managed published Excel files |
| state_dir | Nonempty directory path | jobs.sqlite3 and native scanner/worker locks |
| artifact_dir | Nonempty directory path | Source snapshots, attempt outputs, receipts and evidence |
| scan_interval_seconds | Positive finite number | Scanner sleep after each scan and worker idle/save-retry interval |
| local_model | Nonempty model name or null | Installed Ollama vision model; null disables model fallback |

Exactly these keys are required. Unknown/missing keys are rejected. Folder paths must be distinct and cannot nest inside one another; an existing file cannot be used as a folder. Validation does not guarantee permissions or free disk space.

Load configuration at process startup. Edit while processes are stopped, validate with init_pipeline.py, then restart all components with the same file. Configuration edits do not retroactively requeue completed jobs. Existing attempts retain their recorded configuration/output/artifact roots; moving those folders requires a deliberate migration, not just editing JSON.

## Shared production inputs

- templates/BD_template.xlsx: master used by managed/batch BD conversion. The writer inherits styles while expanding rows. Editing the master affects future generated invoices, not old outputs.
- templates/INDIA_template.xlsx and JORDAN_template.xlsx: retained alternatives, not validated by the BD benchmark.
- valuation_rates.json: approved approximate USD rates; recognized product and unit must match. Decimal line rounding is cents; a complete calculated shipment total rounds to whole USD, half up. An explicit source value retains priority.
- parser.py maintained company directory: supported address/BIN/shipping-mark fallbacks only for identified companies/units. It is code-owned, not an exposed web setting.

Direct main.py supports an explicit template, output/cache directory, local model and diagnostic page limit. Batch supports input/output/cache/model/page limit; its no-argument input defaults to development examples. In a production bundle, pass a real --input-dir because examples are excluded.

## Vision and cache settings

The shared transport currently uses 127.0.0.1:11434, temperature 0, 8,192 context, 4,096 output tokens, think=false, keep_alive=0 and a 7,200-second HTTP timeout. These are converter settings, not editable JSON keys. The model must be installed; the application does not download it.

OCR cache: project/.cache/ocr by default, with source/settings keys and page checkpoints. Weight/package evidence and local_vision responses live below that root. Model answer keys include exact input bytes, model digest, prompt, schema and generation options.

The worker explicitly uses the existing project OCR cache. Configuring another artifact/state folder does not create an isolated OCR cache. Use main.py/run_batch.py --cache-dir for a deliberate fresh-OCR evaluation. Never point a cache cleanup at runtime artifacts.

## Template/source policies

PDF facts take priority over expected reference files. Export date falls back to a labelled packing-list date under the approved rule; there is no current-date assumption. Package quantities follow consistent PDF counting, not inferred consolidation from weight. Gross fallback has no added packaging allowance or rounding; unsupported net remains blank. G for the confirmed small-button categories means GROSS.

Best-effort invoice numbering may use the original invoice-style filename and can be wrong. Renamed/new PDFs and changed source layouts need acceptance testing. These rules are not dashboard settings; changes require a small tested code update.
