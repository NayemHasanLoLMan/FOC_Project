"""Local read-only dashboard. Web requests never claim work or invoke models."""
from datetime import datetime, time as day_time, timedelta, timezone
import hashlib
from importlib import metadata as packages
import io
import json
from pathlib import Path
import platform
import shutil
import secrets
from uuid import UUID
from .invoice_edits import EDIT_FIELDS, validate_changes, edited_data
import threading
import time
import urllib.request

from flask import Flask, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException, SecurityError

from . import __version__
from .job_store import JobStore, STATES
from .pipeline_config import ROOT, attempt_metadata
from .processing_evidence import model_image, page_preview

FIELD_LABELS = {'invoice_number':'Invoice number', 'export_date':'Invoice date', 'consignee':'Consignee',
                'consignee_address':'Consignee address / BIN', 'shipping_marks':'Shipping marks',
                'package_count':'Package count', 'gross_weight_kg':'Gross weight', 'net_weight_kg':'Net weight',
                'total_value':'Invoice value', 'goods_quantity':'Goods quantity', 'unit_price':'Unit price',
                'description':'Description', 'quantity':'Quantity', 'unit':'Unit', 'goods':'Goods'}
STATE_LABELS = {'completed':'Invoice ready', 'queued':'Waiting to start', 'running':'Processing',
                'waiting_to_save':'Waiting to save', 'failed':'Could not finish',
                'interrupted':'Stopped before finishing', 'waiting_for_file':'Waiting for PDF'}


def _field_label(value):
    return FIELD_LABELS.get(value, value.replace('_', ' ').capitalize())


def _issue_text(issue):
    parts = issue.split(':')
    if parts[0] == 'missing':
        field = ('Item '+parts[2]+' — '+_field_label(parts[3])) if len(parts)==4 and parts[1]=='goods' else _field_label(':'.join(parts[1:]))
        return field+' was left blank because no usable value was established.'
    if parts[0] in ('vision_failed', 'vision_decision') and len(parts)>=3:
        return 'The image reader could not provide a usable reading for '+_field_label(parts[1]).lower()+' on '+parts[2].replace('page-', 'page ')+'.'
    return 'An additional processing note was recorded. Its original message is available in Technical details.'


def _reading_value(value, field):
    if value is None or value == '':
        return 'No clear reading'
    if isinstance(value, (str, int, float)):
        return str(value)+(' kg' if field=='gross_weight_kg' and isinstance(value,(int,float)) else '')
    if isinstance(value, list):
        texts = [str(text) for cell in value if isinstance(cell,dict) for text in cell.get('text',[]) if text]
        return ' / '.join(texts) or 'No clear text reading'
    return 'No usable reading'


def _readable_time(value):
    return datetime.fromisoformat(value).astimezone().strftime('%d %b %Y, %I:%M %p') if value else 'Not finished'


def _user_summary(attempt, state):
    if attempt and attempt['metadata'].get('manual_edit'):
        return {'result':{'completed':'Your edited invoice is ready to download.', 'failed':'The edited invoice could not be saved.',
                          'interrupted':'Saving the edited invoice was interrupted.', 'waiting_to_save':'Your edited invoice is waiting to be saved.'}.get(state,'Your invoice changes are being saved.'),
                'how':'Manual changes use the saved invoice information. The original PDF readings and earlier invoices are preserved.',
                'notes':list(dict.fromkeys(_issue_text(issue) for issue in attempt['issues']))}
    result = {'completed':'The invoice was created and is ready to download.',
              'waiting_to_save':'The invoice has been created. Saving it to the output folder is still pending.',
              'failed':'This run could not finish. An invoice is not available from this run.',
              'interrupted':'Processing stopped before this run finished.',
              'running':'The PDF is being processed.',
              'queued':'The PDF is waiting for processing to start.',
              'waiting_for_file':'The PDF is waiting to be accepted.'}.get(state, 'Processing status is not available.')
    summary = attempt.get('metadata',{}).get('processing') if attempt else None
    if summary is None:
        how = 'Reading details have not been recorded for this run.'
    elif summary.get('vision_contributions'):
        fields = list(dict.fromkeys(_field_label(c['field']).lower() for c in summary['vision_contributions']))
        how = 'Text recognition read the PDF. The local image reader helped with '+', '.join(fields)+'.'
    elif summary.get('vision_attempts'):
        how = ('The image reader was tried for unclear areas, but its readings were not used in the final invoice.'
               if summary.get('vision_contributions') == [] else 'The image reader is checking unclear areas of the PDF.')
    else:
        how = 'The PDF was read using text recognition and the invoice rules.'
    return {'result':result, 'how':how,
            'notes':list(dict.fromkeys(_issue_text(issue) for issue in attempt['issues'])) if attempt else []}


