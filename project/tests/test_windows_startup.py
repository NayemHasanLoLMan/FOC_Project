from base64 import b64decode
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.pipeline_config import load_config
from src.foc_extractor.process_lock import process_lock
from src.foc_extractor.windows_startup import task_xml, task_name, _quote, _powershell, background_runtime, request_stop


class StartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root/'settings & invoice.json'
        self.path.write_bytes((ROOT/'pipeline_config.json').read_bytes())
        self.config = load_config(self.path)

    def test_task_uses_current_user_hidden_python_and_safe_restart_limits(self):
        program = self.root/'Python with spaces'/'pythonw.exe'
        document = ET.fromstring(task_xml(self.path,program,'S-1-5-21-123',8082))
        ns = {'t':'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        def value(path):return document.find(path,ns).text
        self.assertEqual(value('t:Principals/t:Principal/t:LogonType'),'InteractiveToken')
        self.assertEqual(value('t:Principals/t:Principal/t:RunLevel'),'LeastPrivilege')
        self.assertEqual(value('t:Triggers/t:LogonTrigger/t:UserId'),'S-1-5-21-123')
        self.assertEqual(value('t:Settings/t:MultipleInstancesPolicy'),'IgnoreNew')
        self.assertEqual(value('t:Settings/t:ExecutionTimeLimit'),'PT0S')
        self.assertEqual(value('t:Settings/t:RestartOnFailure/t:Interval'),'PT1M')
        self.assertEqual(value('t:Settings/t:RestartOnFailure/t:Count'),'3')
        self.assertEqual(value('t:Actions/t:Exec/t:Command'),str(program))
        self.assertEqual(value('t:Actions/t:Exec/t:WorkingDirectory'),str(ROOT))
        arguments = value('t:Actions/t:Exec/t:Arguments')
        self.assertIn(subprocess.list2cmdline([str(self.path)]),arguments)
        self.assertIn('--background',arguments);self.assertIn('--port 8082',arguments)
        self.assertNotIn('Password',ET.tostring(document,encoding='unicode'))

    def test_identity_is_stable_and_separates_state_directories(self):
        self.assertEqual(task_name(self.config),task_name(load_config(self.path)))
        other = self.root/'other/config.json';other.parent.mkdir();other.write_bytes(self.path.read_bytes())
        self.assertNotEqual(task_name(self.config),task_name(load_config(other)))
        self.assertEqual(_quote("x'; Stop-Computer; '"),"'x''; Stop-Computer; '''")

    @unittest.skipUnless(os.name=='nt','Windows native controls')
    def test_powershell_uses_encoded_arguments_without_a_shell(self):
        response = subprocess.CompletedProcess([],0,'{"ok":true}','')
        with patch('src.foc_extractor.windows_startup.subprocess.run',return_value=response) as call:
            self.assertEqual(_powershell("@{ok=$true}|ConvertTo-Json"),{'ok':True})
        args,kwargs = call.call_args
        self.assertEqual(args[0][0],'powershell.exe');self.assertNotIn('shell',kwargs)
        self.assertIn('ConvertTo-Json',b64decode(args[0][-1]).decode('utf-16le'))
        with patch('src.foc_extractor.windows_startup.subprocess.run',return_value=subprocess.CompletedProcess([],1,'','Denied')):
            with self.assertRaisesRegex(RuntimeError,'Denied'):_powershell('bad')

    @unittest.skipUnless(os.name=='nt','Windows native controls')
    def test_native_stop_event_logs_and_cleanup_allow_restart(self):
        stop = threading.Event()
        self.assertFalse(request_stop(self.config))
        with background_runtime(self.config,stop):
            print('background log sample')
            self.assertTrue(request_stop(self.config))
            self.assertTrue(stop.wait(3))
        self.assertFalse(request_stop(self.config))
        self.assertFalse(any(t.name=='invoice-stop-control' for t in threading.enumerate()))
        text = (self.config.state_dir/'logs/system.log').read_text(encoding='utf-8')
        self.assertIn('background log sample',text);self.assertIn('Graceful stop requested',text)
        self.assertIn('stopped normally',text)
        with background_runtime(self.config,threading.Event()):pass

    @unittest.skipUnless(os.name=='nt','Windows native controls')
    def test_duplicate_background_cannot_open_shared_log(self):
        with process_lock(self.config.state_dir/'background.lock'):
            with self.assertRaisesRegex(RuntimeError,'Another process owns'):
                with background_runtime(self.config,threading.Event()):pass
        self.assertFalse((self.config.state_dir/'logs').exists())

    @unittest.skipUnless(os.name=='nt','Windows native controls')
    def test_background_exception_is_logged_and_propagates(self):
        with self.assertRaisesRegex(RuntimeError,'simulated failure'):
            with background_runtime(self.config,threading.Event()):
                raise RuntimeError('simulated failure')
        text=(self.config.state_dir/'logs/system.log').read_text(encoding='utf-8')
        self.assertIn('simulated failure',text);self.assertIn('stopped unexpectedly',text)
        self.assertFalse(request_stop(self.config))

    @unittest.skipUnless(os.name=='nt','Windows native controls')
    def test_logs_rotate_without_growing_without_limit(self):
        with background_runtime(self.config,threading.Event()):
            handler=logging.getLogger('foc.background').handlers[0]
            self.assertEqual(handler.maxBytes,5*1024*1024);self.assertEqual(handler.backupCount,3)
            handler.maxBytes=100
            for _ in range(20):print('log rotation sample '*10)
        files=list((self.config.state_dir/'logs').glob('system.log*'))
        self.assertEqual(len(files),4)


if __name__=='__main__':unittest.main()
