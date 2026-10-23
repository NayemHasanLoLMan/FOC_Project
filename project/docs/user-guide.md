# User guide

## Automatic folder processing

1. Run project/.venv/Scripts/python.exe project/run_system.py and open http://127.0.0.1:8080/; see [operations](operations.md).
2. Place a completed PDF in the configured incoming folder. Prefer copying to a temporary filename and renaming it to .pdf after the copy finishes.
3. The scanner waits for stable observations, checks the PDF and queues an immutable copy.
4. The worker creates its Excel invoice using the shared template. The dashboard shows progress and the saved result.
5. Download the invoice from job detail or use the configured output folder.

The PC must be awake. With Stage 7 installed, processing starts in the background after Windows sign-in; a browser is not required. The same Python command remains available for foreground use. See [background operation](operations.md). The incoming folder is not watched recursively.

## Understand the dashboard

Overview separates the web page, folder scanner, invoice worker and local image reader. “Web available” does not mean the worker is running. A stale heartbeat is shown as unknown. Queued means waiting for the worker; waiting to save means an invoice was prepared but publication is blocked.

Jobs lists each source/content version once. A retry belongs to the same job as another processing run. Search by filename or recorded invoice number; filter by document date or status. Use the prominent View, Edit and Download actions.

The detail page explains **What happened**, shows invoice information and lists fields left blank. It uses “Invoice ready,” “Waiting to start” and other plain status labels. Developer details are available through the API rather than on the job page.

Image readings show the exact area read by the local image model and the highlighted original page. The page explains the value found and whether it was used. A reused saved reading still comes from the image model. An accepted reading can fail to contribute when a complete final field could not be established.

The source download is the accepted PDF snapshot, which may differ from a subsequently edited incoming file. The invoice download is the recorded output version, checked against its saved hash.

India invoice details show IEC/PAN/GST address information, destination, carton references, discharge port/terms and goods HS codes. Blank values use a dash; unsupported values are not inferred. India net weight is omitted. Earlier processing runs show their own saved information; original image readings remain available after manual edits. Use Preview Excel to inspect the invoice's printed layout.

## Blank fields and values

Unsupported/unreadable/conflicting information stays blank; no approval or validation prompt is added to the printed invoice. A completed invoice can therefore have missing information. Notes on the dashboard do not require intervention or automatically stop generation.

The PDF is the shipment source. Manual expected workbooks are development references and are never needed in production. Supported company-directory fallbacks and approved approximate valuation rates may supply maintained information/estimates. See [configuration](configuration.md) before changing those rules.

## Existing files and revisions

The queue preserves occupied output files and chooses a versioned filename when necessary. Identical unchanged arrivals do not create another job; changed bytes create a new source version. Renaming a PDF can create a distinct job because filenames may support invoice-number extraction.

Do not rename, edit or delete internal job snapshots/evidence to repair a result. Use the original PDF and the existing retry controls. Use Pause processing / Resume processing on Overview. Pause lets the current invoice finish while new PDFs continue to queue. On the latest eligible job detail, use Retry this PDF, Retry saving invoice, or Create another invoice. Earlier outputs stay available. A stopped worker must be started with run_system.py before queued requests can run.

Direct main.py/run_batch.py conversion remains available, but it is outside the durable queue. Its outputs do not automatically become dashboard jobs, and it does not provide queue-style historical collision protection. Prefer the folder pipeline for managed operations.

See [invoice downloads, web preview and development reset](user-guide.md) for clean filenames, local viewing and the isolated Clear data option.

## Edit and add information

Choose Edit on Jobs or Edit / add information on a completed job. Add missing header information or change goods, quantities, units and unit values. Save new invoice version creates a separate workbook through the existing worker; original outputs and source images remain available. No OCR/model inference repeats for a manual save. A paused queue must resume before that save runs.

Only the latest completed Bangladesh or India invoice can be edited; stale/concurrent saves are rejected. Bangladesh exposes its applicable TIN/cover-note fields; India exposes HS, discharge port and terms. Country/template/currency stay protected. Net weight is not offered. New goods need a unit value; missing quantity or value leaves the calculated amount and automatic total blank. Bangladesh totals round half up to whole dollars, India to cents. An explicit total can override the automatic calculation. Description/HS-only India edits preserve source money. Manual changes do not train the extractor; Create another invoice reads the PDF afresh without those overrides.

## Download and preview

Downloads use clean names such as 26S8185-I.xlsx; stored versions retain internal job/attempt suffixes for safety. Preview Excel shows the verified first invoice sheet locally, including merged cells, sizes, colors and borders. It is read-only and does not recalculate formulas or reproduce every Excel drawing/format/pagination feature. Use native Excel for final print verification. No upload, workbook macros or external links are executed by the preview.

## Clear data for testing

System → Clear data is available on the main coordinated launcher at 8080 and requires confirmation. It refuses active work; pause first if more jobs are queued. It archives job history, generated invoices from the current Bangladesh/India output folders and retained evidence, preserving input PDFs, templates, settings and model/OCR caches. A successful clear resumes scanning: remaining PDFs pass normal stable-file checks and generate invoices again. Sequence numbers are not reset; repeated delivery of the same request is idempotent.

Recovery copies live under runtime/cleared/<time>-<request-id>/. Other-volume output archives are recorded beside their output under .foc-cleared with matching external-output metadata. Older configured output roots are not cleared. A move failure rolls back; recovery after an OS crash must restore matching database/artifacts/outputs together. Archives are not automatically purged. A standalone dashboard cannot clear data. This intentionally exposed development feature needs an access-policy review before wider deployment.

For an isolated test workspace, run `project/.venv/Scripts/python.exe project/run_system.py --development --port 8081`. Its data stays under development/runtime; do not run tests against the main queue. Development mode cannot combine with custom config or startup installation.
