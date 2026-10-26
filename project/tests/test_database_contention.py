from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.foc_extractor.job_store import JobStore, _retry_busy, _ReadConnection
from src.foc_extractor.dashboard import create_app
from src.foc_extractor.pipeline_config import load_config


def busy(code=sqlite3.SQLITE_BUSY):
    error=sqlite3.OperationalError('controlled contention')
    error.sqlite_errorcode=code
    return error


class DatabaseContentionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.store=JobStore(Path(self.directory.name)/'jobs.sqlite3')
        with closing(sqlite3.connect(self.store.path)) as db:db.execute('PRAGMA journal_mode=DELETE')

    def test_only_busy_and_locked_are_retried_with_a_fixed_limit(self):
        for code in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED,sqlite3.SQLITE_BUSY | (1<<8)):
            action=Mock(side_effect=[busy(code),busy(code),'committed'])
            with patch('src.foc_extractor.job_store.time.sleep') as sleep:
                self.assertEqual(_retry_busy(action),'committed')
            self.assertEqual(action.call_count,3)
            self.assertEqual([call.args[0] for call in sleep.call_args_list],[.1,.2])
        for error in (busy(sqlite3.SQLITE_IOERR),sqlite3.OperationalError('not a coded busy error'),ValueError('invalid')):
            action=Mock(side_effect=error)
            with patch('src.foc_extractor.job_store.time.sleep') as sleep,self.assertRaises(type(error)):
                _retry_busy(action)
            self.assertEqual(action.call_count,1)
            sleep.assert_not_called()
        action=Mock(side_effect=busy())
        with patch('src.foc_extractor.job_store.time.sleep'),self.assertRaises(sqlite3.OperationalError):_retry_busy(action)
        self.assertEqual(action.call_count,3)

    def test_body_failure_is_rolled_back_without_replaying_writes(self):
        bodies=0
        with patch('src.foc_extractor.job_store.time.sleep') as sleep:
            with self.assertRaises(sqlite3.OperationalError),self.store._connection(write=True) as db:
                bodies+=1
                db.execute('UPDATE queue_control SET paused=1')
                raise busy()
            sleep.assert_not_called()
        self.assertEqual(bodies,1)
        self.assertFalse(self.store.queue_control()['paused'])

    def test_exhausted_commit_rolls_back_and_releases_the_connection(self):
        retry=_retry_busy
        def fail_commit(action):
            if getattr(action,'__name__','')=='commit':raise busy()
            return retry(action)
        with patch('src.foc_extractor.job_store._retry_busy',side_effect=fail_commit):
            with self.assertRaises(sqlite3.OperationalError),self.store._connection(write=True) as db:
                db.execute('UPDATE queue_control SET paused=1')
        self.assertFalse(self.store.queue_control()['paused'])
        with self.store._connection(write=True) as db:db.execute('UPDATE queue_control SET paused=1')
        self.assertTrue(self.store.queue_control()['paused'])

    def hold_lock(self,sql,ready):
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute('BEGIN');db.execute(sql).fetchall()
            ready.set();time.sleep(6.5)

    def test_real_writer_longer_than_original_timeout_recovers_once(self):
        ready=threading.Event()
        thread=threading.Thread(target=self.hold_lock,args=('UPDATE queue_control SET paused=paused',ready))
        thread.start();self.addCleanup(thread.join)
        self.assertTrue(ready.wait(5))
        with self.store._connection(write=True) as db:db.execute('UPDATE queue_control SET paused=1')
        thread.join()
        self.assertTrue(self.store.queue_control()['paused'])

    def test_real_reader_blocks_commit_but_transaction_body_runs_once(self):
        ready=threading.Event()
        thread=threading.Thread(target=self.hold_lock,args=('SELECT * FROM queue_control',ready))
        thread.start();self.addCleanup(thread.join)
        self.assertTrue(ready.wait(5));bodies=0
        with self.store._connection(write=True) as db:
            bodies+=1
            db.execute('UPDATE queue_control SET paused=1')
        thread.join()
        self.assertEqual(bodies,1)
        self.assertTrue(self.store.queue_control()['paused'])

    def test_worker_and_dashboard_reads_recover_during_concurrent_writer_contention(self):
        path=Path(self.directory.name)/'config.json'
        path.write_text((Path(__file__).resolve().parents[1]/'pipeline_config.json').read_text())
        config=replace(load_config(path),state_dir=self.store.path.parent)
        app=create_app(config)
        ready=threading.Event()
        def hold():
            with closing(sqlite3.connect(self.store.path)) as db:
                db.execute('BEGIN EXCLUSIVE');ready.set();time.sleep(12.5)
        def request(route):
            with app.test_client() as client:return client.get(route).status_code
        thread=threading.Thread(target=hold);thread.start();self.addCleanup(thread.join)
        self.assertTrue(ready.wait(5))
        with ThreadPoolExecutor(max_workers=5) as pool:
            readers=[pool.submit(self.store.unfinished_attempts),pool.submit(self.store.components)]
            pages=[pool.submit(request,route) for route in ('/api/status','/jobs')]
            writer=pool.submit(self.store.component,'scanner','test-owner',123,'running')
            self.assertEqual(readers[0].result(),[])
            self.assertIsInstance(readers[1].result(),list)
            self.assertEqual([future.result() for future in pages],[200,200])
            writer.result()
        self.assertEqual(self.store.components()[0]['owner'],'test-owner')

    def test_read_retry_limit_and_release_without_replaying_the_caller(self):
        for persistent in (False,True):
            with self.subTest(persistent=persistent),closing(sqlite3.connect(
                    self.store.path,timeout=.01,factory=_ReadConnection)) as reader:
                reader.execute('SELECT * FROM queue_control').fetchall()
                ready=threading.Event();release=threading.Event()
                def hold():
                    with closing(sqlite3.connect(self.store.path)) as db:
                        db.execute('BEGIN EXCLUSIVE');ready.set();release.wait(10)
                thread=threading.Thread(target=hold);thread.start()
                self.assertTrue(ready.wait(5))
                def recover(_):
                    if not persistent:release.set();thread.join()
                try:
                    with patch('src.foc_extractor.job_store.time.sleep',side_effect=recover) as sleep:
                        if persistent:
                            with self.assertRaises(sqlite3.OperationalError):reader.execute('SELECT * FROM queue_control')
                            self.assertEqual(sleep.call_count,2)
                        else:
                            self.assertEqual(reader.execute('SELECT paused FROM queue_control').fetchone()[0],0)
                            self.assertEqual(sleep.call_count,1)
                finally:release.set();thread.join()
                self.assertEqual(reader.execute('SELECT paused FROM queue_control').fetchone()[0],0)

    def test_new_reader_recovers_while_a_writer_waits_to_commit(self):
        ready=threading.Event();written=threading.Event()
        reader=threading.Thread(target=self.hold_lock,args=('SELECT * FROM queue_control',ready))
        reader.start();self.addCleanup(reader.join);self.assertTrue(ready.wait(5))
        def write():
            with self.store._connection(write=True) as db:
                db.execute('UPDATE queue_control SET paused=1');written.set()
        with ThreadPoolExecutor(max_workers=1) as pool:
            writer=pool.submit(write);self.assertTrue(written.wait(5))
            time.sleep(.1)
            self.assertEqual(self.store.components(),[])
            writer.result()
        self.assertTrue(self.store.queue_control()['paused'])

    def test_only_read_scopes_use_statement_retry_and_other_errors_still_escape(self):
        with self.store._connection() as reader:
            self.assertIsInstance(reader,_ReadConnection)
            with patch('src.foc_extractor.job_store.time.sleep') as sleep:
                with self.assertRaises(sqlite3.OperationalError):reader.execute('SELECT * FROM missing_table')
                sleep.assert_not_called()
        with self.store._connection(write=True) as writer:
            self.assertNotIsInstance(writer,_ReadConnection)


if __name__=='__main__':unittest.main()
