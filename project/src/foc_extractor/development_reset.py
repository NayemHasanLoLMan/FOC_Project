"""Recoverable clearing of the main or isolated development workspace."""
from contextlib import ExitStack, closing
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from .pipeline_config import ROOT

DEVELOPMENT_ROOT=ROOT/'development/runtime'


def development_config(config):
    base=DEVELOPMENT_ROOT
    return replace(config,incoming_dir=base/'incoming/bangladesh',output_dir=base/'output/bangladesh',
                   india_incoming_dir=base/'incoming/india' if config.india_incoming_dir else None,
                   india_output_dir=base/'output/india' if config.india_output_dir else None,
                   state_dir=base/'state',artifact_dir=base/'artifacts')


def validate_development(config):
    base=DEVELOPMENT_ROOT
    if base.resolve()!=base or any(getattr(config,key).resolve()!=getattr(development_config(config),key)
        for key in ('state_dir','artifact_dir')):
        raise ValueError('Development clearing is restricted to the isolated development workspace')
    from .runtime_settings import validate_setting_paths
    validate_setting_paths(config,development=True)


def clear_development(config,store,locks,request_id):
    validate_development(config)
    return clear_workspace(config,store,locks,request_id,development=True)


def validate_workspace(config, *, development=False):
    if development:
        validate_development(config)
        return
    expected={'state_dir':ROOT/'runtime/state','artifact_dir':ROOT/'runtime/artifacts'}
    if ROOT.resolve()!=ROOT or any(getattr(config,key)!=path or path.resolve()!=path for key,path in expected.items()):
        raise ValueError('Clear data requires the standard main workspace folders or the isolated development workspace')
    from .runtime_settings import validate_setting_paths
    validate_setting_paths(config)


def clear_workspace(config,store,locks,request_id, *, development=False):
    validate_workspace(config,development=development)
    base=DEVELOPMENT_ROOT if development else ROOT
    archive_root=base/'cleared' if development else base/'runtime/cleared'
    with ExitStack() as stack:
        for lock in locks:
            if not lock.acquire(blocking=False):raise ValueError('A scan or invoice is active. Wait for it to finish and try again.')
            stack.callback(lock.release)
        moved=[];archive=None
        try:
            with store._connection(write=True) as db:
                old=db.execute('SELECT action,result_json FROM admin_commands WHERE request_id=?',(request_id,)).fetchone()
                if old:
                    if old['action']!='development_reset':raise ValueError('This request ID already belongs to another command')
                    return json.loads(old['result_json'])
                if db.execute("SELECT 1 FROM attempts WHERE state='running'").fetchone():
                    raise ValueError('An invoice is still running')
                count=db.execute('SELECT count(*) FROM jobs').fetchone()[0]
                archive=archive_root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+request_id)
                if archive.resolve()!=archive or not archive.resolve().is_relative_to(base):
                    raise ValueError('The recovery archive escapes the workspace')
                if archive.exists():raise ValueError('A previous reset archive exists; inspect it before retrying with a new request')
                generated=[(config.artifact_dir,'artifacts'),(config.output_dir,'output')]
                if config.india_output_dir:generated.append((config.india_output_dir,'output-india'))
                for folder,_ in generated:
                    for path in [folder,*folder.rglob('*')]:
                        if path.is_symlink() or path.resolve()!=path or not path.resolve().is_relative_to(folder):
                            raise ValueError('Generated files contain a link or escape their workspace')
                archive.mkdir(parents=True)
                with store._connection() as source, closing(sqlite3.connect(archive/'jobs.sqlite3')) as backup:
                    source.backup(backup)
                for folder,name in generated:
                    if folder.exists():
                        target=archive/name
                        if folder.stat().st_dev!=archive.stat().st_dev:
                            # Keep the recovery move atomic on the output drive rather than copying/deleting across volumes.
                            target=folder.parent/'.foc-cleared'/archive.name/name
                            if target.resolve()!=target or not target.is_relative_to(folder.parent) or target.exists():
                                raise ValueError('The output recovery folder is redirected or already exists')
                            target.parent.mkdir(parents=True,exist_ok=True)
                            (archive/('external-output-india.json' if name=='output-india' else 'external-output.json')).write_text(json.dumps({'original':str(folder),'archived':str(target)}),encoding='utf-8')
                        folder.rename(target);moved.append((folder,target))
                    folder.mkdir(parents=True,exist_ok=True)
                # Rediscover remaining PDFs through the normal stable-file checks after clearing.
                db.execute('DELETE FROM intake_files')
                db.execute('UPDATE admin_commands SET job_id=NULL,attempt_id=NULL')
                for table in ('events','attempts','jobs'):db.execute('DELETE FROM '+table)
                db.execute('UPDATE queue_control SET paused=0,updated_at=? WHERE id=1',
                           (datetime.now(timezone.utc).isoformat(),))
                result={'request_id':request_id,'action':'development_reset','cleared_jobs':count,
                        'archive':str(archive.relative_to(base))}
                db.execute('INSERT INTO admin_commands VALUES(?,?,NULL,NULL,?,?)',
                    (request_id,'development_reset',datetime.now(timezone.utc).isoformat(),json.dumps(result)))
            return result
        except BaseException:
            for original,target in reversed(moved):
                if original.exists():original.rmdir()
                target.rename(original)
            raise
        # shortcut: after an OS crash mid-reset, restore the matching database and generated folders from the recovery archive.
