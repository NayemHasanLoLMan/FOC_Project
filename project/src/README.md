# Backend

Production Python modules live in foc_extractor/. Existing imports use src.foc_extractor; the seven project-level CLI entry points remain unchanged. dashboard.py serves the separate ../frontend/ directory. No production module imports tests, tools or development.

See [code reference](../docs/code-reference.md), [architecture](../docs/architecture.md) and [configuration](../docs/configuration.md). Keep this directory in production.
