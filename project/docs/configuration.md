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
- templates/INDIA_template.xlsx: available-sample India master; templates/JORDAN_template.xlsx: retained for the next implementation stage, not production-ready.
- valuation_rates.json: approved approximate USD rates; recognized product and unit must match. Top-level rates remain Bangladesh-only, with cent line rounding and whole-USD shipment rounding (half up). The separate `india` object prices fabric at 0.20/YDS, zippers at 0.10/PCS, and fabric swatches/samples/cuttings at 0.10/SETS; India lines and complete calculated totals retain cents (half up). Source prices, amounts and totals retain priority. Unknown categories/units stay unpriced; an incomplete shipment does not get a partial calculated total. The existing rates SHA-256 covers both countries.

[Current acceptance](roadmap.md) confirms the current three goods groups are covered. No additional India rates were introduced; Bangladesh rates are not automatically shared. An explicit source total is preserved even when a complete estimated total cannot be calculated.
- Header identities are PDF-only: filenames and company directories do not supply invoice numbers, addresses, BINs or shipping marks. Packing-sheet recipient abbreviations remain literal; absent addresses/identifiers stay empty. Bangladesh preserves FABRIC/GMT/FOC marks actually printed in the header rather than changing every category to FOC.

Direct main.py supports an explicit template, output/cache directory, local model and diagnostic page limit. Batch supports input/output/cache/model/page limit; its no-argument input defaults to development examples. In a production bundle, pass a real --input-dir because examples are excluded.

## Vision and cache settings

The shared transport currently uses 127.0.0.1:11434, temperature 0, 8,192 context, 4,096 output tokens, think=false, keep_alive=0 and a 7,200-second HTTP timeout. The output/context/timeout values are editable configuration and dashboard settings; the other transport options remain converter policy. The model must be installed; the application does not download it.

OCR cache: project/.cache/ocr by default, with source/settings keys and page checkpoints. Weight/package evidence and local_vision responses live below that root. Model answer keys include exact input bytes, model digest, prompt, schema and generation options.

The worker explicitly uses the existing project OCR cache. Configuring another artifact/state folder does not create an isolated OCR cache. Use main.py/run_batch.py --cache-dir for a deliberate fresh-OCR evaluation. Never point a cache cleanup at runtime artifacts.

## Country folders

Default production processing watches incoming/bangladesh and publishes to output/bangladesh, relative to pipeline_config.json. Initialization and the single-command launcher create bangladesh, india and jordan siblings under each parent. Bangladesh remains enabled by default. India intake is available with explicit separate folders and `india_enabled: true`; Jordan is not scanned. The current installation has India enabled for controlled use after Fix 14; additional unseen-PDF validation remains pending. Do not drop PDFs into the parent folder. Custom configurations still use their exact supplied paths.

Existing queue snapshots and published files retain recorded absolute paths; settings changes do not relocate them.

## Bangladesh invoice details

The shared writer prints BIN lines as BIN : identifier, without surrounding brackets, retaining leading zeros/hyphens and using red text. Carton references use red values. Labelled TINs from the PDF are printed in red above the customs-purpose footer. Import open cover notes from the PDF are printed in red above the customs invoice number, with wrapping. These optional values are never copied from expected workbooks or guessed from a company directory. Missing/conflicting values stay empty.

Bangladesh invoices omit net weight, its audit entry and missing-field warnings. Net-weight support remains available for other regions. These generation rules apply to every future invoice; there is no per-shipment formatting patch or sample-specific lookup.

## Editable dashboard settings

Open **System → Processing settings** on the combined launcher (main port 8080 or isolated test port 8081). Change the model, scan interval or vision limits, and use Choose folder for the PDF intake parent and invoice output parent. Each parent contains bangladesh, india and jordan subfolders; Save settings creates missing country folders. Folder buttons display the selected name instead of a full path. The Vision model dropdown lists locally installed Ollama models and refreshes automatically. Select OCR only to disable vision. The current selection is preserved if Ollama is unavailable or its model is removed. Use an installed vision-capable Ollama model; saving does not download or install it. Ollama availability is checked separately.

