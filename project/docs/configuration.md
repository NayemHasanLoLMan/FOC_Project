# Configuration reference

The default file is project/pipeline_config.json. Each pipeline CLI accepts --config. Paths resolve against the configuration file's folder, independently of the process working directory.

~~~json
{
  "incoming_dir": "incoming/bangladesh",
  "output_dir": "output/bangladesh",
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

The six keys above are required. Optional `vision_output_tokens`, `vision_context_tokens` and `vision_timeout_seconds` default to 4096, 8192 and 7200. These must be positive whole numbers, with context at least as large as output. Unknown/missing required keys are rejected. Folder paths must be distinct and cannot nest inside one another; an existing file cannot be used as a folder. Validation does not guarantee permissions or free disk space.

Load configuration at process startup. Edit while processes are stopped, validate with init_pipeline.py, then restart all components with the same file. Configuration edits do not retroactively requeue completed jobs. Existing attempts retain their recorded configuration/output/artifact roots; moving those folders requires a deliberate migration, not just editing JSON.

## Shared production inputs

- templates/BD_template.xlsx: master used by managed/batch BD conversion. The writer inherits styles while expanding rows. Editing the master affects future generated invoices, not old outputs.
- templates/INDIA_template.xlsx and JORDAN_template.xlsx: retained alternatives, not validated by the BD benchmark.
- valuation_rates.json: approved approximate USD rates; recognized product and unit must match. Top-level rates remain Bangladesh-only, with cent line rounding and whole-USD shipment rounding (half up). The separate `india` object prices fabric at 0.20/YDS, zippers at 0.10/PCS, and fabric swatches/samples/cuttings at 0.10/SETS; India lines and complete calculated totals retain cents (half up). Source prices, amounts and totals retain priority. Unknown categories/units stay unpriced; an incomplete shipment does not get a partial calculated total. The existing rates SHA-256 covers both countries.
- parser.py maintained company directory: supported address/BIN/shipping-mark fallbacks only for identified companies/units. It is code-owned, not an exposed web setting.

Direct main.py supports an explicit template, output/cache directory, local model and diagnostic page limit. Batch supports input/output/cache/model/page limit; its no-argument input defaults to development examples. In a production bundle, pass a real --input-dir because examples are excluded.

## Vision and cache settings

The shared transport currently uses 127.0.0.1:11434, temperature 0, 8,192 context, 4,096 output tokens, think=false, keep_alive=0 and a 7,200-second HTTP timeout. These are converter settings, not editable JSON keys. The model must be installed; the application does not download it.

OCR cache: project/.cache/ocr by default, with source/settings keys and page checkpoints. Weight/package evidence and local_vision responses live below that root. Model answer keys include exact input bytes, model digest, prompt, schema and generation options.

The worker explicitly uses the existing project OCR cache. Configuring another artifact/state folder does not create an isolated OCR cache. Use main.py/run_batch.py --cache-dir for a deliberate fresh-OCR evaluation. Never point a cache cleanup at runtime artifacts.

## Template/source policies

PDF facts take priority over expected reference files. Export date falls back to a labelled packing-list date under the approved rule; there is no current-date assumption. Package quantities follow consistent PDF counting, not inferred consolidation from weight. Gross fallback has no added packaging allowance or rounding; unsupported net remains blank. G for the confirmed small-button categories means GROSS.

Best-effort invoice numbering may use the original invoice-style filename and can be wrong. Renamed/new PDFs and changed source layouts need acceptance testing. These rules are not dashboard settings; changes require a small tested code update.

## Country folders

Default production processing watches incoming/bangladesh and publishes to output/bangladesh, relative to pipeline_config.json. Initialization and the single-command launcher create bangladesh, india and jordan siblings under each parent. Only the configured Bangladesh folder is scanned; India/Jordan are reserved and are not part of validated automatic processing. Do not drop PDFs into the parent folder. Custom configurations still use their exact supplied paths.

Old queue snapshots and historical published files are not relocated. Changing the current default paths does not move attempts' recorded locations. The original standalone test workbooks were preserved under reports/bd_layout_20261021/previous_flat_output before regeneration into the Bangladesh output folder.

## Bangladesh invoice details

The shared writer prints BIN lines as BIN : identifier, without surrounding brackets, retaining leading zeros/hyphens and using red text. Carton references use red values. Labelled TINs from the PDF are printed in red above the customs-purpose footer. Import open cover notes from the PDF are printed in red above the customs invoice number, with wrapping. These optional values are never copied from expected workbooks or guessed from a company directory. Missing/conflicting values stay empty.

Bangladesh invoices omit net weight, its audit entry and missing-field warnings. Net-weight support remains available for other regions. These generation rules apply to every future invoice; there is no per-shipment formatting patch or sample-specific lookup.

## Editable dashboard settings

Open **System → Processing settings** on the combined launcher (main port 8080 or isolated test port 8081). Change the model, scan interval, vision output/context tokens, vision timeout, incoming folder and output folder, then Save settings. The Vision model dropdown lists locally installed Ollama models and refreshes automatically. Select OCR only to disable vision. The current selection is preserved if Ollama is unavailable or its model is removed. Use an installed vision-capable Ollama model; saving does not download or install it. Ollama availability is checked separately.

Saving requires the scanner and worker to be idle. If work is active, pause consumption on Overview, let the current invoice finish, then save and resume. No active invoice is interrupted. Every new attempt records the actual configuration. Vision options reach the shared quantity/package/weight reader; changing model or limits separates its relevant cache keys. Existing defaults retain their prior caches.

Changes persist atomically in `settings.json` under the fixed state directory. On the next combined-launcher startup these seven overrides take precedence over the base JSON. Standalone conversion/scanner/worker commands continue to use their explicit base config; use the combined launcher for this editable dashboard flow. Database/artifact locations, startup task identity and port remain unchanged. To recover from invalid manual edits, stop the launcher and restore/remove this override file before restarting.

Use full absolute paths to dedicated folders. Missing folders are created and write access checked. Input/output cannot overlap each other, state/artifacts, application/cache/reference folders or broad drive/home/project roots. The optional development launcher restricts paths to its isolated workspace. Existing outputs and queued snapshots are not moved or deleted: old downloads retain their recorded destination, queued jobs finish from their snapshots, and new arrivals use the newly watched folder. Previously completed PDFs do not requeue just because settings changed. Clear data still intentionally requeues remaining inbox PDFs.

Clear data archives the currently configured output folder, not older output folders. Use a dedicated invoice folder. For output on the same volume, generated files are archived with the database/artifacts in the workspace recovery folder. For output on another volume, the output folder is atomically moved into `.foc-cleared/<reset-id>/output` beside its original folder; `external-output.json` in the main recovery archive records both paths. Restore that output together with its matching database/artifacts. A failed move rolls back the reset. No cross-volume copy-and-delete is used.

POST `/api/settings` accepts a UUID `request_id` and a `changes` object containing all seven editable fields. Origin/CSRF protections apply. Replaying the UUID returns the original result without applying old values over later settings. Busy/invalid settings return 409; an uncoordinated standalone dashboard returns 403. See OpenAPI and the Postman Processing settings group.


### India currency policy (Fix 2)

Read explicit currency declarations, financial headings/values and supported currency-table cells before valuation. Explicit USD is supported; declared non-USD currency is retained by parsing but cannot be exported through the USD India template. No exchange-rate conversion or USD estimates are applied to non-USD data. Conflicting declarations and unreadable/ambiguous explicit declarations fail safely, with candidate evidence retained. Existing invoice/JSON files remain untouched.

When no currency is supplied, keep the approved USD valuation default and record `approved_default_usd` evidence; this is not a claim that the PDF declared USD. An unqualified dollar sign in an amount alone does not establish a different currency. Bare `Currency: $` is ambiguous and rejected. Common codes and unambiguous US$/HK$/A$/C$/S$/euro/pound/rupee markers in financial contexts are recognized; an isolated yen/rupee marker that cannot establish a single currency is not guessed as USD. Detection is bounded to financial/currency contexts, not arbitrary address or product words. The live watcher remains Bangladesh-only.


### India invoice-number readers (Fix 3)

`local_model` remains the primary vision model; null disables both primary and optional invoice-header vision reading. India first uses a readable PDF invoice reference without a filename hint. If absent, one bounded labelled header area can be read by the configured primary model. A completed but invalid header response may use the already installed `qwen3.5:4b` as an optional fallback, through the same transport, output/context/timeout limits and image/model cache. A valid primary reference avoids the fallback. Missing/unavailable readers retain the existing filename fallback or blank. No model is installed/downloaded automatically and no global model setting changes.

The fallback is limited to India invoice-number reading. Bangladesh extraction, other fields and their configured model remain unchanged. Per-field fallback choice is currently a small fixed policy, not another settings control; review regional model preferences when regional watching is enabled. Both models, rejected/accepted responses, exact input images and the actual invoice-number contribution are retained in attempt evidence.
