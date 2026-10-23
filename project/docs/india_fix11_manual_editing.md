# India Fix 11 — safe manual editing

23 October 2026. Extend the established Bangladesh edit flow to completed India jobs. No schema migration, OCR/model change, template change, scanner activation or new endpoint/dependency.

## Delivered

- Reuse the existing latest-completed-version editor and protected edit command. Immutable job region selects the field and goods-row contract in the UI, HTTP API and queue store; the worker validates again against retained original data.
- India supports invoice number/date, consignee/address (IEC/PAN/GST), marks, carton references, destination city, packages/gross, port/terms, explicit total, and add/remove/edit goods with quantity/unit/unit value/HS code. HS text preserves leading zeros and is bounded to 20 characters. Unsupported BD-only TIN/import cover note and country changing are rejected for India. Source file, template, currency, source attribution and job region remain protected. Jordan remains unsupported.
- Changed/new monetary rows use Decimal half-up line rounding and India cent totals. Unchanged India line amounts remain authoritative, including source amounts not equal to quantity × unit price. Description/HS-only corrections preserve line amounts and an explicit original total. A monetary/row-list change recalculates the sum unless the user enters an explicit total. BD whole-dollar calculations and field contract remain unchanged.
- Original source snapshots, evidence, receipts and earlier invoices are preserved. Changed India description/quantity/unit/HS loses source row attribution; unchanged rows keep it. Manual corrections emit existing manual-edit evidence and do not rerun OCR or guess new unit rates.
- Existing request-ID replay protection, stale-version checks, locked-save retry, crash recovery, literal-text export and publication verification remain in use. An invalid generated invoice cannot replace a published original.
- India totals are calculated on save; an automatically cleared editor total is not submitted as an explicit blank override. HS/description-only edits leave it visible. A human can still explicitly clear or override the total. This also avoids submitting an automatic total change when a user reverts a goods edit.
- OpenAPI, Postman request instructions and user/API documentation describe both regional contracts. India's main detail-page HS/port labels and other regional presentation changes remain Fix 12.

## Acceptance

Evidence under `reports/india_fix11_20261023/`: nine focused tests, full regression log, isolated real-sample browser queue, native print samples, preservation results and release manifest. Tests cover headers, HS/leading zeros, literal formula-like text, added/removed/unpriced goods, source-amount preservation, explicit totals, protected fields, region isolation, stale/replayed requests, two edit generations, original image readings, locked publication, interrupted recovery and rejected publication.

The browser test uses retained India extraction and a copied PDF in an isolated queue; it is not fresh OCR or unseen-PDF acceptance. It saves port/terms/HS corrections as one new version, then quantity/unit-price/new-goods changes as another. Worker OCR is explicitly blocked throughout manual saves. Original source and earlier versions remain downloadable. Review-only values are not defaults or production data.

Production source, frontend, state, templates, evidence and output are backed up after drain. Preservation checks compare the stopped backup with production history/artifacts and all 20 retained Bangladesh parser/valuation results. The service is restarted and dashboard/detail/edit/preview/download routes checked. No production job is reprocessed for testing.

Rollback: stop/drain first, restore matching source and frontend files from `pre-fix11-backup.zip`, then restart. There is no migration to undo. Retain any new India edit records; older code cannot process their regional payloads. Do not replace a live database or discard new invoices just to roll back code.

## Remaining boundary

India automatic folder intake remains disabled; this supports India jobs already registered in the queue. Existing standalone CLI exports are not automatically imported. Additional unseen India PDF validation (Fix 10) remains pending. Origin, transport method and departure-date fields are not part of the current shared data model/editor. [Fix 12](india_fix12_dashboard_details.md) subsequently added HS/identifier/shipment presentation to India detail pages and removed irrelevant net-weight presentation.
