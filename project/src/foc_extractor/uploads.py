"""Validate uploaded PDFs and publish complete files to the existing inbox."""
from pathlib import Path, PureWindowsPath
from tempfile import NamedTemporaryFile

from werkzeug.exceptions import RequestEntityTooLarge

from .folder_intake import _validate_pdf, _digest

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


def save_pdf(upload, folder):
    name = upload.filename or ''
    if (not name or len(name) > 200 or name != PureWindowsPath(name).name
            or PureWindowsPath(name).is_reserved() or name.endswith((' ', '.'))
            or any(c in '<>:"/\\|?*' or ord(c) < 32 for c in name)
            or Path(name).suffix.lower() != '.pdf'):
        raise ValueError('Choose a PDF with a valid filename of up to 200 characters.')
    folder = Path(folder)
    if folder.resolve() != folder or folder.is_symlink():
        raise OSError('The incoming folder no longer matches its configured location')
    folder.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=folder, suffix='.upload', delete=False) as handle:
            temporary = Path(handle.name)
            upload.save(handle)
        if temporary.stat().st_size > MAX_UPLOAD_BYTES:
            raise RequestEntityTooLarge('The PDF must be 100 MB or smaller.')
        _validate_pdf(temporary, pdf_bytes=temporary.read_bytes())
        from .queue_worker import _publish_copy
        _publish_copy(temporary, folder/name, _digest(temporary))
        return name
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
