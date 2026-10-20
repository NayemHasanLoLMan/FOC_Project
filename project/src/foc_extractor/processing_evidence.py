"""Optional processing observations; review artifacts never change invoice data."""
from contextvars import ContextVar
from functools import wraps
import hashlib
import io
import json
from pathlib import Path
import time
from uuid import uuid4

_observer = ContextVar('invoice_observer', default=None)
_accepted_refs = ContextVar('accepted_vision_refs', default=None)


class EvidenceWriteError(Exception):
    """Evidence failures must not be swallowed as OCR/model fallback failures."""


def emit(kind, *, png=None, **details):
    if kind == 'vision_decision' and details.get('accepted') and details.get('source_ref') and _accepted_refs.get() is not None:
        _accepted_refs.get().add(details['source_ref'])
    observer = _observer.get()
    if observer is not None:
        try:
            observer({'kind': kind, **details}, png=png)
        except Exception as exc:
            raise EvidenceWriteError('Could not persist processing evidence') from exc


def observed(function):
    @wraps(function)
    def wrapper(*args, observer=None, **kwargs):
        token = _observer.set(observer)
        refs_token = _accepted_refs.set(set())
        try:
            return track('pipeline', function, *args, **kwargs)
        finally:
            _observer.reset(token)
            _accepted_refs.reset(refs_token)
    return wrapper


def accepted_vision_refs():
    return _accepted_refs.get() or set()


def track(stage, function, *args, **kwargs):
    started = time.monotonic()
    emit('stage', stage=stage, status='started')
    try:
        value = function(*args, **kwargs)
    except Exception as exc:
        emit('stage', stage=stage, status='failed', error=f'{type(exc).__name__}: {exc}', elapsed_seconds=time.monotonic()-started)
        raise
    emit('stage', stage=stage, status='completed', elapsed_seconds=time.monotonic()-started)
    return value


def region(field, ocr, page, bbox, **details):
    return {'call_id': uuid4().hex, 'field': field, 'page': page+1, 'bbox': bbox,
            'dpi': ocr.dpi, 'coordinate_space': 'transformed_page_pixels',
            'transform': ocr.page_transforms[page] if page < len(ocr.page_transforms) else None, **details}


class EvidenceRecorder:
    def __init__(self, store, attempt, folder):
        self.store, self.attempt, self.folder = store, attempt, Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)

    def __call__(self, event, *, png=None):
        if event['kind'] == 'ocr_document':
            content = json.dumps(event['document'], ensure_ascii=False, allow_nan=False).encode('utf-8')
            target = self.folder / 'ocr.json'
            temporary = target.with_suffix('.tmp')
            temporary.write_bytes(content)
            temporary.replace(target)
            event = {'kind': 'ocr_document', 'artifact_path': str(target), 'sha256': hashlib.sha256(content).hexdigest(),
                     'pages': len(event['document']['pages']), 'transforms': event['document']['page_transforms']}
        if png is not None:
            digest = hashlib.sha256(png).hexdigest()
            target = self.folder / (digest+'.png')
            if target.exists():
                if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                    raise ValueError('Retained model image hash mismatch')
            else:
                temporary = target.with_suffix('.tmp')
                temporary.write_bytes(png)
                temporary.replace(target)
            event = {**event, 'image_path': str(target), 'image_sha256': digest}
        self.store.processing_event(self.attempt['id'], self.attempt['worker_id'], event)


def _artifact(store, job_id, event, path_key, hash_key):
    attempt = store.get_attempt(event['attempt_id'])
    base = Path(attempt['metadata']['configuration']['artifact_dir'])
    root = base / 'jobs' / str(job_id) / f"attempt-{attempt['id']}" / 'evidence'
    path = Path(event['details'][path_key])
    if not root.resolve().is_relative_to(base) or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Review artifact escapes its attempt storage')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != event['details'][hash_key]:
        raise ValueError('Review artifact hash mismatch')
    return content


def model_image(store, job_id, event_id):
    event = next(e for e in store.events(job_id) if e['id'] == event_id)
    if event['details'].get('kind') != 'vision_request':
        raise ValueError('Event is not a model image request')
    return _artifact(store, job_id, event, 'image_path', 'image_sha256')


def page_preview(store, job_id, page, event_id=None):
    """Render on demand in retained OCR coordinates; optionally highlight a request."""
    from PIL import ImageDraw
    from .ocr_engine import _cached_page_image
    events = store.events(job_id)
    selected = next((e for e in events if e['id'] == event_id), None)
    if event_id is not None and selected is None:
        raise ValueError('Review event is not part of this job')
    documents = [e for e in events if e['details'].get('kind') == 'ocr_document'
                 and (selected is None or e['attempt_id'] == selected['attempt_id'])]
    if not documents:
        raise FileNotFoundError('No retained OCR document for this attempt')
    document = json.loads(_artifact(store, job_id, documents[-1], 'artifact_path', 'sha256'))
    if type(page) is not int or not 1 <= page <= len(document['pages']):
        raise ValueError('Page is outside retained OCR coverage')
    job = store.get_job(job_id)
    source = Path(job['snapshot_path'])
    if hashlib.sha256(source.read_bytes()).hexdigest() != job['source_sha256']:
        raise ValueError('Source snapshot hash mismatch')
    transform = document['page_transforms'][page-1] if page <= len(document['page_transforms']) else None
    image = _cached_page_image(source, page-1, dpi=document['dpi'], transform=transform)
    if selected and selected['details'].get('page') == page and selected['details'].get('bbox'):
        ImageDraw.Draw(image).rectangle(selected['details']['bbox'], outline='red', width=6)
    image.thumbnail((1000, 1400))
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()
