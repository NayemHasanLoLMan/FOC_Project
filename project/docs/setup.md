# Installation and setup

## Supported baseline

The validated environment is Windows x64 with Python 3.12, local CPU PaddleOCR and an installed Ollama vision model. BD packing-list layouts and the BD template are the tested scope. Other platforms and India/Jordan extraction are not release acceptance claims.

Microsoft Excel is not required to generate .xlsx files or run the dashboard. It is required only for the optional native print-layout test. No Azure subscription or paid cloud document service is required.

## Python environment

Run from the repository/release root containing project/:

~~~powershell
py -3.12 -m venv project/.venv
project/.venv/Scripts/python.exe -m pip install -r project/requirements-lock.txt
project/.venv/Scripts/python.exe -m pip check
~~~

The lock file records the currently working Windows/Python versions, including transitive packages. It is a version snapshot, not a wheel archive or a hash-enforced lock. Installation still requires compatible packages to be available. To intentionally resolve newer dependencies within supported direct constraints, use requirements.txt in a separate environment and rerun acceptance before updating the lock.

The test suite uses Python unittest; no separate test framework is required.

## Local OCR and vision models

PaddleOCR uses the PP-OCRv5 mobile detector, English recognizer and page-orientation model. Initial model initialization may download required model files; later processing reuses project/.cache/paddlex. Do not assume a new machine is ready for offline use until models have been provisioned and a real PDF has passed.

Install Ollama using its [official Windows instructions](https://docs.ollama.com/windows). The application expects its local API at 127.0.0.1:11434. Provision the approved model explicitly if it is not already installed:

~~~powershell
ollama list
ollama pull qwen3-vl:latest
Invoke-RestMethod http://127.0.0.1:11434/api/tags
~~~

Pulling a model downloads it and can take substantial disk space/time; the invoice application never runs that command automatically. A mutable latest tag may resolve to a different digest later. Job evidence records the digest actually used; revalidate after changing models. To run without local vision, set pipeline_config.json local_model to null or use --no-local-vision on direct/batch commands.

## Initialize and verify

Review pipeline_config.json using the [configuration guide](configuration.md), then:

~~~powershell
project/.venv/Scripts/python.exe project/init_pipeline.py
project/.venv/Scripts/python.exe project/scan_incoming.py --once
project/.venv/Scripts/python.exe project/run_worker.py --once
~~~

Use an empty inbox for this smoke test. Initialization creates/migrates state but does not start processing. The one-shot worker may process a queued job if one exists.

For normal use, run project/.venv/Scripts/python.exe project/run_system.py. It initializes state and starts scanner, worker and dashboard together; see [operations](operations.md). The one-shot commands above are optional maintenance checks, not required startup steps.

## First real document / offline readiness

For a new document, use an isolated output folder:

~~~powershell
project/.venv/Scripts/python.exe project/main.py --pdf C:/shipments/test.pdf --output-dir C:/shipments/test-invoices --save-json
~~~

Check PDF facts, generated goods, blank unsupported fields and Excel print layout. Confirm local OCR/model availability before disconnecting network access. Dependency/model download caches are separate from retained job evidence.

Hardware throughput varies. Vision currently allows 4,096 output tokens, 8,192 context and a two-hour request timeout. Better hardware may reduce latency; it does not guarantee better extraction. Do not set a short external process timeout merely because no progress token is visible.

See [build](build.md) for a deployable source bundle, dependency wheel provisioning and the limits of the verified build.


### Optional India invoice-header fallback

India Fix 3 can use the already installed `qwen3.5:4b` only after an invalid primary invoice-header reading. On a new machine, provision it explicitly with `ollama pull qwen3.5:4b` if this fallback is wanted. The application does not download models. The primary model setting remains unchanged; this does not approve switching Bangladesh extraction to another model. Without the optional reader, the existing source-OCR/filename fallback still works, but unreadable handwriting may remain unresolved. See [Fix 3 acceptance](india_fix3_invoice_number.md) for the model comparison and limits.
