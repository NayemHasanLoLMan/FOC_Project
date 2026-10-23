"""Persist user settings and apply them while scanner and worker are idle."""
from contextlib import ExitStack
import json
from pathlib import Path
from datetime import datetime, timezone

from .pipeline_config import ROOT, IO_FIELDS, parse_config

LEGACY_SETTINGS_FIELDS=('local_model','scan_interval_seconds','vision_output_tokens','vision_context_tokens',
                 'vision_timeout_seconds','incoming_dir','output_dir')
SETTINGS_FIELDS=(*LEGACY_SETTINGS_FIELDS,'india_enabled','india_incoming_dir','india_output_dir')


def editable_settings(config):
    values=config.to_dict()
    return {key:values[key] for key in SETTINGS_FIELDS}


def validate_setting_paths(config, *, development=False):
    protected=[config.state_dir,config.artifact_dir,*[ROOT/name for name in
        ('src','frontend','templates','.cache','.venv','docs','tools','tests','reports','development','examples','expected_output','expected_outputs')]]
    for folder in (getattr(config,key) for key in IO_FIELDS):
        if folder is None:continue
        if development:
            from .development_reset import DEVELOPMENT_ROOT
            if folder==DEVELOPMENT_ROOT or not folder.is_relative_to(DEVELOPMENT_ROOT):
                raise ValueError('Development folders must stay inside the isolated development workspace')
        for parent in folder.parents:
            if parent.is_symlink() or parent.resolve()!=parent:
                raise ValueError('Folders must not pass through redirected paths')
        if folder.is_symlink() or folder.resolve()!=folder or folder==Path(folder.anchor) or folder==Path.home() or ROOT.is_relative_to(folder):
            raise ValueError('Choose a dedicated input/output folder, not a drive, home or project root')
        for path in protected:
            if development and path==ROOT/'development':continue
            if folder==path or folder.is_relative_to(path) or path.is_relative_to(folder):
                raise ValueError('Input/output folders must not overlap application, cache, reference or state folders')
    folders=[getattr(config,key) for key in IO_FIELDS if getattr(config,key) is not None]
    for index,first in enumerate(folders):
        for second in folders[index+1:]:
            if first==second or first.is_relative_to(second) or second.is_relative_to(first):
                raise ValueError('Regional input and output folders must not overlap')


def settings_config(config,changes, *, development=False):
    if not isinstance(changes,dict) or set(changes) not in (set(SETTINGS_FIELDS),set(LEGACY_SETTINGS_FIELDS)):
        raise ValueError('Submit all settings fields (legacy seven-field requests are also supported)')
    for key in IO_FIELDS:
        if key not in changes or (key.startswith('india_') and changes[key] is None):continue
        if not isinstance(changes[key],str) or not Path(changes[key]).is_absolute():
            raise ValueError('Use a full absolute path for the input and output folders')
        requested=Path(changes[key])
        if any(path.is_symlink() or path.is_junction() for path in (requested,*requested.parents)):
            raise ValueError('Folders must not pass through redirected paths')
    model=changes['local_model']
    if isinstance(model,str) and (len(model)>200 or model.strip()!=model or any(ord(char)<32 for char in model)):
        raise ValueError('Use a valid installed model name, or leave it blank for OCR only')
    updated=parse_config({**config.to_dict(),**changes},ROOT)
    validate_setting_paths(updated,development=development)
    return updated


def load_runtime_settings(config, *, development=False):
    path=config.state_dir/'settings.json'
    if not path.exists():return config
    return settings_config(config,json.loads(path.read_text(encoding='utf-8')),development=development)


def save_runtime_settings(config,store,locks,request_id,changes,apply, *, development=False):
    from .queue_worker import _write_json
    with ExitStack() as stack:
        for lock in locks:
            if not lock.acquire(blocking=False):raise ValueError('A scan or invoice is active. Wait for it to finish, or pause processing, then save again.')
            stack.callback(lock.release)
        path=config.state_dir/'settings.json'
        previous=path.read_bytes() if path.exists() else None
        written=False
        try:
            with store._connection(write=True) as db:
                old=db.execute('SELECT action,result_json FROM admin_commands WHERE request_id=?',(request_id,)).fetchone()
                if old:
                    if old['action']!='settings':raise ValueError('This request ID already belongs to another command')
                    return json.loads(old['result_json'])
                if db.execute("SELECT 1 FROM attempts WHERE state='running'").fetchone():
                    raise ValueError('An invoice is running. Wait for it to finish before changing settings.')
                updated=settings_config(config,changes,development=development)
                if config.india_output_dir and updated.india_output_dir is None and db.execute("SELECT 1 FROM jobs WHERE region='INDIA'").fetchone():
                    raise ValueError('Keep India folders while India history exists; disable new India intake instead')
                for region,folder in updated.inboxes().items():
                    for row in db.execute('SELECT source_path,region FROM jobs WHERE region<>?',(region,)):
                        if Path(row['source_path']).parent==folder:
                            raise ValueError('An input folder with existing jobs cannot be reassigned to another country')
                for folder in (getattr(updated,key) for key in IO_FIELDS):
                    if folder is None:continue
                    folder.mkdir(parents=True,exist_ok=True)
                    # Check actual write access without touching existing user files.
                    from tempfile import TemporaryFile
                    with TemporaryFile(dir=folder):pass
                result={'request_id':request_id,'action':'settings','settings':editable_settings(updated)}
                _write_json(path,result['settings']);written=True
                db.execute('INSERT INTO admin_commands VALUES(?,?,NULL,NULL,?,?)',
                    (request_id,'settings',datetime.now(timezone.utc).isoformat(),json.dumps(result)))
        except BaseException:
            if written:
                if previous is None:path.unlink()
                else:
                    temporary=path.with_suffix('.json.tmp');temporary.write_bytes(previous);temporary.replace(path)
            raise
        apply(updated)
        return result