Saving requires the scanner and worker to be idle. If work is active, pause consumption on Overview, let the current invoice finish, then save and resume. No active invoice is interrupted. Every new attempt records the actual configuration. Vision options reach the shared quantity/package/weight reader; changing model or limits separates its relevant cache keys. Existing defaults retain their prior caches.

Changes persist atomically in `settings.json` under the fixed state directory. On the next combined-launcher startup the saved overrides take precedence over the base JSON. Standalone conversion/scanner/worker commands continue to use their explicit base config; use the combined launcher for this editable dashboard flow. Database/artifact locations, startup task identity and port remain unchanged. To recover from invalid manual edits, stop the launcher and restore/remove this override file before restarting.

The folder browser opens inside the dashboard and returns an absolute local directory. Cancelling leaves selections unchanged, and choosing does not apply anything until Save settings. For direct API clients, use full absolute paths to dedicated country folders. Missing folders are created and write access checked. Input/output cannot overlap each other, state/artifacts, application/cache/reference folders or broad drive/home/project roots. The optional development launcher restricts paths to its isolated workspace. Existing outputs and queued snapshots are not moved or deleted: old downloads retain their recorded destination, queued jobs finish from their snapshots, and new arrivals use the newly watched folder. Previously completed PDFs do not requeue just because settings changed. Clear data still intentionally requeues remaining inbox PDFs.

Clear data archives both currently configured country output folders (including India when intake is disabled), not older output folders. Use a dedicated invoice folder. For output on the same volume, generated files are archived with the database/artifacts in the workspace recovery folder. For output on another volume, the output folder is atomically moved into `.foc-cleared/<reset-id>/output` beside its original folder; `external-output.json` in the main recovery archive records both paths. Restore that output together with its matching database/artifacts. A failed move rolls back the reset. No cross-volume copy-and-delete is used.

POST `/api/settings` accepts a UUID `request_id` and a `changes` object containing all ten editable fields. Legacy requests containing exactly the original seven fields remain supported and preserve the current India configuration. Origin/CSRF protections apply. Replaying the UUID returns the original result without applying old values over later settings. Busy/invalid settings return 409; an uncoordinated standalone dashboard returns 403. See OpenAPI and the Postman Processing settings group.

### India currency policy

Read explicit currency declarations, financial headings/values and supported currency-table cells before valuation. Explicit USD is supported; declared non-USD currency is retained by parsing but cannot be exported through the USD India template. No exchange-rate conversion or USD estimates are applied to non-USD data. Conflicting declarations and unreadable/ambiguous explicit declarations fail safely, with candidate evidence retained. Existing invoice/JSON files remain untouched.

When no currency is supplied, keep the approved USD valuation default and record `approved_default_usd` evidence; this is not a claim that the PDF declared USD. An unqualified dollar sign in an amount alone does not establish a different currency. Bare `Currency: $` is ambiguous and rejected. Common codes and unambiguous US$/HK$/A$/C$/S$/euro/pound/rupee markers in financial contexts are recognized; an isolated yen/rupee marker that cannot establish a single currency is not guessed as USD. Detection is bounded to financial/currency contexts, not arbitrary address or product words. India folder watching is opt-in; the base configuration remains Bangladesh-only.

### India invoice-number readers

`local_model` remains the primary vision model; null disables both primary and optional invoice-header vision reading. India first uses a readable PDF invoice reference without a filename hint. If absent, one bounded labelled header area can be read by the configured primary model. A completed but invalid header response may use the already installed `qwen3.5:4b` as an optional fallback, through the same transport, output/context/timeout limits and image/model cache. A valid primary reference avoids the fallback. Missing/unavailable readers retain the existing filename fallback or blank. No model is installed/downloaded automatically and no global model setting changes.

The fallback is limited to India invoice-number reading. Bangladesh extraction, other fields and their configured model remain unchanged. Per-field fallback choice is currently a small fixed policy, not another settings control; review regional model preferences when regional watching is enabled. Both models, rejected/accepted responses, exact input images and the actual invoice-number contribution are retained in attempt evidence.

### India folder settings

Optional base configuration keys: `india_enabled` (boolean, default false), `india_incoming_dir` and `india_output_dir` (directory strings or null, default null). Supply both India paths together; enabling requires both. Base-file paths may be relative to that file. Dashboard paths must be absolute. All regional input/output, state and artifact paths must be distinct and non-nested, and dashboard paths must pass the existing protected-folder and redirection checks. No folder is inferred from a custom Bangladesh path.

