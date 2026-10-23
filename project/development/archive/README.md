# Historical material

`completed-milestones-20261023.zip` retains 36 completed stage/fix narratives and three retired evaluation wrappers, with SHA-256 values in `CLEANUP_MANIFEST.json`. Current instructions live in [docs](../../docs/README.md); [readiness](../../docs/readiness.md) retains unfinished work and the Jordan sequence.

Older generated QA runs and release bundles are retained locally in ignored `project/reports/archive/qa-history-20261023.zip` and `retired-releases-20261023.zip`. Latest India acceptance remains in `project/reports/india_fix15_20261023/`. Cleanup evidence and the pre-cleanup source snapshot are in `project/reports/repository_cleanup_20261023/`.

Entries are relative to `project/`, except the pre-cleanup source snapshot, whose entries are relative to the repository root. Each archive was hash-verified before source removal. Any old dependency junctions are recorded in `qa-links.json` inside the QA archive; their targets were not traversed or removed. These archives contain private shipment evidence and are excluded from production releases. Archiving reduces active clutter, not total backup disk usage.

For historical investigation, extract into a separate scratch directory and check `CLEANUP_MANIFEST.json`. Old scripts/configurations may contain absolute paths or import retired wrappers. To reproduce an old run, stop any affected test service and deliberately restore matching files to original paths, using matching code/environment. Never overlay an archive onto the live repository or point a historical demo at production state. A source snapshot alone is not a consistent production-data backup.
