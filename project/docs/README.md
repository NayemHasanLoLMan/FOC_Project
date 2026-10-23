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
| [India fix checklist](india_fix_checklist.md) | Ordered India fixes and acceptance gates before moving to Jordan |
| [Invoice layout and India comparison](invoice_layout_review.md) | Complete sample reference comparison, supported blanks and reusable Bangladesh/India goods tables |
| [India shipment section](india_shipment_section.md) | Reusable shipment labels, PDF-backed port/terms values and intentionally blank departure slots |
| [India Fix 1](india_fix1_source_prices.md) | Source price/amount extraction, grouping and preservation acceptance |
| [India Fix 2](india_fix2_currency.md) | Source currency detection and safe rejection of unsupported/conflicting currency |
| [India Fix 3](india_fix3_invoice_number.md) | PDF-first invoice number, bounded image reading and filename-independent acceptance |
| [India Fix 4](india_fix4_headers.md) | Date, shipping-mark and airport layout tolerance with bounded source readings |
| [India Fix 5](india_fix5_continuation.md) | Supported goods continuation across adjacent tables/pages, with source and unit boundaries |
| [India Fix 6](india_fix6_header_verification.md) | Printed header comparison, visibility/format gates and safe publication failure |
| [India Fix 7](india_fix7_hs_continuation.md) | Source-backed HS continuation, conflict boundaries and leading-zero preservation |
| [India Fix 8 review](india_fix8_handwriting_review.md) | Fresh local handwriting comparisons and supported printed-description fallback; no production code change |
| [India Fix 9 review](india_fix9_runtime_review.md) | Measured cold/cache timings, zero fresh warm inference and accuracy-preserving runtime decisions |
| [India Fix 11](india_fix11_manual_editing.md) | Region-aware versioned editing, HS/port/terms, cent totals and preserved source evidence |
| [India Fix 12](india_fix12_dashboard_details.md) | Regional invoice details, HS/shipment labels, hidden net weight and original image review |
| [India / Jordan Stage 1](india_jordan_stage1.md) | Verified BD baseline, rollback instructions and all-page source checklist |
| [India / Jordan Stage 2](india_jordan_stage2.md) | Explicit country identity, schema migration, template provenance and verification |
| [India / Jordan Stage 3](india_jordan_stage3.md) | India master, expanding goods rows and native print acceptance |
| [India / Jordan Stage 4A](india_jordan_stage4.md) | India source extraction, real-model tests and source/reference acceptance |
| [India / Jordan Stage 4B](india_jordan_stage4b.md) | Approved India rates, cent totals and Bangladesh preservation checks |

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