System exposes these three settings alongside the existing seven. Save all twelve fields, or an exact legacy ten/seven-field payload that preserves omitted country controls. Partial India updates are rejected. Disabling India pauses new intake only: accepted India jobs/retries keep their immutable region and still use the configured India output. Do not remove India folder settings while India history exists; disable intake instead. Folders containing historical jobs cannot be reassigned to another country through settings. A direct file misconfiguration is reported without changing job identity. Startup loads old seven-field settings files without losing India fields declared in the base config.

Every new attempt records its actual publication root in metadata `output_dir`, independently of the full configuration. Prepared saves and historical downloads use that recorded root after any folder/settings change; old receipts fall back to `configuration.output_dir`. Newly started attempts use current regional folders. Clear data archives Bangladesh output as `output` and India output as `output-india`, with a separate `external-output-india.json` for an India output on another volume. Failed moves roll back both countries. Enabled inboxes rediscover retained PDFs through the same stable-file checks exactly once. Development mode redirects both countries into its isolated workspace.

One scanner/worker/database serves both countries. Scanner results retain the existing top-level keys and add `folders`, keyed by BD/INDIA, with per-folder errors/counts; totals aggregate enabled inboxes. One unavailable inbox degrades scanner health but does not block the other. Same basenames in different country folders remain separate jobs; repeat observations of the same path/content do not enqueue again. The folder supplies immutable job region, and the converter still rejects a conflicting PDF country. Jordan is not enabled by this change.

The current India sample passed, but there is only one unique real shipment. Fix 10 remains pending; enabling routing is not a claim of unseen-document accuracy. See [Current acceptance](roadmap.md).

## Source rules preserved across countries

Prefer explicit PDF declarations and readable corrections. When no export date exists, use the approved packing date; India and Jordan use the latest labelled packing date. Never copy a reference-only date, tax identifier, cover note, port or terms. Existing maintained company-directory behavior remains as implemented; it is not a source for invented tax values.

Quantity multiplication such as `20 YDS x 2 = 40 YDS` uses the declared total once only when the positive quantities, integer multiplier, arithmetic and units agree. A trailing equals sign is accepted when OCR orders that sign after the total. The same normalization is used by table parsing and cell-reader validation; readable expressions do not trigger vision. Contradictory expressions stay unresolved. When a merged cell contains several quantities and no established material heading, OCR word positions can recover separate description bands only if every source quantity/unit agrees and the bands do not cut through text. Existing material/color continuation remains authoritative; source row references and the recovered bands are retained. No filename-specific quantity or target invoice total is used.

Goods normalization preserves explicit PCW RECYCLED and GRS fiber modifiers, validates full blends, and separates labelled BW +/- measurement tolerances from composition percentages. Uncounted style/item metadata retains the material heading; actual products and sender changes still reset it. Description-header fabric notes and quantity-column TRIM CARDS notes retain their source references and apply to the related sender block. The existing bounded fabric-annotation reader runs for Bangladesh and India, accepts only visible swatch/sample phrases, and retains the printed/broad category when a reading is rejected. It does not supply missing units or quantities.

Compact packing tables with separate SHIPPED QTY and UNIT columns use a bounded physical-grid recovery when the normal table parser has no recognized goods table on that page. It joins only the shipped quantity and unit spans, excluding ordered/balance columns and packing footers. Existing source-keyed OCR caches are enriched through the same path as new OCR; no expected invoice supplies an answer. Recovery requires readable headers, physical rules and a printed end boundary. Every page receives a page_coverage evidence entry before goods aggregation; partial, unclassified, unreadable and unprocessed pages remain distinguishable. This records extraction coverage, not proof of row accuracy, and adds no warning text to the printed invoice.

Packages use explicit declared totals/ranges/IDs, then readable physical packing cells counted once; weight cannot establish carton consolidation. Gross weight uses an explicit declaration, otherwise corrected packing-weight cells summed once with no invented allowance. Bangladesh and India do not print net weight. BIN/TIN/cover-note rendering follows each template's red highlights; TIN and cover notes require PDF evidence.

