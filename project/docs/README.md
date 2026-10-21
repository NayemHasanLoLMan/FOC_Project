# Project documentation

Current scope: local PDF-to-BD-invoice conversion, a durable folder queue and a read-only dashboard. Stages 1–5 are implemented. Admin controls, unattended Windows startup and the final production acceptance gate remain pending.

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

The source code is authoritative. The API reference describes implemented read-only endpoints; it does not promise future controls. Null values mean unavailable data, not zero. Production conversion never reads manual expected invoices.

Historical development material is retained without moving its paths:

- [Sequential roadmap](pipeline_dashboard_plan.md): what was delivered and what still needs approval.
- Stage acceptance reports: [1](pipeline_stage1.md), [2](pipeline_stage2.md), [3](pipeline_stage3.md), [4](pipeline_stage4.md), [5](pipeline_stage5.md).
- [Processing rules](processing_flow.md) and [diagnosis](diagnosis.md): detailed extraction decisions and development-set limitations. Older milestone numbers are historical, not current guarantees.
- Local project/reports contains ignored generated QA evidence; it is not required by production and is excluded from release bundles.

- [Deployment boundaries](deployment-boundaries.md): required production files and safe cleanup.
- [Postman collection and usage](../development/postman/README.md): local read-only API checks.
