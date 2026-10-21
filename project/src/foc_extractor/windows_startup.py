"""Current-user Windows startup using the existing single-process launcher."""
from base64 import b64encode
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
import ctypes
from ctypes import wintypes
import hashlib
import io
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
from tempfile import NamedTemporaryFile
import threading
import xml.etree.ElementTree as ET

from .pipeline_config import ROOT
from .process_lock import process_lock


def _identity(config):
    return hashlib.sha256(os.path.normcase(str(config.state_dir)).encode()).hexdigest()[:12]


def task_name(config):
    return 'FOC Invoice Pipeline-' + _identity(config)


def _powershell(script):
    if os.name != 'nt':
        raise RuntimeError('Startup management is available on Windows only')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-EncodedCommand',
        b64encode(("$ErrorActionPreference='Stop';$OutputEncoding=[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"+script).encode('utf-16le')).decode()],
        capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=45,
        creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return json.loads(result.stdout.lstrip('\ufeff'))


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def task_xml(config_path, pythonw, sid, port=8080):
    namespace = 'http://schemas.microsoft.com/windows/2004/02/mit/task'
    ET.register_namespace('', namespace)
    root = ET.Element('Task', {'version':'1.2', 'xmlns':namespace})
    def add(parent, name, text=None):
        child = ET.SubElement(parent, name)
        child.text = text
        return child
    info = add(root, 'RegistrationInfo')
    add(info, 'Description', 'FOC invoice pipeline | ' + str(Path(config_path).resolve()))
    triggers = add(root, 'Triggers')
    trigger = add(triggers, 'LogonTrigger')
    add(trigger, 'Enabled', 'true'); add(trigger, 'UserId', sid); add(trigger, 'Delay', 'PT30S')
    # Native failure restart did not recover an externally killed process on this PC.
    recovery = add(triggers, 'TimeTrigger')
    repetition = add(recovery, 'Repetition')
    add(repetition,'Interval','PT1M'); add(repetition,'StopAtDurationEnd','false')
    add(recovery,'StartBoundary',(datetime.now(timezone.utc)+timedelta(minutes=1)).isoformat(timespec='seconds'))
    add(recovery,'Enabled','true')
    principal = add(add(root, 'Principals'), 'Principal'); principal.set('id','Author')
    add(principal, 'UserId', sid); add(principal, 'LogonType', 'InteractiveToken')
    add(principal, 'RunLevel', 'LeastPrivilege')
    settings = add(root, 'Settings')
    for key,value in [('MultipleInstancesPolicy','IgnoreNew'),('DisallowStartIfOnBatteries','false'),
        ('StopIfGoingOnBatteries','false'),('AllowHardTerminate','true'),('StartWhenAvailable','true'),
        ('RunOnlyIfNetworkAvailable','false'),('AllowStartOnDemand','true'),('Enabled','true'),
        ('Hidden','false'),('ExecutionTimeLimit','PT0S'),('Priority','7')]:
        add(settings,key,value)
    restart = add(settings, 'RestartOnFailure')
    add(restart,'Interval','PT1M'); add(restart,'Count','3')
    actions = add(root,'Actions'); actions.set('Context','Author')
    action = add(actions,'Exec')
    add(action,'Command',str(pythonw))
    add(action,'Arguments',subprocess.list2cmdline([str(ROOT/'run_system.py'),'--config',
        str(Path(config_path).resolve()),'--port',str(port),'--background']))
    add(action,'WorkingDirectory',str(ROOT))
    return ET.tostring(root,encoding='unicode')


