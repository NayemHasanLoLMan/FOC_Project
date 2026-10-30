"""One local worker using the existing converter and recoverable publication."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
import threading
from uuid import uuid4

from openpyxl import load_workbook
import pymupdf

from .folder_intake import _digest, _validate_pdf
from .job_store import JobStore
from .pipeline import run
from .excel_writer import populate_template
from .invoice_edits import edited_data
from .pipeline_config import ROOT, PipelineConfig, attempt_metadata
from .process_lock import process_lock
from .processing_evidence import EvidenceRecorder
from .workbook_verification import verify_workbook as _verify_workbook
from .pipeline import _resolve_template
from .development_reset import processing_cache_dir

HEARTBEAT_SECONDS = 5


def _write_json(path, value):
    temporary = path.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def _output_name(folder, name, job_id, attempt_id, prefer_base=True):
    candidate = folder / name
    if prefer_base and not os.path.lexists(candidate):
        return candidate
    version = 1
    while True:
        suffix = '' if version == 1 else f'-{version}'
        candidate = folder / f'{Path(name).stem}__job-{job_id}-attempt-{attempt_id}{suffix}.xlsx'
        if not os.path.lexists(candidate):
            return candidate
        version += 1


def _publish_copy(source, target, expected_digest, *, replace_existing=False):
    """Publish atomically; verified edits and reruns may replace their own output."""
    with NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copyfile(source, temporary)
        if _digest(temporary) != expected_digest:
            raise ValueError('Workbook changed while preparing its publication copy')
        if replace_existing:
            if os.path.lexists(target) and (target.is_symlink() or not target.is_file()):
                raise ValueError('The invoice output is not a regular file')
            os.replace(temporary, target)
        elif os.name == 'nt':
            os.rename(temporary, target)  # Windows rename refuses an existing destination.
        else:
            os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


class QueueWorker:
    def __init__(self, config: PipelineConfig, store: JobStore):
        self.config = config
        self.store = store
        self.owner = 'worker:' + uuid4().hex
        self.lock_path = store.path.parent / 'worker.lock'
        self.stop_requested = threading.Event()
        self._heartbeat_stop = threading.Event()
        self._heartbeat_error = None
        self._stack = ExitStack()

    def __enter__(self):
        try:
            self._stack.enter_context(process_lock(self.lock_path))
            self._startup_metadata = attempt_metadata(self.config)
            self._recover()
            self.store.component('worker', self.owner, os.getpid(), 'running')
            self._thread = threading.Thread(target=self._heartbeat, name='invoice-worker-heartbeat', daemon=True)
            self._thread.start()
            return self
        except BaseException:
            self._stack.close()
            raise

    def __exit__(self, kind, error, traceback):
        self._heartbeat_stop.set()
        self._thread.join()
        try:
            self.store.component('worker', self.owner, os.getpid(), 'failed' if error or self._heartbeat_error else 'stopped',
                                 str(error or self._heartbeat_error) if error or self._heartbeat_error else None)
        finally:
            self._stack.close()

    def _heartbeat(self):
        while not self._heartbeat_stop.wait(HEARTBEAT_SECONDS):
            try:
                self.store.touch_worker(self.owner)
            except Exception as exc:
                self._heartbeat_error = exc
                self.stop_requested.set()
                return

    def _healthy(self):
        if self._heartbeat_error is not None:
            raise RuntimeError('Worker heartbeat failed; restart to recover its attempt') from self._heartbeat_error

    def _receipt_path(self, attempt):
        root = Path(attempt['metadata']['configuration']['artifact_dir'])
        return root / 'jobs' / str(attempt['job_id']) / f"attempt-{attempt['id']}" / 'ready.json'

    def _read_ready(self, attempt):
        path = self._receipt_path(attempt)
        if path.is_symlink() or not path.resolve().is_relative_to(Path(attempt['metadata']['configuration']['artifact_dir'])):
            raise ValueError('Prepared receipt escapes its artifact directory')
        ready = json.loads(path.read_text(encoding='utf-8'))
        job = self.store.get_job(attempt['job_id'])
        if (ready['job_id'], ready['attempt_id'], ready['source_sha256']) != (job['id'], attempt['id'], job['source_sha256']):
            raise ValueError('Prepared receipt identifies another input or attempt')
        for key in ('workbook_name', 'data_name'):
            if Path(ready[key]).name != ready[key]:
                raise ValueError('Prepared artifact name is not a basename')
        prepared = path.parent / ready['workbook_name']
        data_path = path.parent / ready['data_name']
        for file, digest in [(prepared, ready['workbook_sha256']), (data_path, ready['data_sha256'])]:
            if file.is_symlink() or not file.resolve().is_relative_to(path.parent.resolve()) or _digest(file) != digest:
                raise ValueError('Prepared artifact failed hash/path verification')
        target = Path(ready['destination'])
        if (not target.is_absolute() or target.parent != Path(attempt['metadata'].get('output_dir', attempt['metadata']['configuration']['output_dir']))
                or target.suffix.lower() != '.xlsx'):
            raise ValueError('Prepared destination escapes its output directory')
        if ready.get('replace_existing'):
            edit = attempt['metadata'].get('manual_edit')
            base_id = edit['base_attempt_id'] if edit else attempt['metadata'].get('reprocess_base_attempt_id')
            if not base_id:
                raise ValueError('Only an invoice edit or rerun can replace an output file')
            base = self.store.get_attempt(base_id)
            if base['job_id']!=job['id'] or base['state']!='completed' or Path(base['output_path'])!=target:
                raise ValueError('Replacement output does not belong to this invoice')
        if _digest(job['snapshot_path']) != job['source_sha256']:
            raise ValueError('Source snapshot has changed since intake')
        region = attempt['metadata'].get('region', 'BD')
        if region != job['region'] or ready.get('region', 'BD') != region:
            raise ValueError('Prepared invoice region does not match its job')
        return path, ready, prepared

    def _recover(self):
        for attempt in self.store.unfinished_attempts():
            if attempt['metadata'].get('worker_lock') != str(self.lock_path):
                raise RuntimeError('An unfinished attempt is not owned by this managed worker; refusing automatic takeover')
            receipt = None
            try:
                self._read_ready(attempt)
                receipt = self._receipt_path(attempt)
            except (OSError, ValueError, KeyError, TypeError):
                pass
            self.store.recover_attempt(attempt['id'], attempt['worker_id'], self.owner, self.lock_path, receipt)

    def _publish(self, attempt):
        try:
            receipt, ready, prepared = self._read_ready(attempt)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.store.finish(attempt['id'], self.owner, 'failed', error='Prepared artifact verification failed: ' + str(exc))
            return
        try:
            target = Path(ready['destination'])
            if target.parent.resolve() != target.parent:
                raise ValueError('Output directory changed to a different resolved path')
            target.parent.mkdir(parents=True, exist_ok=True)
            for _ in range(3):
                if os.path.lexists(target):
                    if not target.is_symlink() and target.is_file() and _digest(target) == ready['workbook_sha256']:
                        break  # Reconcile a crash after publication but before the DB commit.
                    if not ready.get('replace_existing'):
                        target = _output_name(target.parent, ready['workbook_name'], attempt['job_id'], attempt['id'], False)
                        ready['destination'] = str(target)
                        _write_json(receipt, ready)
                try:
                    if ready.get('replace_existing'):
                        _publish_copy(prepared, target, ready['workbook_sha256'], replace_existing=True)
                    else:
                        _publish_copy(prepared, target, ready['workbook_sha256'])
                    break
                except FileExistsError:
                    continue
            else:
                raise OSError('Output destination kept changing; publication will retry later')
            if _digest(target) != ready['workbook_sha256']:
                raise ValueError('Published workbook failed hash verification')
        except OSError as exc:
            self.store.publication_error(attempt['id'], self.owner, str(exc))
            return
        except (ValueError, KeyError, TypeError) as exc:
            self.store.finish(attempt['id'], self.owner, 'failed', error='Prepared artifact verification failed: ' + str(exc))
            return
        self._healthy()
        self.store.finish(attempt['id'], self.owner, 'completed', output_path=target)

    def run_once(self, *, job_id=None):
        self._healthy()
        for attempt in self.store.unfinished_attempts():
            if attempt['state'] == 'waiting_to_save' and attempt['worker_id'] == self.owner and (job_id is None or attempt['job_id'] == job_id):
                self._publish(attempt)
        if self.stop_requested.is_set():
            return None
        metadata = attempt_metadata(self.config)
        if metadata['application_sha256'] != self._startup_metadata['application_sha256']:
            raise RuntimeError('Application files changed; restart the worker before processing')
        def metadata_for(job):
            value = {**attempt_metadata(self.config, job['region']),
                     'worker_lock':str(self.lock_path),'worker_pid':os.getpid()}
            if job.get('manual_edit_json'):
                edit = json.loads(job['manual_edit_json'])
                base = self.store.get_attempt(edit['base_attempt_id'])
                value['output_dir'] = str(Path(base['output_path']).parent)
            else:
                base = next((a for a in reversed(self.store.attempts(job['id'])) if a['state']=='completed'),None)
                if base:
                    value['reprocess_base_attempt_id'] = base['id']
                    value['output_dir'] = str(Path(base['output_path']).parent)
            return value
        attempt = self.store.claim_next(self.owner, metadata_for, job_id=job_id) if job_id is not None else self.store.claim_next(self.owner, metadata_for)
        if attempt is None:
            return None
        metadata = attempt['metadata']
        job = self.store.get_job(attempt['job_id'])
        try:
            region = job['region']
            template = _resolve_template(None, region)
            if metadata['region'] != region or metadata['template_path'] != str(template):
                raise ValueError('Attempt template does not match its queued region')
            source = Path(job['snapshot_path'])
            if source.name != Path(job['source_path']).name or _digest(source) != job['source_sha256']:
                raise ValueError('Input snapshot filename or SHA-256 does not match its queued source')
            _validate_pdf(source)
            receipt = self._receipt_path(attempt)
            folder = receipt.parent
            if not folder.resolve().is_relative_to(self.config.artifact_dir):
                raise ValueError('Attempt directory escapes managed artifact storage')
            folder.mkdir(parents=True, exist_ok=True)
            observer = EvidenceRecorder(self.store, attempt, folder / 'evidence')
            if metadata.get('manual_edit'):
                edit = metadata['manual_edit']
                base = self.store.get_attempt(edit['base_attempt_id'])
                if base['job_id'] != job['id'] or base['state'] != 'completed':
                    raise ValueError('The original invoice does not belong to this completed job')
                base_receipt, previous, _ = self._read_ready(base)
                original = json.loads((base_receipt.parent/previous['data_name']).read_text(encoding='utf-8'))
                data = edited_data(original,edit['changes'])
                workbook = folder/previous['workbook_name']
                populate_template(template,workbook,data)
                _write_json(folder/(source.stem+'.json'),data.to_dict())
                for field in edit['changes']:
                    observer({'kind':'field_source','field':field,'method':'manual_edit','value':getattr(data,field) if field!='items' else [i.__dict__ for i in data.items]})
                unresolved = [f for f in ('invoice_number','export_date','consignee','consignee_address','shipping_marks','package_count','gross_weight_kg','total_value') if getattr(data,f) is None]
                unresolved.extend(f'goods:{n+1}:{key}' for n,item in enumerate(data.items) for key in ('description','quantity','unit','unit_price') if getattr(item,key) in (None,''))
                if not data.items:
                    unresolved.append('goods')
                observer({'kind':'invoice_evidence','vision_contributions':[], 'unresolved_fields':unresolved})
            else:
                from .local_vision import vision_limits
                with vision_limits(self.config):
                    workbook = Path(run(source, template=template, region=region, output_dir=folder,
                                        save_json=True, cache_dir=processing_cache_dir(self.config), local_model=self.config.local_model,
                                        observer=observer)).resolve()
            if workbook.parent != folder or workbook.suffix.lower() != '.xlsx':
                raise ValueError('Converter returned an unexpected output path')
            data_path = folder / f'{source.stem}.json'
            data = json.loads(data_path.read_text(encoding='utf-8'))
            _verify_workbook(workbook, data, source, region)
            after = attempt_metadata(self.config, region)
            if (_digest(source) != job['source_sha256'] or any(after[key] != metadata[key]
                    for key in ('template_sha256', 'rates_sha256', 'application_sha256', 'factory_profiles_sha256'))):
                raise ValueError('Source, template, rates, factory master or application changed during conversion')
            if metadata.get('manual_edit') or metadata.get('reprocess_base_attempt_id'):
                if not metadata.get('manual_edit'):
                    base = self.store.get_attempt(metadata['reprocess_base_attempt_id'])
                    _,previous,_ = self._read_ready(base)
                target = Path(base['output_path'])
                if base['job_id']!=job['id'] or target!=Path(previous['destination']):
                    raise ValueError('Replacement output does not match the original invoice')
            else:
                target = _output_name(Path(metadata['output_dir']), workbook.name, job['id'], attempt['id'])
            _write_json(receipt, {'job_id': job['id'], 'attempt_id': attempt['id'], 'source_sha256': job['source_sha256'], 'region':region,
                                 'workbook_name': workbook.name, 'workbook_sha256': _digest(workbook),
                                 'data_name': data_path.name, 'data_sha256': _digest(data_path), 'destination': str(target),
                                 'replace_existing':bool(metadata.get('manual_edit') or metadata.get('reprocess_base_attempt_id'))})
        except Exception as exc:
            self.store.finish(attempt['id'], self.owner, 'failed', error=f'{type(exc).__name__}: {exc}')
            return attempt['id']
        self._healthy()
        self.store.prepare(attempt['id'], self.owner, receipt)
        self._publish(self.store.get_attempt(attempt['id']))
        return attempt['id']
