# India Fix 12 — invoice details and image review

23 October 2026. A regional presentation update to the existing job detail page. Only `dashboard.py` and `frontend/templates/detail.html` change in production. No extraction, valuation, edit contract, invoice writer/template, schema, model settings, folder activation or API route change.

## Delivered

India uses the immutable job region to choose its presentation. It shows invoice/date, consignee, address labelled IEC/PAN/GST, shipping marks, destination country/city, carton references, package count, gross weight, supported discharge port/terms and total. A goods HS-code column preserves literal text and leading zeros. Total/unit-value/item-value labels use the saved India currency, with the existing USD default; this does not enable non-USD invoice publication.

Blank values display a dash; zero remains zero. Header and goods values come from the selected saved version, including supported manual corrections. No source values, calculations or new inference are introduced. Currency/amount formatting in Excel remains the writer's responsibility; the page links to its existing Excel preview.

India hides net weight and irrelevant BD-only TIN/import-cover-note rows. A legacy missing-net-weight processing note is also suppressed for India, including manual versions. Raw data and recorded issues are retained; only the explanatory view changes. Address labels in reading summaries/image panels use IEC/PAN/GST for India. Bangladesh labels, displayed fields, notes and goods columns remain as before.

Original image crops, highlighted source-page previews, earlier processing runs, download/preview actions and manual editing remain available. HTML escaping is retained for source text and HS codes. Missing/unverified invoice data still shows the existing safe fallback.

## Acceptance

Evidence is in `reports/india_fix12_20261023/`:

- Six focused tests cover regional fields/currency, blank and zero values, escaped source text, earlier/current manual versions, read-only behavior, unavailable data and original image endpoints.
- Full regression: 438 tests. No source/model inference is needed to test this display update.
- The browser review uses a copied India sample and retained extraction/readings in an isolated queue. It verifies destination/carton/HS fields, blank port/terms, hidden net weight and functioning image panels. Three retained crop hashes and three highlighted page responses are checked.
- All 20 production Bangladesh detail pages are rendered with the backed-up template and the new template and compared semantically. Whitespace-only differences are ignored; visible text, structure, attributes and links must match.
- All 21 retained invoice datasets can be re-rendered without value/type/number-format differences. Templates and historical published invoices are protected by file hashes; production jobs/attempts/events/controls are compared with the stopped backup.
- Main dashboard/detail/edit/preview/download routes are checked after restart. The release is built and manifest-verified with development fixtures, reports and runtime data excluded.

This is not new-PDF extraction or an accuracy percentage. India folder watching remains disabled, and unseen-PDF validation remains pending. Native print testing is not repeated because no workbook writer, master or published workbook changes in this update; earlier print acceptance remains applicable.

Rollback: stop/drain, restore the matching `dashboard.py` and `detail.html` from `pre-fix12-backup.zip`, then restart. No database migration or record restoration is needed. Preserve any newly created invoices/history.

Next, after approval: Fix 13 reviews unsupported goods/unit valuation coverage using available source data. It must not invent shipment-specific rates or force totals to match manual references.
