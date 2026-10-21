# Frontend

Jinja HTML lives in templates/; dashboard CSS and JavaScript live in static/. Flask renders these files through the backend in ../src/foc_extractor/dashboard.py. The public static URL remains /dashboard_static/. There is no Node dependency or frontend compilation step.

Start with ../run_dashboard.py using the existing configuration. These assets are required in production; do not remove them. Extraction, queue state and file validation belong to the backend. See [structure](../docs/project-structure.md) and [API](../docs/api.md).
