# Postman API collection

Import FOC-Invoice.postman_collection.json and optionally Local.postman_environment.json into Postman. Use the desktop app or desktop agent to access localhost. Start the dashboard with the same configuration used by your scanner and worker:

~~~powershell
project/.venv/Scripts/python.exe project/run_dashboard.py --config project/pipeline_config.json
~~~

Select the local environment and send API > getStatus, then listJobs. The 15 GET views and five protected POST commands are grouped into API, Documents and images, Dashboard pages, and Admin controls. Names follow operationId in [OpenAPI](../../docs/openapi.json). Optional query parameters start disabled: enable them in Params when needed. No upload, settings or forced cancellation endpoint exists.

Edit the collection variables before sending ID-specific requests:

| Variable | Meaning |
|---|---|
| base_url | Local dashboard address; default http://127.0.0.1:8080 |
| job_id | Existing job ID returned by /api/jobs |
| attempt_id | Existing attempt ID from that job's detail response |
| event_id | Image-bearing evidence event ID belonging to the same job |
| pdf_page | Source PDF page number, starting at 1 |

The initial IDs are placeholders, not test fixtures. Use job detail to inspect attempts/evidence and choose matching IDs. The optional attempt query is an attempt ID, not a sequence number. The environment only sets base_url, so it does not shadow your collection IDs. Responses containing no jobs are valid for an empty production queue. Requests for absent IDs, unavailable invoices or events without retained images return errors by design; do not expect a whole collection run to pass without data.

The four unparameterized JSON requests include status/JSON checks. ID-specific requests are manual checks because they require your local data. No automatic retries or stored customer responses are included. Only the Admin controls folder contains queue-changing requests. Imported files contain no credentials. Keep downloaded shipment data and saved responses local. The service is intended for loopback access; publishing the collection does not make it remotely accessible.

For full schemas, errors and file-integrity rules see [API documentation](../../docs/api.md). Tests verify the collection still covers every documented route. These development files are excluded from production builds.

Stage 6: send getControls first to save the current csrf_token. The Admin controls folder changes queue state; use an isolated test queue when experimenting. Origin and token headers are supplied. Select the latest attempt_id for a job action. Request bodies use a dynamic UUID for each new send; to repeat an uncertain request, replace it with the original request_id so the saved result is replayed. Refresh the token after a server restart. A full collection run can pause/resume/reprocess eligible data; do not run it blindly against production.

The invoice-tools group includes local invoice preview and Clear data on the main coordinated launcher (8080) or isolated development launcher (8081). Clearing archives current generated files, clears history and resumes automatic invoice creation from remaining inbox PDFs. Do not run the reset request unless that is intended. See ../../docs/invoice-web-tools.md.
