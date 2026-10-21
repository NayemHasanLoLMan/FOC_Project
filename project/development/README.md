# Development only

- analysis/: comparison against manual invoices, output validation and optional Excel print QA.
- postman/: importable collection/environment for all existing read-only HTTP routes.

Automated regression tests remain in ../tests/. Samples and manual references remain at ../examples/ and ../expected_outputs/ so saved commands and reports stay valid. Generated QA evidence stays in ../reports/. None of these folders is included in the production ZIP.

Use [build instructions](../docs/build.md) to create the clean production package. See [safe removal boundaries](../docs/deployment-boundaries.md) before cleaning an existing checkout; a demo configuration may reference reports.
