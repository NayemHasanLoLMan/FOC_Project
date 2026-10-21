# Postman API collection

Import FOC-Invoice.postman_collection.json and optionally Local.postman_environment.json into Postman. Use the desktop app or desktop agent to access localhost. Start the dashboard with the same configuration used by your scanner and worker:

~~~powershell
project/.venv/Scripts/python.exe project/run_dashboard.py --config project/pipeline_config.json
~~~

Select the local environment and send API > getStatus, then listJobs. All 14 implemented GET routes are grouped into API, Documents and images, and Dashboard pages. Names follow operationId in [OpenAPI](../../docs/openapi.json). Optional query parameters start disabled: enable them in Params when needed. No upload or process-control endpoint exists.

Edit the collection variables before sending ID-specific requests:

| Variable | Meaning |
|---|---|
| base_url | Local dashboard address; default http://127.0.0.1:8080 |
| job_id | Existing job ID returned by /api/jobs |
| attempt_id | Existing attempt ID from that job's detail response |
| event_id | Image-bearing evidence event ID belonging to the same job |
| pdf_page | Source PDF page number, starting at 1 |

The initial IDs are placeholders, not test fixtures. Use job detail to inspect attempts/evidence and choose matching IDs. The optional attempt query is an attempt ID, not a sequence number. The environment only sets base_url, so it does not shadow your collection IDs. Responses containing no jobs are valid for an empty production queue. Requests for absent IDs, unavailable invoices or events without retained images return errors by design; do not expect a whole collection run to pass without data.

The four unparameterized JSON requests include status/JSON checks. ID-specific requests are manual checks because they require your local data. No automatic retries, writes or stored customer responses are included. Imported files contain no credentials. Keep downloaded shipment data and saved responses local. The service is intended for loopback access; publishing the collection does not make it remotely accessible.

For full schemas, errors and file-integrity rules see [API documentation](../../docs/api.md). Tests verify the collection still covers every documented route. These development files are excluded from production builds.
