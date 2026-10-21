# Development rules and change checklist

Use the smallest shared change that addresses a demonstrated problem:

1. Skip what is unnecessary.
2. Reuse code already here.
3. Prefer the standard library, native platform feature or installed dependency.
4. Add the minimum clear logic and a small meaningful test.

Backend code stays in src/foc_extractor and the seven CLI entry points; frontend assets stay in frontend/. Unit tests stay under tests; analysis and Postman files stay under development; release tooling stays under tools. Production must not import tests/tools/development, manual references or generated reports.

Before editing a shared function, search every caller. Preserve direct, batch, worker and dashboard contracts. New route parameters and response changes must update api.md/openapi.json, the development/postman collection and route-coverage tests. Add documentation to docs/README.md rather than scattering current instructions through historical reports.

Use explicit temporary directories for tests. Preserve canonical PDFs/manual references/templates. Never use an expected invoice as runtime lookup, add shipment-ID answers, infer missing package counts from weight, or print human-intervention wording onto invoices. Source-grounded extraction and approved rates remain the rules.

For a code/logic change:

- Reproduce the case with a focused test.
- Run relevant tests, then the existing full suite if shared behavior changes.
- Check preserved invoice facts/styles and appropriate real-PDF/reference cases.
- Test new file/state/HTTP trust boundaries and failure/recovery cases.
- Update current code/API/configuration/build documentation where contracts changed.
- Build the release and verify it excludes private/local/test data.

Use requirements.txt for direct constraints. Validate dependency updates in a separate environment, run acceptance, then update requirements-lock.txt. Do not silently upgrade the working OCR stack as part of unrelated changes. The lock is platform-specific and not an offline installation bundle.

No API mutation/admin control or startup-task stage is approved by a documentation/organization task. Follow the staged roadmap and ask before advancing to the next implementation stage.

Do not commit .venv, .cache, incoming PDFs, runtime state, generated invoices, reports, build ZIPs or secrets. Historical reports are private local QA artifacts; they are not product code.