def _age(value):
    return max(0, (datetime.now(timezone.utc)-datetime.fromisoformat(value)).total_seconds()) if value else None


def _health(row, stale_after):
    if row is None:
        return {'state': 'unknown', 'heartbeat_at': None, 'age_seconds': None}
    age = _age(row['heartbeat_at'])
    return {**row, 'age_seconds': age,
            'state': 'unknown' if row['state'] in ('running', 'degraded') and age > stale_after else row['state']}


def _method(attempt):
    if attempt.get('metadata',{}).get('manual_edit'):
        return 'Manually edited'
    summary = attempt.get('metadata', {}).get('processing')
    if summary is None:
        return 'Not recorded'
    if summary.get('vision_contributions'):
        return 'Vision assisted'
    if summary.get('vision_attempts'):
        return 'Vision attempted' if summary.get('vision_contributions') is None else 'Vision attempted; no final contribution'
    return 'OCR / source rules' if summary.get('vision_contributions') == [] else 'Processing'


def _file_bytes(path, root, digest):
    path, root = Path(path), Path(root)
    if root.resolve() != root or path.is_symlink() or not path.resolve().is_relative_to(root):
        raise ValueError('File is outside managed storage')
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError('File no longer matches the retained version')
    return content


def _prepared(job, attempt, kind):
    base = Path(attempt['metadata']['configuration']['artifact_dir'])
    folder = base / 'jobs' / str(job['id']) / f"attempt-{attempt['id']}"
    receipt = folder / 'ready.json'
    if (receipt.is_symlink() or not folder.resolve().is_relative_to(base)
            or not receipt.resolve().is_relative_to(folder)):
        raise ValueError('Receipt is outside managed storage')
    ready = json.loads(receipt.read_text(encoding='utf-8'))
    if (ready['job_id'], ready['attempt_id'], ready['source_sha256']) != (job['id'], attempt['id'], job['source_sha256']):
        raise ValueError('Receipt identifies another attempt')
    key = 'data' if kind == 'data' else 'workbook'
    name = ready[key+'_name']
    if Path(name).name != name:
        raise ValueError('Artifact name is not a basename')
    if kind == 'invoice':
        root = Path(attempt['metadata']['configuration']['output_dir'])
        path = Path(attempt['output_path'])
        if path.parent != root or path.suffix.lower() != '.xlsx':
            raise ValueError('Invoice is outside its recorded output folder')
    else:
        root, path = folder, folder / name
    return _file_bytes(path, root, ready[key+'_sha256'])


def _public(value):
    if isinstance(value, dict):
        return {k: _public(v) for k, v in value.items() if k not in
                ('image_path', 'artifact_path', 'destination', 'snapshot_path', 'output_path', 'receipt_path', 'source_path','manual_edit_json')}
    if isinstance(value, list):
        return [_public(v) for v in value]
    return value


