"""Legacy test-tool entry point; implementation lives in tests/evaluation."""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    runpy.run_path(str(ROOT / "tests/evaluation/compare_invoices.py"), run_name="__main__")
else:
    from tests.evaluation.compare_invoices import *