Packing controls include numeric declarations above quantity rows, and colour continuations share their declared heading package/weight once. Compact shipped-quantity forms may supply a labelled per-page gross total and a unitless Total only when package-column wording establishes its meaning. True shipment covers are skipped during packing sums; unknown/excluded pages block incomplete weight sums. Carton IDs deduplicate consistent repeated identified cartons; conflicting explicit package entries are retained with both readings in review evidence. Blank package cells are not fabricated counts, while a page with no supported count blocks a partial total.

Corrected model weights require agreement with a separate literal numeral reading, using the existing installed qwen3.5:4b fallback. Where OCR locates a lower replacement beneath an old KG line, its exact pixel region is isolated, including within a shared brace. Literal decimals are preserved; disagreement leaves gross blank. No rule divides a reading by ten or fits a reference total. Weight aggregate cache version 8 and package version 4 invalidate prior aggregate decisions; exact source/model-keyed cell responses remain reusable. Requests, correction bounds, raw responses and decisions are retained.

Source money/currency takes priority over estimates; India currently supports USD and rejects unsupported/conflicting source currency. Supported fallback category/unit rates come from valuation_rates.json. Small-button G means gross (144 pieces), not grams. Unknown category/unit pairs remain unpriced; incomplete estimated totals stay blank unless an explicit source total is available. Bangladesh totals use whole-dollar half-up rounding; India uses cents. Source units and HS leading zeros remain intact. Local vision reads unresolved source regions with retained input images; it does not invent missing facts or rates.

Existing nonstandard country paths remain supported: the page shows Existing separate folders, and retains those paths until a parent is explicitly selected. The JSON settings contract and recorded historical output roots are unchanged.

Bangladesh intake uses bangladesh_enabled (default true). India uses india_enabled. Jordan uses the reserved jordan_enabled control (false only; true is rejected). Changes apply on Save settings while idle and affect new arrivals only; accepted jobs and historical files remain intact. Both supported countries can be disabled together without stopping the scanner or worker. Badges mark unsaved changes until saved.

### Jordan header and page policy

Jordan reads consignee/address, marks, carton references and destination from the shipment cover, without maintained-directory or filename answers. Explicit export date takes priority; otherwise use the latest labelled packing date across all included pages. A cover signature date is not a packing date. Unreadable explicit export dates stay unresolved rather than silently falling back. Bounded local vision may verify the handwritten cover reference or an unreadable labelled date; source crops, responses and decisions are retained. A missing year is never supplied from the filename.

The approved page policy is to include every page and use the shipment cover destination. A packing recipient naming another country is retained in page-identity evidence and dashboard diagnostics; it does not remove goods or reroute the shipment. Item country of origin is separate from recipient destination. Jordan automatic intake remains disabled until the later extraction, valuation and regional-acceptance gates pass.

### Bangladesh header reading (B6)

Bangladesh reuses the bounded local invoice-reference reader for labelled shipment headers and visible reference-like handwriting near packing-list titles. It preserves the supported variable three-to-five-digit serial and two-digit year; no serial length, year or missing digit comes from the filename. Corrected model references require two matching source-crop readings. The configured model and existing qwen3.5:4b fallback read the ink-isolated view; when available, the original-colour view provides one additional fallback reading. If agreement is unavailable, keep only an existing PDF OCR reference, or leave the field empty. This is best-effort extraction, not proof that matching models are correct. Crops, provisional/rejected answers and final decisions remain available for review. India/Jordan retain their existing regional reading policies.

Labelled consignee blocks take priority; packing-only files retain the actual To recipient text without expanding it into a maintained address. Shipment marks and destinations come from their PDF header sections; packing enclosures and currency labels are not shipping marks. TIN and import cover notes remain source-only. No new customer master or hidden defaults are used. Existing published attempts are preserved; current rules apply on new processing/reprocessing.

