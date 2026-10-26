from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.foc_extractor.dashboard import create_app
from src.foc_extractor.job_store import JobStore
from src.foc_extractor.pipeline_config import load_config


class WalDatabaseTests(unittest.TestCase):
    def test_dashboard_and_worker_reads_do_not_wait_for_a_writer_or_see_uncommitted_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);path=root/'config.json';path.write_text((ROOT/'pipeline_config.json').read_text())
            config=load_config(path);store=JobStore(config.state_dir/'jobs.sqlite3');app=create_app(config)
            with store._connection() as db:
                self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'wal')
                self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0],2)
            ready=threading.Event();release=threading.Event()
            def write():
                with store._connection(write=True) as db:
                    db.execute('UPDATE queue_control SET paused=1');ready.set()
                    if not release.wait(10):raise TimeoutError('Test reader did not complete')
            def read():
                with app.test_client() as client:
                    status=client.get('/api/status');jobs=client.get('/jobs')
                return store.unfinished_attempts(),status.status_code,status.json['queue']['paused'],jobs.status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                writer=pool.submit(write);self.assertTrue(ready.wait(5))
                try:self.assertEqual(pool.submit(read).result(timeout=3),([],200,False,200))
                finally:release.set()
                writer.result()
            self.assertTrue(store.queue_control()['paused'])

    def test_backup_api_captures_committed_wal_data_and_reopening_preserves_it(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'jobs.sqlite3';store=JobStore(path)
            with closing(sqlite3.connect(path)) as anchor:
                anchor.execute('SELECT * FROM queue_control').fetchall()
                with store._connection(write=True) as db:db.execute('UPDATE queue_control SET paused=1')
                self.assertTrue(Path(str(path)+'-wal').exists())
                backup=Path(folder)/'backup.sqlite3'
                with store._connection() as source,closing(sqlite3.connect(backup)) as target:source.backup(target)
                self.assertTrue(JobStore(backup,read_only=True).queue_control()['paused'])
            self.assertTrue(JobStore(path).queue_control()['paused'])

    def test_unrelated_database_is_rejected_without_changing_its_journal_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'unrelated.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE unrelated(value)');db.commit()
            with self.assertRaises(ValueError):JobStore(path)
            with closing(sqlite3.connect(path)) as db:self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'delete')

    def test_unsafe_sqlite_runtime_is_rejected_before_creating_state(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'jobs.sqlite3'
            with patch('src.foc_extractor.job_store.sqlite3.sqlite_version_info',(3,51,2)):
                with self.assertRaisesRegex(RuntimeError,'SQLite 3.51.3'):JobStore(path)
            self.assertFalse(path.exists())


if __name__=='__main__':unittest.main()