def manage_startup(action, config, config_path, port=8080):
    name = task_name(config)
    marker = 'FOC invoice pipeline | '+str(Path(config_path).resolve())
    query = ('try{$task=Get-ScheduledTask -TaskName '+_quote(name)+
        " -ErrorAction Stop}catch{if($_.CategoryInfo.Category -eq 'ObjectNotFound'){$task=$null}else{throw}};")
    owned = ("if(!$task){throw 'Startup task is not installed'};if($task.Description -ne "+_quote(marker)+
        "){throw 'Task belongs to another configuration; no change made'};")
    if action == 'install':
        pythonw = Path(sys.executable).with_name('pythonw.exe')
        if not pythonw.is_file():
            raise RuntimeError('pythonw.exe is missing beside this Python interpreter')
        sid = _powershell('[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value | ConvertTo-Json')
        with NamedTemporaryFile(mode='w',suffix='.xml',encoding='utf-8',delete=False) as handle:
            path = Path(handle.name)
            handle.write(task_xml(config_path,pythonw,sid,port))
        try:
            return _powershell(query+"if($task){throw 'Task already exists; use status or uninstall first'};"
                'Register-ScheduledTask -TaskName '+_quote(name)+' -Xml (Get-Content -Encoding UTF8 -Raw -LiteralPath '+
                _quote(path)+') | Out-Null;@{installed=$true;task_name='+_quote(name)+'} | ConvertTo-Json')
        finally:
            path.unlink(missing_ok=True)
    if action == 'status':
        return _powershell(query+"if(!$task){@{installed=$false} | ConvertTo-Json;exit};"+owned+
            '$info=$task | Get-ScheduledTaskInfo;@{installed=$true;task_name=$task.TaskName;state=[string]$task.State;'
            'enabled=$task.Settings.Enabled;account=$task.Principal.UserId;last_result=$info.LastTaskResult;last_run=[string]$info.LastRunTime;'
            'program=$task.Actions.Execute;arguments=$task.Actions.Arguments;working_directory=$task.Actions.WorkingDirectory;'
            'restart_count=$task.Settings.RestartCount;restart_interval=$task.Settings.RestartInterval;'
            'execution_time_limit=$task.Settings.ExecutionTimeLimit} | ConvertTo-Json')
    if action == 'start':
        return _powershell(query+owned+'$task | Enable-ScheduledTask | Out-Null;$task | Start-ScheduledTask;@{start_requested=$true} | ConvertTo-Json')
    if action == 'stop':
        result = _powershell(query+'if($task){'+owned+'$task | Disable-ScheduledTask | Out-Null};@{automatic_start_disabled=[bool]$task} | ConvertTo-Json')
        return {**result,'stop_requested':request_stop(config),
                'message':'Automatic starts are disabled. An active invoice is allowed to finish before exit. Use start to enable again.'}
    if action == 'uninstall':
        return _powershell(query+owned+"if($task.State -eq 'Running'){throw 'Stop the pipeline and wait for exit before uninstalling'};"
            '$task | Unregister-ScheduledTask -Confirm:$false;@{installed=$false} | ConvertTo-Json')
    raise ValueError('Unknown startup action')


def _kernel():
    if os.name != 'nt':
        raise RuntimeError('Background startup is available on Windows only')
    api = ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateEventW.argtypes = [wintypes.LPVOID,wintypes.BOOL,wintypes.BOOL,wintypes.LPCWSTR]
    api.CreateEventW.restype = wintypes.HANDLE
    api.OpenEventW.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.LPCWSTR]
    api.OpenEventW.restype = wintypes.HANDLE
    for name in ('SetEvent','CloseHandle'):
        getattr(api,name).argtypes = [wintypes.HANDLE]
        getattr(api,name).restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    return api


def _event_name(config):
    return 'Local\\FOCInvoiceStop-' + _identity(config)


def request_stop(config):
    api = _kernel()
    handle = api.OpenEventW(0x0002,False,_event_name(config))
    if not handle:
        error = ctypes.get_last_error()
        if error == 2:
            return False
        raise ctypes.WinError(error)
    try:
        if not api.SetEvent(handle):
            raise ctypes.WinError(ctypes.get_last_error())
        return True
    finally:
        api.CloseHandle(handle)


class _LogStream(io.TextIOBase):
    def __init__(self, logger, level):
        self.logger, self.level = logger, level

    @property
    def encoding(self):
        return 'utf-8'

    def write(self, value):
        if value.strip():
            self.logger.log(self.level,value.rstrip())
        return len(value)

    def flush(self):
        for handler in self.logger.handlers:
            handler.flush()


@contextmanager
def background_runtime(config, stop):
    api = _kernel()
    with process_lock(config.state_dir/'background.lock'):
        log_dir = config.state_dir/'logs'
        log_dir.mkdir(parents=True,exist_ok=True)
        handler = RotatingFileHandler(log_dir/'system.log',maxBytes=5*1024*1024,backupCount=3,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger = logging.getLogger('foc.background')
        logger.setLevel(logging.INFO); logger.propagate = False; logger.addHandler(handler)
        handle = api.CreateEventW(None,True,False,_event_name(config))
        if not handle:
            logger.removeHandler(handler); handler.close()
            raise ctypes.WinError(ctypes.get_last_error())
        def watch():
            while not stop.wait(.2):
                result = api.WaitForSingleObject(handle,0)
                if result == 0:
                    logger.info('Graceful stop requested; waiting for the current invoice to finish.')
                    stop.set()
                elif result == 0xFFFFFFFF:
                    logger.error('Windows stop event failed.')
                    stop.set()
        watcher = threading.Thread(target=watch,name='invoice-stop-control',daemon=True)
        watcher.start()
        try:
            with redirect_stdout(_LogStream(logger,logging.INFO)), redirect_stderr(_LogStream(logger,logging.WARNING)):
                logger.info('Background pipeline starting. PID=%s; input=%s; output=%s',os.getpid(),config.incoming_dir,config.output_dir)
                try:
                    yield
                except BaseException:
                    logger.exception('Background pipeline stopped unexpectedly.')
                    raise
                else:
                    logger.info('Background pipeline stopped normally.')
        finally:
            stop.set(); watcher.join(); api.CloseHandle(handle)
            logger.removeHandler(handler); handler.close()
