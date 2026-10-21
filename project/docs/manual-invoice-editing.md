# Edit an invoice

On Jobs, choose **Edit**, or open **View** and choose **Edit / add information**. Add missing fields or change existing invoice information. You can add, remove or change goods, quantities, units and unit values. Blank fields remain empty. Bangladesh net weight is not offered.

Choose **Save new invoice version**. The running worker uses the existing shared template and saves a separate Excel file; the original invoice remains available in history. No OCR or image-model inference is repeated for a manual save. If processing is paused, your change waits until processing resumes. A stopped system must be started with the normal single command.

Goods changes recalculate line amounts to cents and the shipment total to the nearest whole dollar. You may enter a different total. New rows need their own unit value; the editor does not guess a new rate. Missing quantity or price leaves that line value and automatic total empty.

Original PDF images and readings remain available and are labelled as original readings. Changed descriptions, quantities or units lose their old row source attribution; manually entered facts are not presented as PDF extractions. Editing does not alter the PDF or teach the extractor a rule for later PDFs.

Only the latest completed Bangladesh invoice can be edited. Concurrent or stale submissions are rejected; reload the latest invoice before trying again. Repeated delivery of the same save request does not create duplicate work. Retry preserves an interrupted edit; **Create another invoice** processes the PDF afresh and discards manual overrides for that new version.

## API

GET /jobs/{job_id}/edit opens the editor. POST /api/jobs/{job_id}/edit uses the existing matching Origin and X-CSRF-Token protection, plus a UUID request_id, current completed attempt_id and nonempty changes object. The body limit is 65,536 bytes. See [OpenAPI](openapi.json) for the complete field allowlist and limits.

Example changes: {"tin_number":"User supplied identifier","gross_weight_kg":12.5}. Send only changed fields. An empty string clears an optional field. If items is supplied it replaces the goods list, limited to 200 rows, each containing source_index (original zero-based row or null), description, quantity, unit and unit_price. Amounts are calculated on the server. Unsupported/protected properties are rejected.

Schema 5 adds jobs.manual_edit_json. The queued edit records its base attempt and changes, copied into the new attempt metadata. Changes are validated before queuing and again when preparing the workbook. Existing publication, hash verification and crash recovery apply. Back up schema 4 state before migration; older code cannot open schema 5.
