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
                forbidden = {'tests','tools','development','examples','expected_outputs','reports','runtime','incoming','output','.venv','.cache','.git','__pycache__'}
                self.assertFalse(any(forbidden.intersection(Path(name).parts) for name in names))
                for name in ENTRY_POINTS:
                    self.assertIn('foc-invoice/project/'+name,names)
                self.assertEqual([name for name in names if Path(name).name=='README.md'],['foc-invoice/README.md'])
                for name in ('templates/BD_template.xlsx','docs/openapi.json','frontend/templates/detail.html',
                             'frontend/static/dashboard.js','requirements-lock.txt'):
                    self.assertIn('foc-invoice/project/'+name,names)
                for name in names:
                    if not name.endswith('.py'):continue
                    for node in ast.walk(ast.parse(archive.read(name))):
                        imports = [node.module or ''] if isinstance(node,ast.ImportFrom) else [a.name for a in node.names] if isinstance(node,ast.Import) else []
                        self.assertFalse(any(m.split('.')[0] in ('tests','tools','development') for m in imports),name)

    def test_build_refuses_to_replace_an_existing_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'release.zip'
            output.write_bytes(b'previous build')
            with self.assertRaises(FileExistsError):build_release(output)
            self.assertEqual(output.read_bytes(),b'previous build')

    def test_current_documentation_links_resolve_in_the_production_bundle(self):
        from tools.build_release import release_files
        files = set(release_files())
        for path in files:
            if path.suffix != '.md':continue
            for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
                if target.startswith(('http:','https:','#')):continue
                destination = (path.parent/target.split('#')[0]).resolve()
                self.assertIn(destination,files,(path.name,target))

    def test_postman_collection_covers_documented_routes(self):
        collection = json.loads((ROOT/'development/postman/FOC-Invoice.postman_collection.json').read_text())
        specification = json.loads((ROOT/'docs/openapi.json').read_text())
        requests = [item['request'] for group in collection['item'] for item in group['item']]
        routes = []
        for request in requests:
            self.assertIn(request['method'],('GET','POST'))
            route = request['url']['raw'].removeprefix('{{base_url}}')
            route = re.sub(r'\{\{(\w+)\}\}',lambda m:'{'+('page' if m[1]=='pdf_page' else m[1])+'}',route)
            routes.append((route,request['method'].lower()))
            documented = specification['paths'][route][request['method'].lower()].get('parameters',[])
            parameters = [specification['components']['parameters'][p['$ref'].split('/')[-1]] if '$ref' in p else p for p in documented]
            self.assertEqual({p['name'] for p in parameters if p['in']=='query'},
                             {p['key'] for p in request['url']['query']})
        self.assertEqual(len(routes),len(set(routes)))
        self.assertEqual(set(routes),{(route,method) for route,item in specification['paths'].items() for method in item if method in ('get','post')})
        variables = {v['key']:v['value'] for v in collection['variable']}
        self.assertEqual(variables['base_url'],'http://127.0.0.1:8080')

    def test_frontend_is_separate_with_compatible_static_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory)/'pipeline_config.json'
            config_path.write_text((ROOT/'pipeline_config.json').read_text())
            config = load_config(config_path)
            JobStore(config.state_dir/'jobs.sqlite3')
            app = create_app(config)
            self.assertEqual(Path(app.template_folder),ROOT/'frontend/templates')
            self.assertEqual(Path(app.static_folder),ROOT/'frontend/static')
            with app.test_client() as client:
                response = client.get('/dashboard_static/dashboard.js')
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.data,(ROOT/'frontend/static/dashboard.js').read_bytes())
                response.close()

    def test_openapi_matches_live_routes_and_all_references_resolve(self):
        specification = json.loads((ROOT/'docs/openapi.json').read_text())
        operation_ids = [operation['operationId'] for item in specification['paths'].values()
                         for method,operation in item.items() if method in ('get','post')]
        self.assertEqual(len(operation_ids),len(set(operation_ids)))
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
