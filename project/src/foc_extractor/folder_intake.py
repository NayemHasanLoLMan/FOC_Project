"""Poll and validate PDF arrivals; queue snapshots without running extraction."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
import time

import pymupdf

from .job_store import JobStore, _identity
from .pipeline_config import PipelineConfig


class SourceChangedError(OSError):
    pass


class InvalidPDFError(ValueError):
    pass


def _fingerprint(path):
    stat = path.stat()
    return (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns, stat.st_dev, stat.st_ino)


def _digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _validate_pdf(path):
    with Path(path).open('rb') as stream:
        stream.seek(0, 2)
        stream.seek(max(0, stream.tell() - 1024))
        if not stream.read().rstrip(b'\x00 \t\r\n\f').endswith(b'%%EOF'):
            raise InvalidPDFError('PDF end marker is missing; wait for the completed copy')
    try:
        with pymupdf.open(path) as document:
            if not document.is_pdf or document.page_count < 1:
                raise InvalidPDFError('File is not a PDF with readable pages')
            if document.needs_pass:
                raise InvalidPDFError('PDF requires a password; automatic intake cannot read it')
            if document.is_repaired:
                raise InvalidPDFError('PDF requires structural repair; wait for a complete, valid copy')
            for page in range(document.page_count):
                document.load_page(page)
    except (RuntimeError, ValueError) as exc:
        raise InvalidPDFError(str(exc)) from exc


class FolderScanner:
    def __init__(self, config: PipelineConfig, store: JobStore):
        self.config = config
        self.store = store

    def _snapshot(self, source, digest, fingerprint):
        identity = hashlib.sha256(_identity(source).encode()).hexdigest()
        target = self.config.artifact_dir / 'inputs' / identity / digest / source.name
        if not target.resolve().is_relative_to(self.config.artifact_dir) or target.is_symlink():
            raise OSError('Snapshot path escapes managed artifact storage or is a symbolic link')
        if target.exists():
            if _digest(target) != digest:
                raise OSError('Stored snapshot has changed; refusing to overwrite it')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(dir=target.parent, suffix='.tmp', delete=False) as handle:
                temporary = Path(handle.name)
            try:
                shutil.copyfile(source, temporary)
                if (_digest(temporary) != digest or _fingerprint(source) != fingerprint
                        or _digest(source) != digest):
                    raise SourceChangedError('Source changed while copying; waiting for stable bytes')
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        if _fingerprint(source) != fingerprint or _digest(source) != digest:
            raise SourceChangedError('Source changed before intake completed; waiting for stable bytes')
        return target

    def scan_once(self):
        scans = {region: self._scan_folder(folder, region) for region, folder in self.config.inboxes().items()}
        result = dict(scans['BD']) if 'BD' in scans else {
            'scanned_at':datetime.fromtimestamp(time.time(),timezone.utc).isoformat(),
            'incoming_dir':str(self.config.incoming_dir),'region':'BD'}
        result['folders'] = scans
        result['accepted_job_ids'] = [job for scan in scans.values() for job in scan['accepted_job_ids']]
        result['errors'] = [error for scan in scans.values() for error in scan['errors']]
        result['folder_error'] = '; '.join(region + ': ' + scan['folder_error'] for region, scan in scans.items()
                                          if scan['folder_error']) or None
        result['intake_counts'] = dict(sum((Counter(scan['intake_counts']) for scan in scans.values()), Counter()))
        result['jobs'] = self.store.counts()
        return result

    def _scan_folder(self, folder, region):
        now = time.time()
        result = {'scanned_at': datetime.fromtimestamp(now, timezone.utc).isoformat(),
                  'incoming_dir': str(folder), 'region': region, 'folder_error': None,
                  'accepted_job_ids': [], 'errors': []}
        try:
            entries = sorted(folder.iterdir(), key=lambda path: path.name.casefold())
        except OSError as exc:
            result['folder_error'] = str(exc)
            entries = None
        if entries is not None:
            seen = set()
            for source in entries:
                name = source.name.lower()
                if (source.suffix.lower() != '.pdf' or name.startswith(('.', '~$'))
                        or name.endswith(('.tmp.pdf', '.part.pdf', '.partial.pdf', '.crdownload.pdf', '.download.pdf'))):
                    continue
                identity = None
                try:
                    if source.is_symlink():
                        result['errors'].append({'source': source.name, 'error': 'Symbolic-link inputs are ignored'})
                        continue
                    identity = _identity(source)
                    seen.add(identity)
                    if not source.is_file():
                        seen.discard(identity)
                        continue
                    fingerprint = _fingerprint(source)
                    digest = _digest(source)
                    if _fingerprint(source) != fingerprint:
                        raise SourceChangedError('Source changed during hashing; waiting for stable bytes')
                    signature = json.dumps([fingerprint, digest])
                    record = self.store.observe_intake(source, signature, now)
                    if record['job_id'] and self.store.get_job(record['job_id'])['region'] != region:
                        raise ValueError('This input folder contains jobs accepted for another country')
                    if record['state'] in ('queued', 'rejected') or now - record['stable_since'] < self.config.scan_interval_seconds:
                        continue
                    snapshot = self._snapshot(source, digest, fingerprint)
                    _validate_pdf(snapshot)
                    job_id = self.store.enqueue(source, digest, snapshot, region=region)
                    if self.store.finish_intake(source, signature, 'queued', job_id=job_id):
                        result['accepted_job_ids'].append(job_id)
                except InvalidPDFError as exc:
                    self.store.finish_intake(source, signature, 'rejected', error=str(exc))
                    result['errors'].append({'source': source.name, 'error': str(exc)})
                except (OSError, RuntimeError, ValueError) as exc:
                    if identity is not None:
                        self.store.observe_intake(source, None, now, error=str(exc))
                    result['errors'].append({'source': source.name, 'error': str(exc)})
            self.store.mark_missing_intakes(folder, seen)
        result['intake_counts'] = dict(Counter(record['state'] for record in self.store.intake_files(folder)))
        result['jobs'] = self.store.counts()
        return result
