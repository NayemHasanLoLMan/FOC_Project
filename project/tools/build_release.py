"""Build a production source ZIP without test or machine-local data."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINTS = ('main.py', 'run_batch.py', 'init_pipeline.py', 'scan_incoming.py', 'run_worker.py', 'run_dashboard.py')


def release_files(root=ROOT):
    fixed = [root.parent/'README.md', root/'README.md', root/'requirements.txt', root/'requirements-lock.txt',
             root/'pipeline_config.json', root/'valuation_rates.json', *(root/name for name in ENTRY_POINTS)]
    selected = fixed + [p for folder, suffixes in [('src', {'.py','.html','.css','.js'}),
                                                  ('templates',{'.xlsx'}), ('docs',{'.md','.json'})]
                        for p in (root/folder).rglob('*') if p.is_file() and p.suffix in suffixes and '__pycache__' not in p.parts]
    for path in selected:
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(root.parent.resolve()):
            raise ValueError(f'Missing or unsafe release input: {path}')
    return sorted(selected)


def build_release(output, root=ROOT):
    output = Path(output).resolve()
    files = release_files(root)
    version = next(ast.literal_eval(node.value) for node in ast.parse((root/'src/foc_extractor/__init__.py').read_text()).body
                   if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='__version__' for t in node.targets))
    manifest = {'application':'foc-invoice', 'version':version, 'format':'production-source',
                'requires':'Windows x64, Python 3.12, dependencies and local OCR/Ollama models installed separately',
                'files':{}}
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as handle:
        try:
            with zipfile.ZipFile(handle,'w',compression=zipfile.ZIP_DEFLATED) as archive:
                for source in files:
                    name = source.relative_to(root.parent).as_posix()
                    content = source.read_bytes()
                    manifest['files'][name] = hashlib.sha256(content).hexdigest()
                    archive.writestr('foc-invoice/'+name,content)
                archive.writestr('foc-invoice/BUILD_MANIFEST.json',json.dumps(manifest,indent=2))
        except BaseException:
            handle.close()
            output.unlink(missing_ok=True)
            raise
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'dist/foc-invoice.zip')
    args = parser.parse_args()
    print(build_release(args.output))


if __name__=='__main__':
    main()
