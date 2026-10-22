# Project documentation

Current scope: local PDF-to-BD-invoice conversion, a durable folder queue and a local admin dashboard. Stages 1–7 are implemented. Current-user background startup is documented in [Stage 7](pipeline_stage7.md); final production/reboot acceptance remains Stage 8.

| Guide | Audience / purpose |
|---|---|
| [Setup](setup.md) | Install on this Windows PC or a new Windows/Python environment |
| [User guide](user-guide.md) | Process PDFs and understand the dashboard without developer terminology |
| [Project structure](project-structure.md) | Production, development, fixture and local-data boundaries |
| [Architecture](architecture.md) | Components, data ownership, queue lifecycle and recovery |
| [Configuration](configuration.md) | Folder paths, model choice, templates, rates and precedence |
| [CLI reference](cli.md) | Every supported command, option and exit behavior |
| [HTTP API](api.md) | Routes, parameters, examples, response fields and errors |
| [OpenAPI 3.1 JSON](openapi.json) | Machine-readable route and schema reference |
| [Code reference](code-reference.md) | Python entry points, module responsibilities and data types |
| [Data and evidence](data-and-evidence.md) | SQLite tables, JSON receipts, workbook sheets and image provenance |
| [Build and release](build.md) | Test, package, verify, install, upgrade and roll back |
| [Operations](operations.md) | Start/stop, backup, recovery, privacy and troubleshooting |
| [Testing](testing.md) | Unit tests, evaluation tools, fixtures and result interpretation |
| [Contributing](contributing.md) | Small-change rules and required checks |
| [India / Jordan staged plan](india_jordan_implementation_plan.md) | Regional implementation sequence and review gates |
| [India / Jordan Stage 1](india_jordan_stage1.md) | Verified BD baseline, rollback instructions and all-page source checklist |
| [India / Jordan Stage 2](india_jordan_stage2.md) | Explicit country identity, schema migration, template provenance and verification |

The source code is authoritative. The API reference describes implemented read-only views and protected Stage 6 commands; it does not promise future controls. Null values mean unavailable data, not zero. Production conversion never reads manual expected invoices.

Historical development material is retained without moving its paths:

- [Sequential roadmap](pipeline_dashboard_plan.md): what was delivered and what still needs approval.
- Stage acceptance reports: [1](pipeline_stage1.md), [2](pipeline_stage2.md), [3](pipeline_stage3.md), [4](pipeline_stage4.md), [5](pipeline_stage5.md).
- [Processing rules](processing_flow.md) and [diagnosis](diagnosis.md): detailed extraction decisions and development-set limitations. Older milestone numbers are historical, not current guarantees.
- Local project/reports contains ignored generated QA evidence; it is not required by production and is excluded from release bundles.

- [Deployment boundaries](deployment-boundaries.md): required production files and safe cleanup.
- [Postman collection and usage](../development/postman/README.md): local API checks and protected admin commands.

- [Stage 6 controls and recovery](pipeline_stage6.md): pause/resume, selected retry, save recovery and preserved reprocessing.

- [Country folders and Bangladesh layout update](bd_layout_update.md): source-only TIN/cover note, red identifiers and no Bangladesh net weight.

See [manual invoice editing](manual-invoice-editing.md) for the simplified dashboard and safe versioned editing workflow.

See [invoice downloads, web preview and development reset](invoice-web-tools.md) for clean filenames, local viewing and the isolated Clear data option.