class DashboardData:
    def __init__(self, config):
        self.config = config
        self.store = JobStore(config.state_dir / 'jobs.sqlite3', read_only=True)
        self.started = time.monotonic()
        self._ollama_lock = threading.Lock()
        self._ollama_checked = 0
        self._ollama = None

    def jobs(self, filters, page=1):
        query = '''WITH current AS (
            SELECT j.*, a.id AS attempt_id, a.metadata_json, a.issues_json, a.error,
                a.started_at, a.finished_at, base_name(j.source_path) AS filename,
                (SELECT json_extract(e.details_json,'$.value') FROM events e
                 WHERE e.attempt_id=a.id AND json_extract(e.details_json,'$.kind')='field_source'
                 AND json_extract(e.details_json,'$.field')='invoice_number' ORDER BY e.id DESC LIMIT 1) AS invoice_number,
                (SELECT json_extract(e.details_json,'$.value') FROM events e
                 WHERE e.attempt_id=a.id AND json_extract(e.details_json,'$.kind')='field_source'
                 AND json_extract(e.details_json,'$.field')='export_date' ORDER BY e.id DESC LIMIT 1) AS export_date
            FROM jobs j LEFT JOIN attempts a ON a.id=(SELECT MAX(id) FROM attempts WHERE job_id=j.id)
        ) SELECT * FROM current'''
        where, values = [], []
        if filters.get('q'):
            text = filters['q'].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            where.append("(filename LIKE ? ESCAPE '\\' OR invoice_number LIKE ? ESCAPE '\\')")
            values.extend(['%'+text+'%']*2)
        if filters.get('status'):
            where.append('state=?'); values.append(filters['status'])
        if filters.get('date'):
            where.append('export_date=?'); values.append(filters['date'])
        if filters.get('issues') == 'yes':
            where.append("COALESCE(issues_json,'[]')<>'[]'")
        elif filters.get('issues') == 'no':
            where.append("COALESCE(issues_json,'[]')='[]'")
        if where:
            query += ' WHERE '+' AND '.join(where)
        with self.store._connection() as db:
            db.create_function('base_name', 1, lambda name: Path(name).name)
            total = db.execute('SELECT COUNT(*) FROM ('+query+')', values).fetchone()[0]
            rows = db.execute(query+' ORDER BY id DESC LIMIT 25 OFFSET ?', [*values, (page-1)*25]).fetchall()
        jobs = []
        for row in rows:
            item = dict(row)
            item['metadata'] = json.loads(item.pop('metadata_json') or '{}')
            item['issues'] = json.loads(item.pop('issues_json') or '[]')
            item['method'] = _method(item)
            jobs.append(item)
        return {'jobs': jobs, 'total': total, 'page': page, 'pages': max(1, (total+24)//25)}

    def status(self):
        components = {r['name']: r for r in self.store.components()}
        local_now = datetime.now().astimezone()
        start = datetime.combine(local_now.date(), day_time.min, tzinfo=local_now.tzinfo)
        bounds = (start.astimezone(timezone.utc).isoformat(), (start+timedelta(days=1)).astimezone(timezone.utc).isoformat())
        with self.store._connection() as db:
            attempts = db.execute('SELECT COUNT(*) FROM attempts').fetchone()[0]
            received = db.execute('SELECT COUNT(*) FROM jobs WHERE created_at>=? AND created_at<?', bounds).fetchone()[0]
            completed = db.execute("SELECT COUNT(DISTINCT job_id) FROM attempts WHERE state='completed' AND finished_at>=? AND finished_at<?", bounds).fetchone()[0]
            with_issues = db.execute("""SELECT COUNT(*) FROM jobs j JOIN attempts a ON a.id=(SELECT MAX(id) FROM attempts WHERE job_id=j.id)
                WHERE j.state='completed' AND a.issues_json<>'[]'""").fetchone()[0]
            active = db.execute("SELECT job_id,started_at,metadata_json FROM attempts WHERE state='running'").fetchone()
        progress = None
        if active:
            summary = json.loads(active['metadata_json']).get('processing', {})
            stages = [e for e in self.store.events(active['job_id']) if e['details'].get('kind') == 'stage'
                      and e['details'].get('stage') == summary.get('stage')]
            last = stages[-1] if stages else None
            progress = {'job_id': active['job_id'], 'stage': summary.get('stage', 'starting'),
                        'stage_status': summary.get('stage_status'), 'last_observed_page': summary.get('page'),
                        'attempt_seconds': _age(active['started_at']),
                        'stage_seconds': (_age(last['created_at']) if last['details']['status']=='started'
                                          else last['details'].get('elapsed_seconds')) if last else None}
        intakes = self.store.intake_files(self.config.incoming_dir)
        intake_counts = {s: sum(i['state']==s for i in intakes) for s in ('waiting_for_file', 'queued', 'rejected', 'missing')}
        return {'web': 'available', 'web_uptime_seconds': time.monotonic()-self.started,
                'queue': self.store.queue_control(),
                'checked_at': datetime.now(timezone.utc).isoformat(), 'counts': self.store.counts(),
                'attempts': attempts, 'completed_with_issues': with_issues,
                'today': {'date': str(local_now.date()), 'timezone': str(local_now.tzinfo), 'received': received, 'completed': completed},
                'scanner': _health(components.get('scanner'), max(30, self.config.scan_interval_seconds*3+10)),
                'worker': _health(components.get('worker'), 30), 'active': progress,
                'intake_counts': intake_counts,
                'intake_issues': [{'filename': Path(r['source_path']).name, 'state': r['state'], 'error': r['error']}
                                  for r in intakes if r['state'] in ('rejected', 'waiting_for_file') and r['error']][-10:]}

    def ollama(self):
        if self.config.local_model is None:
            return {'state': 'disabled', 'model': None}
        with self._ollama_lock:
            if self._ollama is not None and time.monotonic()-self._ollama_checked < 10:
                return self._ollama
            try:
                with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=2) as response:
                    models = json.load(response)['models']
                installed = next((m for m in models if m['name'] in (self.config.local_model, self.config.local_model+':latest')), None)
                result = {'state': 'available' if installed else 'model_missing', 'model': self.config.local_model,
                          'digest': installed['digest'] if installed else None}
            except (OSError, ValueError, KeyError, TypeError):
                result = {'state': 'unavailable', 'model': self.config.local_model}
            self._ollama_checked = time.monotonic()
            self._ollama = {**result, 'checked_at': datetime.now(timezone.utc).isoformat()}
            return self._ollama

    def system(self):
        folders = []
        for name in ('incoming_dir', 'output_dir', 'state_dir', 'artifact_dir'):
            path = getattr(self.config, name)
            existing = path
            while not existing.exists() and existing != existing.parent:
                existing = existing.parent
            try:
                disk = shutil.disk_usage(existing)
                free, total = disk.free, disk.total
            except OSError:
                free = total = None
            folders.append({'name': name, 'path': str(path), 'exists': path.is_dir(), 'free_bytes': free, 'total_bytes': total})
        versions = {}
        for name in ('Flask', 'waitress', 'paddleocr', 'paddlepaddle', 'PyMuPDF', 'openpyxl'):
            try: versions[name] = packages.version(name)
            except packages.PackageNotFoundError: versions[name] = 'not installed'
        return {'folders': folders, 'versions': versions, 'application_version': __version__,
                'python': platform.python_version(), 'platform': platform.platform(),
                'template': str(ROOT/'templates/BD_template.xlsx'), 'fingerprints': attempt_metadata(self.config),
                'model': self.config.local_model, 'model_defaults': {'num_predict':4096, 'num_ctx':8192, 'timeout_seconds':7200},
                'scan_interval_seconds': self.config.scan_interval_seconds}

    def detail(self, job_id, attempt_id=None, event_page=1):
        job = self.store.get_job(job_id)
        attempts = self.store.attempts(job_id)
        attempt = next((a for a in attempts if a['id']==attempt_id), None) if attempt_id is not None else (attempts[-1] if attempts else None)
        if attempt_id is not None and attempt is None:
            raise KeyError(attempt_id)
        all_events = self.store.events(job_id)
        events = [e for e in all_events if attempt is None or e['attempt_id'] in (None, attempt['id'])]
        reading_attempt = attempt
        while reading_attempt and reading_attempt['metadata'].get('manual_edit'):
            base_id = reading_attempt['metadata']['manual_edit']['base_attempt_id']
            reading_attempt = next((a for a in attempts if a['id']==base_id and a['id']<reading_attempt['id']),None)
        reading_events = [e for e in all_events if reading_attempt and e['attempt_id']==reading_attempt['id']]
        data, data_error = None, None
        if attempt and attempt['state'] in ('completed', 'waiting_to_save'):
            try: data = json.loads(_prepared(job, attempt, 'data'))
            except (OSError, ValueError, KeyError, TypeError): data_error = 'Retained extracted data is missing or failed verification.'
        evidence = []
        for event in reading_events:
            if event['details'].get('kind') != 'vision_request':
                continue
            related = [e for e in reading_events if e['details'].get('call_id')==event['details'].get('call_id')]
            response = next((e['details'] for e in related if e['details'].get('kind')=='vision_response'), {})
            decision = next((e['details'] for e in related if e['details'].get('kind')=='vision_decision'), {})
            field = event['details'].get('field','unknown')
            summary = reading_attempt['metadata'].get('processing',{}) if reading_attempt else {}
            contributions = summary.get('vision_contributions')
            used = bool(decision.get('accepted')) and any(c['field']==field and (field!='goods_quantity' or c.get('source_ref')==event['details'].get('source_ref'))
                                                         for c in contributions or [])
            if used:
                outcome = 'This reading was used in the invoice.'
            elif decision.get('accepted'):
                outcome = ('The reading was accepted, but did not produce a final invoice value.'
                           if contributions is not None else 'The reading was accepted. The final invoice is not ready yet.')
            else:
                outcome = 'This reading was not accepted for the invoice.'
            if attempt and attempt['metadata'].get('manual_edit'):
                outcome = 'Original reading: ' + outcome
            answer = response.get('answer') or {}
            candidate = decision.get('candidate', answer.get('weight_kg') if field=='gross_weight_kg' else answer.get('text'))
            evidence.append({'request': event, 'related': related, 'label':_field_label(field),
                             'original':_reading_value(event['details'].get('original'),field),
                             'original_label':'First text reading on this page' if isinstance(event['details'].get('original'),list) else 'First text reading',
                             'reading':_reading_value(candidate,field), 'outcome':outcome,
                             'saved':response.get('cached',False),
                             'failed':any(e['details'].get('kind')=='vision_failed' for e in related)})
        stages = [e for e in events if e['details'].get('kind')=='stage']
        return {'job': {**job, 'filename': Path(job['source_path']).name}, 'attempt': attempt, 'attempts': attempts,
                'method': _method(attempt) if attempt else 'Not started', 'data': data, 'data_error': data_error,
                'user_summary':_user_summary(attempt, attempt['state'] if attempt else job['state']),
                'stages': stages, 'evidence': evidence, 'events': events[(event_page-1)*100:event_page*100],
                'event_page':event_page, 'event_pages':max(1,(len(events)+99)//100)}


def create_app(config):
    app = Flask(__name__, template_folder=str(ROOT/'frontend/templates'),
                static_folder=str(ROOT/'frontend/static'), static_url_path='/dashboard_static')
    app.config.update(TRUSTED_HOSTS=['127.0.0.1', 'localhost'], MAX_CONTENT_LENGTH=65536)
    data = DashboardData(config)
    app.extensions['dashboard_data'] = data
    app.jinja_env.filters['field_label'] = _field_label
    app.jinja_env.filters['readable_time'] = _readable_time
    app.jinja_env.filters['status_label'] = lambda value: STATE_LABELS.get(value,value.replace('_',' '))
    previews = threading.BoundedSemaphore(2)
    csrf_token = secrets.token_urlsafe(32)

    @app.context_processor
    def control_context():
        return {'csrf_token': csrf_token}

    @app.before_request
    def local_requests():
        if request.remote_addr not in ('127.0.0.1', '::1'):
            abort(403)
        if request.method not in ('GET', 'HEAD', 'POST'):
            abort(405)
        if request.headers.get('Sec-Fetch-Site') == 'cross-site':
            abort(403)
        if request.headers.get('Origin') and request.headers['Origin'] != request.host_url.rstrip('/'):
            abort(403)
        if request.method == 'POST':
            if request.url_rule is None or 'POST' not in request.url_rule.methods:
                abort(405)
            if request.headers.get('Origin') != request.host_url.rstrip('/') or not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), csrf_token):
                abort(403, description='Reload this dashboard before sending a command.')
            if not request.is_json:
                abort(415, description='Commands require application/json.')

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
            'X-Frame-Options':'DENY', 'Referrer-Policy':'no-referrer',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
        return response

    @app.errorhandler(Exception)
    def failure(error):
        if isinstance(error, SecurityError):
            return jsonify(error='Only localhost is accepted by this dashboard.'), 400
        if isinstance(error, HTTPException):
            code, message = error.code, error.description
        elif isinstance(error, (KeyError, StopIteration, FileNotFoundError)):
            code, message = 404, 'Requested job or retained file is unavailable.'
        elif isinstance(error, (ValueError, TypeError)):
            code, message = 409, 'Retained data failed verification or is unavailable for this request.'
        else:
            app.logger.exception('Dashboard request failed')
            code, message = 503, 'Dashboard data is temporarily unavailable. Check the local console.'
        if request.path.startswith(('/api/', '/images/', '/files/')):
            return jsonify(error=message), code
        return render_template('error.html', message=message, code=code), code

    def number(name, default):
        try:
            value = int(request.args.get(name, default))
            if not 1 <= value <= 1000000: raise ValueError()
            return value
        except ValueError:
            abort(400, description='Invalid page or attempt number.')

    def filters():
        values = {name: request.args.get(name, '').strip() for name in ('q', 'status', 'date', 'issues')}
        if len(values['q']) > 200 or values['status'] not in ('', *STATES) or values['issues'] not in ('', 'yes', 'no'):
            abort(400, description='Invalid job filter.')
        if values['date']:
            try: datetime.strptime(values['date'], '%Y-%m-%d')
            except ValueError: abort(400, description='Use YYYY-MM-DD for the document date.')
        return values

    @app.get('/')
    def overview():
        return render_template('overview.html', status=data.status(), listing=data.jobs({}, 1), filters={}, states=STATES)

    @app.get('/jobs')
    def jobs():
        selected = filters()
        return render_template('job_table.html' if request.args.get('partial')=='1' else 'jobs.html',
                               listing=data.jobs(selected, number('page', 1)), filters=selected, states=STATES)

    @app.get('/jobs/<int:job_id>')
    def detail(job_id):
        return render_template('detail.html', **_public(data.detail(job_id, number('attempt', 1) if 'attempt' in request.args else None,
                                                                  number('event_page',1))))

    @app.get('/jobs/<int:job_id>/edit')
    def edit(job_id):
        view = data.detail(job_id)
        if view['job']['state']!='completed' or not view['attempt'] or view['attempt']['state']!='completed':
            abort(409,description='This invoice is not ready for editing. Open its latest completed version.')
        if not view['data']:
            abort(409,description='The saved invoice information could not be verified.')
        if view['data'].get('template_type') not in (None,'BD'):
            abort(409,description='Editing is currently available for Bangladesh invoices.')
        return render_template('edit.html',**_public(view),edit_fields=EDIT_FIELDS)

    @app.get('/system')
    def system():
        return render_template('system.html', system=data.system())

    @app.get('/api/status')
    def status_api(): return jsonify(data.status())

    @app.get('/api/controls')
    def controls_api():
        return jsonify(csrf_token=csrf_token, queue=data.store.queue_control())

    def command(action, job_id=None):
        payload = request.get_json()
        keys = {'request_id'} if job_id is None else {'request_id', 'attempt_id'}
        if action == 'edit':
            keys.add('changes')
        if not isinstance(payload, dict) or set(payload) != keys:
            abort(400, description='Invalid command fields.')
        try:
            if not isinstance(payload['request_id'], str) or str(UUID(payload['request_id'])) != payload['request_id']:
                raise ValueError()
            if job_id is not None and (type(payload['attempt_id']) is not int or payload['attempt_id'] < 1):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            abort(400, description='Use a UUID request_id and a positive attempt_id.')
        writer = JobStore(data.store.path)
        changes = None
        if action == 'edit':
            try:
                changes = validate_changes(payload['changes'])
                original = data.store.get_attempt(payload['attempt_id'])
                if original['job_id'] != job_id or original['state']!='completed':
                    abort(409,description='Choose a completed invoice from this job.')
                edited_data(json.loads(_prepared(data.store.get_job(job_id),original,'data')),changes)
            except ValueError as error:
                abort(400,description=str(error))
        try:
            result = writer.admin_command(payload['request_id'], action, job_id=job_id, attempt_id=payload.get('attempt_id'),changes=changes)
        except ValueError as error:
            abort(409, description=str(error))
        return jsonify(result)

    @app.post('/api/queue/pause')
    def pause_api(): return command('pause')

    @app.post('/api/queue/resume')
    def resume_api(): return command('resume')

    @app.post('/api/jobs/<int:job_id>/retry')
    def retry_api(job_id): return command('retry', job_id)

    @app.post('/api/jobs/<int:job_id>/reprocess')
    def reprocess_api(job_id): return command('reprocess', job_id)

    @app.post('/api/jobs/<int:job_id>/retry-save')
    def retry_save_api(job_id): return command('retry_save', job_id)

    @app.post('/api/jobs/<int:job_id>/edit')
    def edit_api(job_id): return command('edit',job_id)

    @app.get('/api/ollama')
    def ollama_api(): return jsonify(data.ollama())

    @app.get('/api/system')
    def system_api(): return jsonify(data.system())

    @app.get('/api/jobs')
    def jobs_api(): return jsonify(_public(data.jobs(filters(), number('page',1))))

    @app.get('/api/jobs/<int:job_id>')
    def detail_api(job_id):
        return jsonify(_public(data.detail(job_id, number('attempt',1) if 'attempt' in request.args else None, number('event_page',1))))

    @app.get('/api/jobs/<int:job_id>/status')
    def job_status(job_id):
        job = data.store.get_job(job_id)
        return jsonify(job_id=job_id, state=job['state'], status_label=STATE_LABELS.get(job['state'],job['state']),
                       updated_at=job['updated_at'])

    @app.get('/files/jobs/<int:job_id>/source')
    def source(job_id):
        job = data.store.get_job(job_id)
        attempts = data.store.attempts(job_id)
        base = Path(attempts[-1]['metadata']['configuration']['artifact_dir']) if attempts else config.artifact_dir
        content = _file_bytes(job['snapshot_path'], base/'inputs', job['source_sha256'])
        return send_file(io.BytesIO(content), mimetype='application/pdf', as_attachment=True, download_name=Path(job['source_path']).name)

    @app.get('/files/attempts/<int:attempt_id>/invoice')
    def invoice(attempt_id):
        attempt = data.store.get_attempt(attempt_id)
        if attempt['state'] != 'completed': abort(409, description='This attempt has no published invoice.')
        job = data.store.get_job(attempt['job_id'])
        content = _prepared(job, attempt, 'invoice')
        return send_file(io.BytesIO(content), mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                         as_attachment=True, download_name=Path(attempt['output_path']).name)

    @app.get('/images/jobs/<int:job_id>/events/<int:event_id>')
    def image(job_id, event_id):
        return send_file(io.BytesIO(model_image(data.store, job_id, event_id)), mimetype='image/png')

    @app.get('/images/jobs/<int:job_id>/pages/<int:page>')
    def preview(job_id, page):
        if not previews.acquire(blocking=False): abort(429, description='Other source previews are rendering; retry shortly.')
        try:
            content = page_preview(data.store, job_id, page, number('event',1) if 'event' in request.args else None)
            return send_file(io.BytesIO(content), mimetype='image/png')
        finally:
            previews.release()

    return app
