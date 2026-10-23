# Development workspace

Nothing here is required by the production source ZIP.

| Folder | Purpose |
|---|---|
| `analysis/` | Canonical invoice comparison, output checks and optional Excel print QA |
| `postman/` | API collection and local environment; see [usage](postman/README.md) |
| `archive/` | Completed milestone notes and retired wrapper source |
| `runtime/` | Preserved isolated development workspace; local data, not disposable code |

Regression tests live in `project/tests/`. Test PDFs and manual references remain in `project/examples/` and `project/expected_outputs/`; preserve these for regression checks and upcoming Jordan work. Generated QA runs and historical evidence archives live in ignored `project/reports/`.

Use [testing](../docs/testing.md) and [build](../docs/build.md). Run analysis tools directly from `development/analysis/`; obsolete `tools/` forwarding files were retired. Application imports, entry points and production data locations stay unchanged.
