from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.foc_extractor.folder_intake import FolderScanner, _digest
from src.foc_extractor.job_store import APPLICATION_ID, SCHEMA, SCHEMA_VERSION, JobStore
from src.foc_extractor.pipeline_config import load_config


def pdf_bytes(text='ONE'):
    with pymupdf.open() as document:
        document.new_page().insert_text((40, 40), text)
        return document.tobytes()


class IntakeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()
        self.config_path = self.root / 'pipeline_config.json'
        self.config_path.write_bytes((ROOT / 'pipeline_config.json').read_bytes())
        self.config = load_config(self.config_path)
        self.config.incoming_dir.mkdir()
        self.store = JobStore(self.config.state_dir / 'jobs.sqlite3')
        self.scanner = FolderScanner(self.config, self.store)

    def source(self, name='shipment.pdf', data=None):
        path = self.config.incoming_dir / name
        path.write_bytes(pdf_bytes() if data is None else data)
        return path

    def scan(self, when, scanner=None):
        with patch('src.foc_extractor.folder_intake.time.time', return_value=when):
            return (scanner or self.scanner).scan_once()

    def test_requires_two_unchanged_observations_and_preserves_snapshot_and_source(self):
        source = self.source()
        original = source.read_bytes()
        self.assertEqual(self.scan(0)['accepted_job_ids'], [])
        self.assertEqual(self.scan(4)['jobs']['queued'], 0)
        result = self.scan(5)
        self.assertEqual(result['jobs']['queued'], 1)
        job = self.store.get_job(result['accepted_job_ids'][0])
        snapshot = Path(job['snapshot_path'])
        self.assertEqual(snapshot.name, source.name)
        self.assertEqual(snapshot.read_bytes(), original)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual(job['source_sha256'], hashlib.sha256(original).hexdigest())
        self.assertFalse(self.config.output_dir.exists())
        self.assertEqual(self.scan(10)['accepted_job_ids'], [])
        self.assertEqual(len(self.store.events(job['id'])), 1)

    def test_slow_and_invalid_copies_wait_for_new_stable_valid_bytes(self):
        source = self.source(data=b'%PDF-1.7\npartial')
        self.scan(0)
        self.assertEqual(self.scan(5)['intake_counts']['rejected'], 1)
        self.assertEqual(self.store.counts()['queued'], 0)
        source.write_bytes(b'%PDF-1.7\nstill copying more bytes')
        self.assertEqual(self.scan(10)['intake_counts']['waiting_for_file'], 1)
        source.write_bytes(pdf_bytes('COMPLETE'))
        self.assertEqual(self.scan(15)['jobs']['queued'], 0)
        self.assertEqual(self.scan(20)['jobs']['queued'], 1)

    def test_readiness_and_deduplication_survive_process_restart(self):
        self.source()
        self.scan(0)
        command = [sys.executable, str(ROOT / 'scan_incoming.py'), '--config', str(self.config_path), '--once']
        first = subprocess.run(command, capture_output=True, text=True, check=True, cwd=self.root)
        result = json.loads(first.stdout)
        self.assertEqual(result['jobs']['queued'], 1)
        second = subprocess.run(command, capture_output=True, text=True, check=True, cwd=self.root)
        self.assertEqual(json.loads(second.stdout)['accepted_job_ids'], [])
        self.assertEqual(self.store.counts()['queued'], 1)
        self.assertFalse(self.config.output_dir.exists())

    def test_changed_bytes_with_same_name_and_size_preserve_previous_version(self):
        source = self.source()
        self.scan(0)
        first = self.store.get_job(self.scan(5)['accepted_job_ids'][0])
        original = source.read_bytes()
        timestamp = source.stat().st_mtime_ns
        replacement = pdf_bytes('TWO')
        self.assertEqual(len(replacement), len(original))
        source.write_bytes(replacement)
        os.utime(source, ns=(timestamp, timestamp))
        self.assertEqual(self.scan(10)['accepted_job_ids'], [])
        second = self.store.get_job(self.scan(15)['accepted_job_ids'][0])
        self.assertNotEqual(first['id'], second['id'])
        self.assertEqual(Path(first['snapshot_path']).read_bytes(), original)
        self.assertEqual(Path(second['snapshot_path']).read_bytes(), replacement)
        self.assertEqual(Path(first['snapshot_path']).name, Path(second['snapshot_path']).name)

    def test_rename_records_same_content_relationship_and_does_not_alias_filenames(self):
        source = self.source()
        self.scan(0)
        first = self.scan(5)['accepted_job_ids'][0]
        source.rename(source.with_name('renamed.PDF'))
        self.scan(10)
        second = self.scan(15)['accepted_job_ids'][0]
        self.assertNotEqual(first, second)
        self.assertEqual(self.store.events(second)[0]['details']['same_content_job_ids'], [first])
        self.assertEqual(Path(self.store.get_job(second)['snapshot_path']).name, 'renamed.PDF')
        self.assertEqual(self.scan(20)['jobs']['queued'], 2)

    def test_temporary_files_subfolders_and_non_pdfs_are_ignored(self):
        for name in ['.hidden.pdf', '~$owner.pdf', 'copy.part.pdf', 'copy.tmp.pdf',
                     'copy.partial.pdf', 'copy.crdownload.pdf', 'file.pdf.tmp', 'note.txt']:
            self.source(name)
        nested = self.config.incoming_dir / 'subfolder'
        nested.mkdir()
        (nested / 'nested.pdf').write_bytes(pdf_bytes())
        self.source('READY.PDF')
        self.scan(0)
        result = self.scan(5)
        self.assertEqual(result['jobs']['queued'], 1)
        self.assertEqual(len(self.store.intake_files(self.config.incoming_dir)), 1)

    def test_atomic_final_rename_is_discovered_after_readiness_checks(self):
        partial = self.source('arrival.pdf.part')
        self.assertEqual(self.scan(0)['intake_counts'], {})
        partial.rename(partial.with_name('arrival.pdf'))
        self.assertEqual(self.scan(5)['jobs']['queued'], 0)
        self.assertEqual(self.scan(10)['jobs']['queued'], 1)

    def test_link_or_inaccessible_entry_does_not_stop_other_files(self):
        linked = self.source('linked.pdf')
        self.source('good.pdf')
        original = Path.is_symlink
        def is_link(path):
            return path == linked or original(path)
        with patch.object(Path, 'is_symlink', is_link):
            self.scan(0)
            result = self.scan(5)
        self.assertEqual(result['jobs']['queued'], 1)
        self.assertEqual(len(self.store.intake_files(self.config.incoming_dir)), 1)
        def inaccessible(path):
            if path == linked:
                raise PermissionError('Entry metadata is unavailable')
            return original(path)
        with patch.object(Path, 'is_symlink', inaccessible):
            self.assertTrue(self.scan(10)['errors'])

    def test_password_and_repair_required_pdfs_are_rejected_without_blocking_good_files(self):
        protected = self.config.incoming_dir / 'protected.pdf'
        with pymupdf.open(stream=pdf_bytes(), filetype='pdf') as document:
            document.save(protected, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='secret')
        self.source('broken.pdf', pdf_bytes().replace(b'startxref', b'badxxxxxx'))
        self.source('incomplete.pdf', pdf_bytes().split(b'%%EOF')[0])
        self.source('empty.pdf', b'')
        self.source('good.pdf')
        self.scan(0)
        result = self.scan(5)
        self.assertEqual(result['intake_counts']['rejected'], 4)
        self.assertEqual(result['jobs']['queued'], 1)
        self.assertTrue(any('password' in (row['error'] or '') for row in self.store.intake_files(self.config.incoming_dir)))
        self.assertEqual(self.scan(10)['errors'], [])

    def test_unavailable_folder_and_disappeared_source_preserve_queued_snapshots(self):
        self.config.incoming_dir.rmdir()
        self.assertIsNotNone(self.scan(0)['folder_error'])
        self.config.incoming_dir.mkdir()
        source = self.source()
        data = source.read_bytes()
        self.scan(5)
        job = self.store.get_job(self.scan(10)['accepted_job_ids'][0])
        source.unlink()
        self.assertEqual(self.scan(15)['intake_counts']['missing'], 1)
        self.assertTrue(Path(job['snapshot_path']).is_file())
        self.source(data=data)
        self.scan(20)
        self.assertEqual(self.scan(25)['jobs']['queued'], 1)
        self.assertEqual(len(self.store.events(job['id'])), 1)

    def test_unreadable_file_is_recorded_and_other_files_continue(self):
        bad = self.source('locked.pdf')
        self.source('good.pdf')
        def read(path):
            if path == bad:
                raise PermissionError('File is still locked by producer')
            return _digest(path)
        with patch('src.foc_extractor.folder_intake._digest', side_effect=read):
            self.scan(0)
            result = self.scan(5)
        self.assertEqual(result['jobs']['queued'], 1)
        self.assertEqual(result['intake_counts']['waiting_for_file'], 1)
        self.scan(10)
        self.assertEqual(self.scan(15)['jobs']['queued'], 2)

    def test_source_change_during_snapshot_does_not_queue_mixed_bytes(self):
        source = self.source()
        self.scan(0)
        import shutil
        copy = shutil.copyfile
        replacement = pdf_bytes('REPLACED')
        def copy_then_change(src, target):
            copy(src, target)
            source.write_bytes(replacement)
        with patch('src.foc_extractor.folder_intake.shutil.copyfile', side_effect=copy_then_change):
            self.assertEqual(self.scan(5)['jobs']['queued'], 0)
        self.assertEqual(list(self.config.artifact_dir.rglob('*.tmp')), [])
        self.scan(10)
        job = self.store.get_job(self.scan(15)['accepted_job_ids'][0])
        self.assertEqual(Path(job['snapshot_path']).read_bytes(), replacement)

    def test_snapshot_survives_queue_failure_and_is_reused_without_overwriting(self):
        self.source()
        self.scan(0)
        with patch.object(self.store, 'enqueue', side_effect=sqlite3.OperationalError('simulated crash')):
            with self.assertRaises(sqlite3.OperationalError):
                self.scan(5)
        snapshot = next(self.config.artifact_dir.rglob('*.pdf'))
        before = snapshot.stat().st_mtime_ns
        replacement_scanner = FolderScanner(self.config, JobStore(self.store.path))
        self.assertEqual(self.scan(10, replacement_scanner)['jobs']['queued'], 1)
        self.assertEqual(snapshot.stat().st_mtime_ns, before)

    def test_corrupted_existing_snapshot_is_not_overwritten(self):
        self.source()
        self.scan(0)
        with patch.object(self.store, 'enqueue', side_effect=sqlite3.OperationalError('simulated crash')):
            with self.assertRaises(sqlite3.OperationalError):
                self.scan(5)
        snapshot = next(self.config.artifact_dir.rglob('*.pdf'))
        snapshot.write_bytes(b'damaged saved snapshot')
        result = self.scan(10)
        self.assertEqual(result['jobs']['queued'], 0)
        self.assertIn('refusing to overwrite', result['errors'][0]['error'])
        self.assertEqual(snapshot.read_bytes(), b'damaged saved snapshot')

    def test_two_scanners_do_not_create_duplicate_jobs(self):
        self.source()
        self.scan(0)
        scanners = [FolderScanner(self.config, JobStore(self.store.path)) for _ in range(2)]
        with patch('src.foc_extractor.folder_intake.time.time', return_value=5):
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(lambda scanner: scanner.scan_once(), scanners))
        self.assertEqual(self.store.counts()['queued'], 1)
        self.scan(10)
        self.scan(15)
        self.assertEqual(self.store.counts()['queued'], 1)

    def test_continuous_command_detects_arrival_and_stops_without_processing(self):
        ticks = [0, 5, 10]
        sleeps = 0
        def sleep(interval):
            nonlocal sleeps
            self.assertEqual(interval, self.config.scan_interval_seconds)
            sleeps += 1
            if sleeps == 1:
                self.source()
            if sleeps == 3:
                raise KeyboardInterrupt
        output = io.StringIO()
        with patch.object(sys, 'argv', ['scan_incoming.py', '--config', str(self.config_path)]), redirect_stdout(output):
            with patch('time.time', side_effect=ticks), patch('time.sleep', side_effect=sleep):
                runpy.run_path(str(ROOT / 'scan_incoming.py'), run_name='__main__')
        records = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(records[-2]['jobs']['queued'], 1)
        self.assertEqual(records[-1], {'scanner_stopped': True, 'extraction_started': False})
        self.assertFalse(self.config.output_dir.exists())

    def test_version_one_database_migration_preserves_jobs_attempts_and_events(self):
        database = self.root / 'legacy.sqlite3'
        with closing(sqlite3.connect(database)) as db, db:
            for statement in SCHEMA:
                db.execute(statement)
            db.execute(f'PRAGMA application_id={APPLICATION_ID}')
            db.execute('PRAGMA user_version=1')
            db.execute("INSERT INTO jobs VALUES(1,'old.pdf','old.pdf',?,'saved/old.pdf','failed','before','before')", ('a'*64,))
            db.execute("INSERT INTO attempts VALUES(1,1,'owner','failed','before','before','before','{}',NULL,'old error','[]')")
            db.execute("INSERT INTO events VALUES(1,1,1,'before','failed','{}')")
            columns = {table: [row[1] for row in db.execute(f'PRAGMA table_info({table})')] for table in ('jobs','attempts','events')}
            before = {table: db.execute(f'SELECT * FROM {table}').fetchall() for table in columns}
        migrated = JobStore(database)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], SCHEMA_VERSION)
            for table, rows in before.items():
                self.assertEqual(db.execute(f"SELECT {','.join(columns[table])} FROM {table}").fetchall(), rows)
        self.assertEqual(migrated.counts()['failed'], 1)
        self.assertEqual(migrated.intake_files(self.config.incoming_dir), [])
        JobStore(database)  # Reopening a migrated database is idempotent.


if __name__ == '__main__':
    unittest.main()
