# User guide

## Automatic folder processing

1. Run project/.venv/Scripts/python.exe project/run_system.py and open http://127.0.0.1:8080/; see [operations](operations.md).
2. Place a completed PDF in the configured incoming folder. Prefer copying to a temporary filename and renaming it to .pdf after the copy finishes.
3. The scanner waits for stable observations, checks the PDF and queues an immutable copy.
4. The worker creates its Excel invoice using the shared template. The dashboard shows progress and the saved result.
5. Download the invoice from job detail or use the configured output folder.

The PC must be awake. The current version requires one manually launched Python command; automatic Windows startup is a later stage. The incoming folder is not watched recursively.

## Understand the dashboard

Overview separates the web page, folder scanner, invoice worker and local image reader. “Web available” does not mean the worker is running. A stale heartbeat is shown as unknown. Queued means waiting for the worker; waiting to save means an invoice was prepared but publication is blocked.

Jobs lists each source/content version once. A retry belongs to the same job as another processing run. Search by filename or recorded invoice number; filter by document date or status. Use the prominent View, Edit and Download actions.

The detail page explains **What happened**, shows invoice information and lists fields left blank. It uses “Invoice ready,” “Waiting to start” and other plain status labels. Developer details are available through the API rather than on the job page.

Image readings show the exact area read by the local image model and the highlighted original page. The page explains the value found and whether it was used. A reused saved reading still comes from the image model. An accepted reading can fail to contribute when a complete final field could not be established.

The source download is the accepted PDF snapshot, which may differ from a subsequently edited incoming file. The invoice download is the recorded output version, checked against its saved hash.

## Blank fields and values

Unsupported/unreadable/conflicting information stays blank; no approval or validation prompt is added to the printed invoice. A completed invoice can therefore have missing information. Notes on the dashboard do not require intervention or automatically stop generation.

The PDF is the shipment source. Manual expected workbooks are development references and are never needed in production. Supported company-directory fallbacks and approved approximate valuation rates may supply maintained information/estimates. See [configuration](configuration.md) before changing those rules.

## Existing files and revisions

The queue preserves occupied output files and chooses a versioned filename when necessary. Identical unchanged arrivals do not create another job; changed bytes create a new source version. Renaming a PDF can create a distinct job because filenames may support invoice-number extraction.

Do not rename, edit or delete internal job snapshots/evidence to repair a result. Use the original PDF and approved future retry controls. Use Pause processing / Resume processing on Overview. Pause lets the current invoice finish while new PDFs continue to queue. On the latest eligible job detail, use Retry this PDF, Retry saving invoice, or Create another invoice. Earlier outputs stay available. A stopped worker must be started with run_system.py before queued requests can run.

Direct main.py/run_batch.py conversion remains available, but it is outside the durable queue. Its outputs do not automatically become dashboard jobs, and it does not provide queue-style historical collision protection. Prefer the folder pipeline for managed operations.
