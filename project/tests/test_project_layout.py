import ast
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.build_release import build_release, ENTRY_POINTS
from src.foc_extractor.dashboard import create_app
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.pipeline_config import load_config


class ProjectLayoutTests(unittest.TestCase):
    def test_production_archive_manifest_and_dependency_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            output = build_release(Path(directory)/'release.zip')
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                self.assertIsNone(archive.testzip())
                manifest = json.loads(archive.read('foc-invoice/BUILD_MANIFEST.json'))
                self.assertEqual(set(names),{'foc-invoice/'+name for name in manifest['files']}|{'foc-invoice/BUILD_MANIFEST.json'})
                for name,digest in manifest['files'].items():
                    self.assertEqual(hashlib.sha256(archive.read('foc-invoice/'+name)).hexdigest(),digest)
                forbidden = {'tests','tools','examples','expected_outputs','reports','runtime','incoming','output','.venv','.cache','.git','__pycache__'}
                self.assertFalse(any(forbidden.intersection(Path(name).parts) for name in names))
                for name in ENTRY_POINTS:
                    self.assertIn('foc-invoice/project/'+name,names)
                for name in ('templates/BD_template.xlsx','docs/openapi.json','src/foc_extractor/dashboard_templates/detail.html',
                             'src/foc_extractor/dashboard_static/dashboard.js','requirements-lock.txt'):
                    self.assertIn('foc-invoice/project/'+name,names)
                for name in names:
                    if not name.endswith('.py'):continue
                    for node in ast.walk(ast.parse(archive.read(name))):
                        imports = [node.module or ''] if isinstance(node,ast.ImportFrom) else [a.name for a in node.names] if isinstance(node,ast.Import) else []
                        self.assertFalse(any(m.split('.')[0] in ('tests','tools') for m in imports),name)

    def test_build_refuses_to_replace_an_existing_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'release.zip'
            output.write_bytes(b'previous build')
            with self.assertRaises(FileExistsError):build_release(output)
            self.assertEqual(output.read_bytes(),b'previous build')

    def test_legacy_comparison_imports_use_the_separated_implementation(self):
        from tools import compare_invoices as old
        from tests.evaluation import compare_invoices as current
        self.assertIs(old.read_invoice,current.read_invoice)
        self.assertIs(old.compare,current.compare)
        self.assertEqual(old.ROOT,ROOT)

    def test_openapi_matches_live_routes_and_all_references_resolve(self):
        specification = json.loads((ROOT/'docs/openapi.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory)/'pipeline_config.json'
            config_path.write_text((ROOT/'pipeline_config.json').read_text())
            config = load_config(config_path)
            JobStore(config.state_dir/'jobs.sqlite3')
            app = create_app(config)
            routes = {re.sub(r'<(?:int:)?(\w+)>',r'{\1}',rule.rule) for rule in app.url_map.iter_rules() if rule.endpoint!='static'}
        self.assertEqual(set(specification['paths']),routes)
        def check(value):
            if isinstance(value,dict):
                if '$ref' in value:
                    target = specification
                    for key in value['$ref'].removeprefix('#/').split('/'):target=target[key]
                for child in value.values():check(child)
            elif isinstance(value,list):
                for child in value:check(child)
        check(specification)
        self.assertEqual(specification['openapi'],'3.1.0')


if __name__=='__main__':unittest.main()
