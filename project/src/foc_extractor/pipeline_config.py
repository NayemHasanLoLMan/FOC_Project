"""Configuration for the future folder worker; loading it has no side effects."""
from dataclasses import MISSING, asdict, dataclass, fields
import hashlib
import json
import math
from pathlib import Path
import platform
from threading import TIMEOUT_MAX

from . import __version__

ROOT = Path(__file__).resolve().parents[2]
IO_FIELDS = ('incoming_dir', 'output_dir', 'india_incoming_dir', 'india_output_dir')


def initialize_folders(config):
    """Create configured folders, keeping regional inboxes and outputs separate."""
    for folder in (getattr(config, key) for key in IO_FIELDS):
        if folder is None:
            continue
        if folder.name == 'bangladesh':
            for country in ('bangladesh', 'india', 'jordan'):
                (folder.parent/country).mkdir(parents=True, exist_ok=True)
        else:
            folder.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class PipelineConfig:
    incoming_dir: Path
    output_dir: Path
    state_dir: Path
    artifact_dir: Path
    scan_interval_seconds: float
    local_model: str | None
    vision_output_tokens: int = 4096
    vision_context_tokens: int = 8192
    vision_timeout_seconds: int = 7200
    india_enabled: bool = False
    india_incoming_dir: Path | None = None
    india_output_dir: Path | None = None

    def inboxes(self):
        return {'BD': self.incoming_dir, **({'INDIA': self.india_incoming_dir} if self.india_enabled else {})}

    def output_for(self, region):
        # Legacy manually registered regional jobs retain the original single-output behavior.
        return self.india_output_dir if region == 'INDIA' and self.india_output_dir else self.output_dir

    def to_dict(self):
        return {key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(self).items()}


def load_config(path: Path = ROOT / 'pipeline_config.json') -> PipelineConfig:
    path = Path(path).resolve()
    raw = json.loads(path.read_text(encoding='utf-8'))
    return parse_config(raw,path.parent)


def parse_config(raw, base: Path) -> PipelineConfig:
    expected = {field.name for field in fields(PipelineConfig)}
    required = {field.name for field in fields(PipelineConfig) if field.default is MISSING}
    if not isinstance(raw, dict) or not required <= set(raw) or set(raw)-expected:
        raise ValueError('Configuration has missing or unknown fields')
    directories = {}
    for key in (*IO_FIELDS, 'state_dir', 'artifact_dir'):
        value = raw.get(key)
        if key.startswith('india_') and value is None:
            directories[key] = None
            continue
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'{key} must be a nonempty directory path')
        directories[key] = (base / value).resolve()
        if directories[key].exists() and not directories[key].is_dir():
            raise ValueError(f'{key} points to a file')
    enabled = raw.get('india_enabled', False)
    if type(enabled) is not bool:
        raise ValueError('india_enabled must be true or false')
    if bool(directories['india_incoming_dir']) != bool(directories['india_output_dir']):
        raise ValueError('Provide both India input and output folders')
    if enabled and directories['india_incoming_dir'] is None:
        raise ValueError('India processing requires separate input and output folders')
    paths = [path for path in directories.values() if path is not None]
    for index, first in enumerate(paths):
        for second in paths[index + 1:]:
            if first == second or first in second.parents or second in first.parents:
                raise ValueError('Incoming, output, state and artifact directories must not overlap')
    interval = raw['scan_interval_seconds']
    if type(interval) not in (int, float) or not math.isfinite(interval) or not 0 < interval <= TIMEOUT_MAX:
        raise ValueError('scan_interval_seconds must be positive and within the platform timer limit')
    model = raw['local_model']
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ValueError('local_model must be a nonempty model name or null for OCR-only')
    vision={field.name:raw.get(field.name,field.default) for field in fields(PipelineConfig) if field.name.startswith('vision_')}
    for key,value in vision.items():
        if type(value) is not int or not 1 <= value <= 2147483647:
            raise ValueError(f'{key} must be a positive whole number')
    if vision['vision_output_tokens'] > vision['vision_context_tokens']:
        raise ValueError('Vision context must be at least as large as the output token limit')
    return PipelineConfig(**directories, scan_interval_seconds=interval, local_model=model, india_enabled=enabled, **vision)


def attempt_metadata(config: PipelineConfig, region='BD') -> dict:
    """Capture local versions without contacting Ollama or importing OCR models."""
    from .pipeline import _resolve_template
    from .regions import region_code
    region_code(region)
    template = _resolve_template(None, region)
    application = hashlib.sha256()
    for path in sorted((ROOT / 'src/foc_extractor').glob('*.py')) + [ROOT / 'main.py', ROOT / 'run_batch.py']:
        application.update(path.relative_to(ROOT).as_posix().encode() + b'\0' + path.read_bytes() + b'\0')
    return {
        'configuration': config.to_dict(),
        'output_dir': str(config.output_for(region)),
        'application_version': __version__,
        'application_sha256': application.hexdigest(),
        'python_version': platform.python_version(),
        'region': region,
        'template_path': str(template),
        'template_sha256': hashlib.sha256(template.read_bytes()).hexdigest(),
        'rates_sha256': hashlib.sha256((ROOT / 'valuation_rates.json').read_bytes()).hexdigest(),
        'local_model': config.local_model,
        'model_digest': None,  # Resolved by processing, not assumed from the configured model name.
    }
