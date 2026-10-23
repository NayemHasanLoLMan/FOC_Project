# Readiness and remaining stages

Current checkpoint: 23 October 2026. Bangladesh and opt-in India use the same durable local pipeline, regional templates and one worker. Jordan automatic processing remains disabled. Manual references are QA-only and are never production inputs.

## Production pipeline checklist

- [x] Stage 1: configuration, durable job storage and safe initialization.
- [x] Stage 2: stable-file intake, immutable PDF snapshots and duplicate protection.
- [x] Stage 3: worker, safe publication, restart recovery and ownership locks.
- [x] Stage 4: processing evidence, exact model-input images and source-page review.
- [x] Stage 5: local dashboard, status, job details and verified downloads.
- [x] Stage 6: pause/resume, selected retry, save recovery and preserved reprocessing.
- [x] Stage 7: current-user Windows background startup and restart monitoring.
- [ ] Stage 8: coordinated Windows sign-out/reboot acceptance and final deployment rehearsal.

Dynamic settings, versioned editing, invoice preview, canonical download filenames and recoverable Clear data are implemented. Clear data remains exposed on the main local dashboard by the user's choice; review its availability before wider deployment.

## India checklist

- [x] Source prices/currency, PDF-first invoice number and variable-length serials.
- [x] Header/date/marks handling, goods continuations and source-backed HS continuation.
- [x] Printed-header verification before publication.
- [x] Handwriting and runtime reviews: retain readable printed fallback where handwriting cannot be established; reuse exact cached readings without lowering generous vision limits.
- [x] Regional editing, detail pages, valuation coverage review and separate folder processing.
- [x] Fix 15 available-sample release acceptance: 454 tests, dependency checks, 21 original invoices preserved, native Excel print review, real-PDF recovery checks and an extracted-package conversion without reference folders.
- [ ] Fix 10: additional unseen real India PDFs. Only one unique real India shipment is available; synthetic tests and cached runs do not establish future-document accuracy.

Accepted source/reference differences remain: packing date 13-Oct-2026, width 53 inches and declared estimated gross weight 106 kg. Unsupported CPT, discharge port and departure date are not copied from the manual reference. An unreadable handwritten subtype retains the printed FABRIC CUTTINGS description, 3 SETS.

## Jordan implementation sequence

Regional stages 1–4 established the baseline, country identity, India master and India extraction/valuation. Continue one stage at a time after user approval:

1. **Stage 5 — Jordan master and writer:** inspect all four source/reference pairs; remove duplicate template sections; preserve distinct KG/quantity/value columns; test growing rows, long descriptions, totals and native print. Preserve both existing country workflows.
2. **Stage 6 — Jordan extraction and valuation:** account for every page; preserve units, identifiers, origins and shared weights. Resolve 5173 page 6 naming an India consignee despite its Jordan cover before activation. Preserve partial/mixed origins in 5147 and 5197. Approve category/unit rates, label rules and rounding rather than forcing sample totals. Unsupported per-item weight/origin remains blank.
3. **Stage 7 — Jordan dashboard and folder activation:** reuse regional routing, immutable job region, image evidence, safe editing, recorded output roots and mixed-country reset/recovery. Enable only after isolated acceptance.
4. **Stage 8 — regional release acceptance:** compare source completeness, workbook/print presentation, fault recovery and a reference-free package; preserve Bangladesh and India results. Record unseen-sample and hardware limits separately.

Jordan rates are not approved yet. Existing Bangladesh whole-dollar and India cent-total rules must remain unchanged. Do not introduce a second queue, worker, OCR stack or web application for regional support.

## Evidence and limits

Latest detailed acceptance evidence remains locally under `project/reports/india_fix15_20261023/`. Earlier milestones, source-field contracts and rollback artifacts are archived in the development checkout. Historical scripts may require restoring original paths before rerunning.

New invoices use current masters; existing publications retain their saved appearance. No universal invoice accuracy percentage is established. Fresh-machine/offline provisioning, a physical printer and actual reboot acceptance remain unverified. New PDFs can still require long hardware-bound local inference.
