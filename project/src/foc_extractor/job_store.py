"""Durable local jobs, attempts, recovery transitions and component health."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sqlite3

STATES = ('waiting_for_file', 'queued', 'running', 'waiting_to_save', 'completed', 'failed', 'interrupted')
APPLICATION_ID = 0x464F4349
SCHEMA_VERSION = 3
SCHEMA = (
    """CREATE TABLE jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_path TEXT NOT NULL, source_identity TEXT NOT NULL,
        source_sha256 TEXT NOT NULL CHECK(length(source_sha256)=64),
        snapshot_path TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('waiting_for_file','queued','running','waiting_to_save','completed','failed','interrupted')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(source_identity, source_sha256))""",
    """CREATE TABLE attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id),
        worker_id TEXT NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('running','waiting_to_save','completed','failed','interrupted')),
        started_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL, finished_at TEXT,
        metadata_json TEXT NOT NULL, output_path TEXT, error TEXT,
        issues_json TEXT NOT NULL DEFAULT '[]')""",
    "CREATE UNIQUE INDEX one_running_attempt ON attempts((1)) WHERE state='running'",
    "CREATE UNIQUE INDEX one_unfinished_attempt_per_job ON attempts(job_id) WHERE finished_at IS NULL",
    """CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id INTEGER NOT NULL REFERENCES jobs(id),
        attempt_id INTEGER REFERENCES attempts(id), created_at TEXT NOT NULL,
        kind TEXT NOT NULL, details_json TEXT NOT NULL)""",
)
INTAKE_SCHEMA = """CREATE TABLE intake_files (
    source_identity TEXT PRIMARY KEY, source_path TEXT NOT NULL,
    signature TEXT, stable_since REAL NOT NULL, last_seen REAL NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('waiting_for_file','queued','rejected','missing')),
    error TEXT, job_id INTEGER REFERENCES jobs(id))"""


def _identity(path):
    return os.path.normcase(str(Path(path).resolve()))


def _now():
    return datetime.now(timezone.utc).isoformat()


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')
    return value.strip()


def _attempt(row):
    result = dict(row)
    result['metadata'] = json.loads(result.pop('metadata_json'))
    result['issues'] = json.loads(result.pop('issues_json'))
    return result


class JobStore:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection(write=True) as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            application_id = db.execute('PRAGMA application_id').fetchone()[0]
            if version == 0 and application_id == 0:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone():
                    raise ValueError('Refusing to initialize an unrelated database')
                for statement in SCHEMA:
                    db.execute(statement)
                db.execute(f'PRAGMA application_id={APPLICATION_ID}')
                db.execute('PRAGMA user_version=1')
            elif version not in (1, 2, SCHEMA_VERSION) or application_id != APPLICATION_ID:
                raise ValueError('Unsupported pipeline database identity or schema version')
            if version < 2:
                db.execute(INTAKE_SCHEMA)
            if version < 3:
                db.execute('ALTER TABLE attempts ADD COLUMN receipt_path TEXT')
                db.execute('''CREATE TABLE components (
                    name TEXT PRIMARY KEY, owner TEXT NOT NULL, pid INTEGER NOT NULL,
                    state TEXT NOT NULL, heartbeat_at TEXT NOT NULL, error TEXT)''')
            if version < SCHEMA_VERSION:
                db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

    @contextmanager
    def _connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            with db:
                if write:
                    db.execute('BEGIN IMMEDIATE')
                yield db
        finally:
            db.close()

    def _event(self, db, job_id, attempt_id, kind, details):
        db.execute('INSERT INTO events(job_id,attempt_id,created_at,kind,details_json) VALUES(?,?,?,?,?)',
                   (job_id, attempt_id, _now(), kind, json.dumps(details, allow_nan=False)))

    def enqueue(self, source_path: Path, source_sha256: str, snapshot_path: Path) -> int:
        """Accept an intake-validated snapshot; the scanner will validate PDF bytes."""
        source = Path(source_path).resolve()
        snapshot = Path(snapshot_path).resolve()
        if source.suffix.lower() != '.pdf' or snapshot.name != source.name:
            raise ValueError('A PDF snapshot must preserve the original source filename')
        if not isinstance(source_sha256, str) or not re.fullmatch('[0-9a-fA-F]{64}', source_sha256):
            raise ValueError('source_sha256 must be a SHA-256 hex digest')
        identity = _identity(source)
        digest = source_sha256.lower()
        now = _now()
        with self._connection(write=True) as db:
            inserted = db.execute('''INSERT INTO jobs(source_path,source_identity,source_sha256,snapshot_path,state,created_at,updated_at)
                VALUES(?,?,?,?,'queued',?,?) ON CONFLICT(source_identity,source_sha256) DO NOTHING''',
                (str(source), identity, digest, str(snapshot), now, now)).rowcount
            job_id = db.execute('SELECT id FROM jobs WHERE source_identity=? AND source_sha256=?',
                                (identity, digest)).fetchone()[0]
            if inserted:
                same_content = [row[0] for row in db.execute(
                    'SELECT id FROM jobs WHERE source_sha256=? AND source_identity<>? ORDER BY id', (digest, identity))]
                self._event(db, job_id, None, 'queued', {'same_content_job_ids': same_content})
            return job_id

    def observe_intake(self, source_path: Path, signature: str | None, seen_at: float, error=None) -> dict:
        source = Path(source_path).resolve()
        identity = _identity(source)
        with self._connection(write=True) as db:
            row = db.execute('SELECT * FROM intake_files WHERE source_identity=?', (identity,)).fetchone()
            if (row is None or row['signature'] != signature or row['state'] == 'missing'
                    or error is not None or seen_at < row['last_seen']):
                db.execute('''INSERT INTO intake_files(source_identity,source_path,signature,stable_since,last_seen,state,error)
                    VALUES(?,?,?,?,?,'waiting_for_file',?) ON CONFLICT(source_identity) DO UPDATE SET
                    signature=excluded.signature,stable_since=excluded.stable_since,last_seen=excluded.last_seen,
                    state='waiting_for_file',error=excluded.error,job_id=NULL''',
                    (identity, str(source), signature, seen_at, seen_at, error))
            else:
                db.execute('UPDATE intake_files SET last_seen=? WHERE source_identity=?', (seen_at, identity))
            return dict(db.execute('SELECT * FROM intake_files WHERE source_identity=?', (identity,)).fetchone())

    def finish_intake(self, source_path: Path, signature: str, state: str, *, error=None, job_id=None):
        if state not in ('queued', 'rejected'):
            raise ValueError('Intake completion must be queued or rejected')
        with self._connection(write=True) as db:
            # A concurrent scan of newer bytes must keep its own readiness state.
            return bool(db.execute('''UPDATE intake_files SET state=?,error=?,job_id=?
                WHERE source_identity=? AND signature=?''',
                (state, error, job_id, _identity(source_path), signature)).rowcount)

    def intake_files(self, folder: Path) -> list[dict]:
        folder = Path(folder).resolve()
        with self._connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM intake_files ORDER BY source_identity')
                    if Path(row['source_path']).parent == folder]

    def mark_missing_intakes(self, folder: Path, seen: set[str]):
        folder = Path(folder).resolve()
        with self._connection(write=True) as db:
            for row in db.execute('SELECT * FROM intake_files').fetchall():
                if Path(row['source_path']).parent == folder and row['source_identity'] not in seen:
                    db.execute("UPDATE intake_files SET state='missing',error=? WHERE source_identity=?",
                               ('Source no longer present; accepted snapshots and jobs are retained', row['source_identity']))

    def get_job(self, job_id: int) -> dict:
        with self._connection() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            return dict(row)

    def counts(self) -> dict:
        with self._connection() as db:
            return {**dict.fromkeys(STATES, 0), **dict(db.execute('SELECT state,COUNT(*) FROM jobs GROUP BY state'))}

    def claim_next(self, worker_id: str, metadata: dict) -> dict | None:
        worker_id = _text(worker_id, 'worker_id')
        if not isinstance(metadata, dict):
            raise ValueError('Attempt metadata must be a dictionary')
        serialized = json.dumps(metadata, allow_nan=False, sort_keys=True)
        with self._connection(write=True) as db:
            if db.execute("SELECT 1 FROM attempts WHERE state='running'").fetchone():
                return None
            job = db.execute("SELECT id FROM jobs WHERE state='queued' ORDER BY id LIMIT 1").fetchone()
            if job is None:
                return None
            now = _now()
            attempt_id = db.execute('''INSERT INTO attempts(job_id,worker_id,state,started_at,heartbeat_at,metadata_json)
                VALUES(?,?,'running',?,?,?)''', (job[0], worker_id, now, now, serialized)).lastrowid
            db.execute("UPDATE jobs SET state='running',updated_at=? WHERE id=?", (now, job[0]))
            self._event(db, job[0], attempt_id, 'started', {'worker_id': worker_id})
            return _attempt(db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone())

    def heartbeat(self, attempt_id: int, worker_id: str):
        with self._connection(write=True) as db:
            updated = db.execute("UPDATE attempts SET heartbeat_at=? WHERE id=? AND worker_id=? AND state='running'",
                                 (_now(), attempt_id, worker_id)).rowcount
            if not updated:
                raise ValueError('Attempt is not running under this worker')

    def finish(self, attempt_id: int, worker_id: str, state: str, *, output_path=None, error=None, issues=None):
        if state not in ('completed', 'failed', 'interrupted'):
            raise ValueError('Finish state must be completed, failed or interrupted')
        if state == 'completed':
            if error is not None or output_path is None or not Path(output_path).is_file() or Path(output_path).suffix.lower() != '.xlsx':
                raise ValueError('Completion requires an existing XLSX output and no error')
        elif output_path is not None or not isinstance(error, str) or not error.strip():
            raise ValueError('Failure/interruption requires an error and no published output')
        issues = [] if issues is None else issues
        if not isinstance(issues, list) or any(not isinstance(issue, str) for issue in issues):
            raise ValueError('Issues must be a list of strings')
        with self._connection(write=True) as db:
            row = db.execute("SELECT job_id FROM attempts WHERE id=? AND worker_id=? AND state IN ('running','waiting_to_save')",
                             (attempt_id, worker_id)).fetchone()
            if row is None:
                raise ValueError('Attempt is not running under this worker')
            now = _now()
            db.execute('''UPDATE attempts SET state=?,finished_at=?,heartbeat_at=?,output_path=?,error=?,issues_json=? WHERE id=?''',
                       (state, now, now, str(Path(output_path).resolve()) if output_path else None,
                        error, json.dumps(issues), attempt_id))
            db.execute('UPDATE jobs SET state=?,updated_at=? WHERE id=?', (state, now, row[0]))
            self._event(db, row[0], attempt_id, state, {'error': error, 'issues': issues})

    def get_attempt(self, attempt_id: int) -> dict:
        with self._connection() as db:
            row = db.execute('SELECT * FROM attempts WHERE id=?', (attempt_id,)).fetchone()
            if row is None:
                raise KeyError(attempt_id)
            return _attempt(row)

    def unfinished_attempts(self) -> list[dict]:
        with self._connection() as db:
            return [_attempt(row) for row in db.execute('SELECT * FROM attempts WHERE finished_at IS NULL ORDER BY id')]

    def prepare(self, attempt_id: int, owner: str, receipt_path: Path):
        if not Path(receipt_path).is_file():
            raise ValueError('Prepared receipt does not exist')
        with self._connection(write=True) as db:
            row = db.execute("SELECT job_id FROM attempts WHERE id=? AND worker_id=? AND state='running'", (attempt_id, owner)).fetchone()
            if row is None:
                raise ValueError('Attempt is not running under this worker')
            db.execute("UPDATE attempts SET state='waiting_to_save',receipt_path=?,error=NULL WHERE id=?",
                       (str(Path(receipt_path).resolve()), attempt_id))
            db.execute("UPDATE jobs SET state='waiting_to_save',updated_at=? WHERE id=?", (_now(), row[0]))
            self._event(db, row[0], attempt_id, 'prepared', {})

    def publication_error(self, attempt_id: int, owner: str, error: str):
        with self._connection(write=True) as db:
            row = db.execute("SELECT job_id,error FROM attempts WHERE id=? AND worker_id=? AND state='waiting_to_save'",
                             (attempt_id, owner)).fetchone()
            if row is None:
                raise ValueError('Prepared attempt is not owned by this worker')
            db.execute('UPDATE attempts SET error=? WHERE id=?', (error, attempt_id))
            if row['error'] != error:
                self._event(db, row['job_id'], attempt_id, 'waiting_to_save', {'error': error})

    def recover_attempt(self, attempt_id: int, old_owner: str, owner: str, lock_path: Path, receipt_path=None):
        """Caller must hold the OS lock, proving the previous managed worker exited."""
        with self._connection(write=True) as db:
            row = db.execute('SELECT * FROM attempts WHERE id=? AND worker_id=? AND finished_at IS NULL',
                             (attempt_id, old_owner)).fetchone()
            if row is None or json.loads(row['metadata_json']).get('worker_lock') != str(Path(lock_path).resolve()):
                raise ValueError('Cannot recover an attempt outside this managed worker lock')
            now = _now()
            if receipt_path is not None:
                db.execute("UPDATE attempts SET worker_id=?,state='waiting_to_save',receipt_path=?,heartbeat_at=? WHERE id=?",
                           (owner, str(Path(receipt_path).resolve()), now, attempt_id))
                db.execute("UPDATE jobs SET state='waiting_to_save',updated_at=? WHERE id=?", (now, row['job_id']))
                self._event(db, row['job_id'], attempt_id, 'recovered_prepared', {'previous_owner': old_owner, 'owner': owner})
            else:
                error = 'Managed worker exited before a verified workbook was prepared'
                db.execute("UPDATE attempts SET state='interrupted',finished_at=?,error=? WHERE id=?", (now, error, attempt_id))
                interrupted = db.execute("SELECT COUNT(*) FROM attempts WHERE job_id=? AND state='interrupted'", (row['job_id'],)).fetchone()[0]
                state = 'failed' if interrupted >= 3 else 'queued'
                db.execute('UPDATE jobs SET state=?,updated_at=? WHERE id=?', (state, now, row['job_id']))
                self._event(db, row['job_id'], attempt_id, 'interrupted', {'error': error})
                self._event(db, row['job_id'], None, 'recovery_limit' if state == 'failed' else 'queued_again', {})

    def component(self, name: str, owner: str, pid: int, state: str, error=None):
        with self._connection(write=True) as db:
            db.execute('''INSERT INTO components VALUES(?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET
                owner=excluded.owner,pid=excluded.pid,state=excluded.state,heartbeat_at=excluded.heartbeat_at,error=excluded.error''',
                (name, owner, pid, state, _now(), error))

    def touch_worker(self, owner: str):
        with self._connection(write=True) as db:
            now = _now()
            if not db.execute("UPDATE components SET heartbeat_at=? WHERE name='worker' AND owner=?", (now, owner)).rowcount:
                raise ValueError('Worker component ownership changed')
            db.execute("UPDATE attempts SET heartbeat_at=? WHERE worker_id=? AND finished_at IS NULL", (now, owner))

    def components(self) -> list[dict]:
        with self._connection() as db:
            return [dict(row) for row in db.execute('SELECT * FROM components ORDER BY name')]

    def retry(self, job_id: int):
        with self._connection(write=True) as db:
            updated = db.execute("UPDATE jobs SET state='queued',updated_at=? WHERE id=? AND state IN ('failed','interrupted')",
                                 (_now(), job_id)).rowcount
            if not updated:
                raise ValueError('Only failed or interrupted jobs can be queued again')
            self._event(db, job_id, None, 'queued_again', {})

    def attempts(self, job_id: int) -> list[dict]:
        with self._connection() as db:
            return [_attempt(row) for row in db.execute('SELECT * FROM attempts WHERE job_id=? ORDER BY id', (job_id,))]

    def events(self, job_id: int) -> list[dict]:
        with self._connection() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM events WHERE job_id=? ORDER BY id', (job_id,))]
            for row in rows:
                row['details'] = json.loads(row.pop('details_json'))
            return rows