When no labelled consignee block exists, Bangladesh packing lists may supply a partial address from the first page's labelled RECIPIENT / DEPT column (including the observed RECEIPIENT spelling). Only self-contained cell readings with a recognizable street/location or explicit Bangladesh country line qualify. Contact names/labels, phone/email lines and exact duplicate company names are excluded. Repeated identical addresses collapse; conflicting candidates stay blank. Country follows the retained PDF address; a postal city never becomes an assumed destination airport. BINs are not added when absent. Recipient-column text, cell bounds and source references remain in field evidence. Joining addresses split across separate cells remains unsupported pending reviewed row-grouping rules. India/Jordan header handling is unchanged.

Bangladesh's printed shipment line uses `SHIPMENT TO:` followed by the extracted destination city, or the explicit destination country when no city is available. If neither is available, its value stays empty. The blank master and writer no longer supply Hong Kong, Dhaka or air transport as standing facts. Origin and transport mode have no supported fields in the current Bangladesh extraction contract and are omitted from this line. This does not change source-address or airport extraction. The publication check rejects stale or altered shipment wording; historical publications keep their original appearance until explicitly reprocessed.

### Bangladesh valuation coverage (B7)

Rates are approximate USD policies selected by the extracted category and explicit unit, not facts read from the PDF or values fitted to a manual invoice. Source prices/amounts take priority, including explicit zero prices. Do not attach an estimated unit rate to an already declared line amount. Fractional unit rates and cent-rounded line values remain; complete Bangladesh calculated totals use whole-dollar half-up rounding. Missing quantities/units keep their amounts blank and prevent a partial shipment total.

| Category / unit | Rate key | USD rate in this release |
|---|---|---|
| Individual shanks/rivets, PCS | shank_rivet_per_pc (existing, broader product wording) | 0.025 |
| Shank/snap/rivet fasteners, SETS | metal_fastener_per_set (new fallback) | 0.05 |
| Unspecified rivets, GROSS | rivet_per_gross (new fallback) | 0.35 |
| Shank/snap button options, GROSS | button_per_gross (existing) | 0.35 |
| Interlining, YDS | fabric_per_yd (existing shared fabric estimate) | 0.20 |
| Composition-only fabric samples, SETS | fabric_sample_per_set (existing) | 0.10 |

Specific configured categories remain ahead of generic fallbacks: for example, 9.5MM rivets keep their own gross rate and metal snaps keep their own set rate. Generic tool/mould/card descriptions do not become individual fasteners. No PCS/SETS/GROSS conversion or packing-factor assumption is added. The generic 0.35/GROSS rivet estimate follows the existing generic small-button estimate; 0.05/SET fasteners use the existing metal-snap estimate as their scale. These are transparent approximate defaults, not independently researched market prices.

Singular/plural garment words and normal/curly apostrophes use the existing garment rates. A physical cotton/stretch woman's PANT is not a composition-only fabric swatch. Explicit booking/handloom/fabric-sample context remains supported. Composition-only garment SETS without an approved garment-set rate stay unpriced. India retains its separate supported rates; Bangladesh interlining/fastener coverage does not enable new India estimates.

### Local reader recovery (B8)

Quantity, package, weight and fabric-annotation readers explicitly try the installed qwen3.5:4b alternate when the configured reader fails or returns an unsuitable answer. Each field retains its existing source/unit/category checks. The low-level reader does not silently switch models: invoice-number corroboration keeps its explicit independent reading policy. No model is downloaded automatically.

Exact image/model-digest/prompt/schema/options cache keys retain completed responses and terminal output-limit failures. A length-limited response is diagnostic evidence, never an accepted answer; repeating the same request can proceed to the alternate without paying for the same exhausted generation again. Invalid structured replies are rejected; transient connection errors are not cached. Clear data rotates these derived caches together with other extraction results.

A quantity cell with exactly two vertically separated numeric OCR words can isolate a lower replacement only when a coloured strike crosses the earlier quantity. That crop uses the installed literal reader first and requires a separate full quantity/unit reading to agree before replacing the original. This currently targets coloured strikes; black-ink cancellation needs separate source validation. Narrow YOS/Y0S/Y05 yard-unit glyph repair changes no digits. A matching standalone unit beside a single quantity is redundant; conflicting units and multiple quantities remain distinct.

Configured output/context/timeout limits remain unchanged. Model residency remains zero after each call to release memory for OCR. Review images, both readings, model identity, actual cache use and raw rejected responses remain available; matching model readings do not establish universal handwriting accuracy.
