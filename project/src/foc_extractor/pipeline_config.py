"""Configuration for the future folder worker; loading it has no side effects."""
from dataclasses import asdict, dataclass, fields
import hashlib
import json
import math
from pathlib import Path
import platform

from . import __version__

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class PipelineConfig:
    incoming_dir: Path
    output_dir: Path
    state_dir: Path
    artifact_dir: Path
    scan_interval_seconds: float
    local_model: str | None

    def to_dict(self):
        return {key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(self).items()}


def load_config(path: Path = ROOT / 'pipeline_config.json') -> PipelineConfig:
    path = Path(path).resolve()
    raw = json.loads(path.read_text(encoding='utf-8'))
    expected = {field.name for field in fields(PipelineConfig)}
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ValueError('Configuration must contain exactly: ' + ', '.join(sorted(expected)))
    directories = {}
    for key in ('incoming_dir', 'output_dir', 'state_dir', 'artifact_dir'):
        value = raw[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{key} must be a nonempty directory path')
        directories[key] = (path.parent / value).resolve()
        if directories[key].exists() and not directories[key].is_dir():
            raise ValueError(f'{key} points to a file')
    paths = list(directories.values())
    for index, first in enumerate(paths):
        for second in paths[index + 1:]:
            if first == second or first in second.parents or second in first.parents:
                raise ValueError('Incoming, output, state and artifact directories must not overlap')
    interval = raw['scan_interval_seconds']
    if type(interval) not in (int, float) or not math.isfinite(interval) or interval <= 0:
        raise ValueError('scan_interval_seconds must be a finite positive number')
    model = raw['local_model']
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError('local_model must be a nonempty model name or null for OCR-only')
    return PipelineConfig(**directories, scan_interval_seconds=interval, local_model=model)


def attempt_metadata(config: PipelineConfig) -> dict:
    """Capture local versions without contacting Ollama or importing OCR models."""
    application = hashlib.sha256()
    for path in sorted((ROOT / 'src/foc_extractor').glob('*.py')) + [ROOT / 'main.py', ROOT / 'run_batch.py']:
        application.update(path.relative_to(ROOT).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
    return {
        'configuration': config.to_dict(),
        'application_version': __version__,
        'application_sha256': application.hexdigest(),
        'python_version': platform.python_version(),
        'template_sha256': hashlib.sha256((ROOT / 'templates/BD_template.xlsx').read_bytes()).hexdigest(),
        'rates_sha256': hashlib.sha256((ROOT / 'valuation_rates.json').read_bytes()).hexdigest(),
        'local_model': config.local_model,
        'model_digest': None,  # Resolved by processing, not assumed from the configured model name.
    }
