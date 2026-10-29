'use strict';
const text = (selector, value) => document.querySelectorAll(selector).forEach(node => { node.textContent = value; });
const statusText = (selector, value, state) => document.querySelectorAll(selector).forEach(node => {
  node.textContent = value; node.dataset.state = state;
});
const seconds = value => value == null ? 'not recorded' : Math.round(value) + 's';
async function getJSON(url) {
  const response = await fetch(url, {cache:'no-store', signal:AbortSignal.timeout(8000)});
  if (!response.ok) throw new Error('Status ' + response.status);
  return response.json();
}
let refreshing = false;
async function refresh() {
  if (refreshing || document.hidden) return;
  refreshing = true;
  try {
    const status = await getJSON('/api/status');
    statusText('#web-status', 'Web available', 'available');
    statusText('#queue-state', status.queue.paused ? 'Processing paused' : 'Ready to process', status.queue.paused ? 'paused' : status.worker.state === 'running' ? 'ready' : 'unknown');
    const queueButton = document.querySelector('[data-queue-control]');
    if (queueButton && !queueButton.disabled) {
      const endpoint = '/api/queue/' + (status.queue.paused ? 'resume' : 'pause');
      if (queueButton.dataset.command !== endpoint) delete queueButton.dataset.requestId;
      queueButton.dataset.command = endpoint;
      queueButton.textContent = status.queue.paused ? 'Resume processing' : 'Pause processing';
    }
    text('#refreshed', 'Status checked ' + new Date(status.checked_at).toLocaleTimeString());
    for (const [name, count] of Object.entries(status.counts)) text('[data-count="' + name + '"]', count);
    for (const [name, count] of Object.entries(status.intake_counts)) text('[data-intake="' + name + '"]', count);
    text('[data-summary="received"]', status.today.received);
    text('[data-summary="completed"]', status.today.completed);
    text('[data-summary="attempts"]', status.attempts);
    text('[data-summary="issues"]', status.completed_with_issues);
    for (const name of ['scanner', 'worker']) {
      const health = status[name];
      statusText('[data-health="' + name + '"]', health.state, health.state);
      text('[data-component-error="' + name + '"]', health.error || '');
      text('[data-heartbeat="' + name + '"]', health.heartbeat_at ? 'Heartbeat ' + new Date(health.heartbeat_at).toLocaleString() + ' · ' + seconds(health.age_seconds) + ' ago' : 'No heartbeat recorded');
    }
    const active = status.active;
    statusText('#activity-title', active ? 'Job #' + active.job_id : 'No active conversion', active && status.worker.state === 'running' ? 'running' : active ? 'unknown' : 'idle');
    text('#activity-detail', active ? active.stage + ' · ' + (active.stage_status || 'starting') + (active.last_observed_page ? ' · last observed page ' + active.last_observed_page : '') : status.queue.paused ? 'Processing is paused. New PDFs can still join the queue.' : 'The worker will claim the next queued PDF when running.');
    text('#activity-time', active ? 'Stage ' + seconds(active.stage_seconds) + ' · attempt ' + seconds(active.attempt_seconds) + (status.worker.state !== 'running' ? ' · Worker is not reporting a recent running heartbeat; this is retained progress.' : ' · No completion ETA assumed.') : 'Stage elapsed time is shown during processing. Completion ETA is not estimated.');
    const issueList = document.querySelector('#intake-issues');
    if (issueList) {
      issueList.replaceChildren();
      for (const issue of status.intake_issues) {
        const li = document.createElement('li');
        li.textContent = issue.filename + ' — ' + issue.state + ': ' + issue.error;
        issueList.append(li);
      }
      if (!status.intake_issues.length) { const li = document.createElement('li'); li.textContent = 'No intake errors recorded.'; li.className = 'muted'; issueList.append(li); }
    }
    const listing = document.querySelector('#job-list');
    if (listing && !listing.contains(document.activeElement)) {
      const response = await fetch(listing.dataset.refreshUrl, {cache:'no-store', signal:AbortSignal.timeout(8000)});
      if (response.ok) listing.innerHTML = await response.text(); // Server-rendered, autoescaped HTML only.
    }
    const detail = document.querySelector('[data-job]');
    if (detail) {
      const current = await getJSON('/api/jobs/' + detail.dataset.job + '/status');
      statusText('#detail-state', current.status_label || current.state.replaceAll('_', ' '), current.state);
      if (detail.dataset.displayState !== current.state && current.state === 'completed' && !new URLSearchParams(location.search).has('attempt')) {
        location.reload();
      }
      detail.dataset.displayState = current.state;
    }
  } catch (error) {
    statusText('#web-status', 'Status unavailable', 'error');
    statusText('[data-health]', 'unknown', 'unknown');
    statusText('#queue-state', 'Queue status unavailable', 'unknown');
    statusText('#activity-title', 'Activity status unavailable', 'unknown');
    text('#refreshed', 'Refresh failed; displayed information may be stale.');
  } finally { refreshing = false; }
}
let checkingModel = false;
function updateModelOptions(result) {
  const select = document.querySelector('#vision-model');
  if (!select) return;
  if (!result.model_list_available) {
    text('#model-list-status','Ollama is unavailable. Your selection is kept; the list will refresh automatically.');
    return;
  }
  const names = [...new Set(result.models)].sort();
  const selected = select.value;
  const signature = JSON.stringify([names,selected]);
  if (select.dataset.models !== signature) {
    const options = [new Option('OCR only — vision disabled',''), ...names.map(name => new Option(name,name))];
    if (selected && !names.includes(selected)) options.push(new Option(selected + (names.includes(selected+':latest') ? ' (current)' : ' (unavailable)'),selected));
    select.replaceChildren(...options);
    select.value = selected;
    select.dataset.models = signature;
  }
  text('#model-list-status',names.length ? 'Installed Ollama models. Select a vision-capable model for image reading.' : 'No Ollama models are installed. OCR only is available.');
}
async function refreshModel() {
  if (checkingModel || document.hidden) return;
  checkingModel = true;
  try { const result = await getJSON('/api/ollama'); statusText('[data-health="ollama"]', result.state.replaceAll('_', ' '), result.state); updateModelOptions(result); }
  catch (error) { statusText('[data-health="ollama"]', 'unknown', 'unknown'); updateModelOptions({model_list_available:false}); }
  finally { checkingModel = false; }
}
document.addEventListener('toggle', event => {
  if (!(event.target instanceof HTMLDetailsElement) || !event.target.open) return;
  event.target.querySelectorAll('img[data-src]').forEach(image => {
    image.addEventListener('error', () => {
      const message = document.createElement('p'); message.className = 'image-error';
      message.textContent = 'Image unavailable or failed verification. Reload this page to retry.';
      image.replaceWith(message);
    }, {once:true});
    image.src = image.dataset.src; image.removeAttribute('data-src');
  });
}, true);
refresh(); refreshModel();
setInterval(refresh, 5000); setInterval(refreshModel, 15000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) { refresh(); refreshModel(); } });

document.addEventListener('click', async event => {
  const button = event.target.closest('[data-command]');
  if (!button || button.disabled) return;
  if (button.dataset.confirm && !window.confirm(button.dataset.confirm)) return;
  button.disabled = true;
  button.dataset.requestId ||= crypto.randomUUID();
  const payload = {request_id: button.dataset.requestId};
  if (button.dataset.attempt) payload.attempt_id = Number(button.dataset.attempt);
  try {
    const response = await fetch(button.dataset.command, {method:'POST', cache:'no-store',
      signal:AbortSignal.timeout(8000), headers:{'Content-Type':'application/json',
      'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content}, body:JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The command could not be accepted.');
    if (result.action === 'development_reset') {
      text('#command-result', 'Cleared ' + result.cleared_jobs + ' jobs. A recovery archive was saved. Processing has resumed. PDFs still in the inbox will be picked up automatically and their invoices recreated.');
      delete button.dataset.requestId;
      return;
    }
    if (result.job_id && result.action !== 'retry_save') {
      window.location.assign('/jobs/' + result.job_id);
      return;
    }
    text('#command-result', result.action === 'retry_save' ? 'Save retry requested. The running worker will check the prepared invoice on its next pass.' : result.paused ? 'Processing paused. The current invoice can finish.' : 'Processing resumed. A running worker can start the next queued PDF.');
  } catch (error) {
    text('#command-result', error.name === 'TimeoutError' || error.name === 'TypeError' ? 'No response received. Try again; the same request will not create duplicate work.' : error.message);
  } finally {
    button.disabled = false;
    refresh();
  }
});

const editor = document.querySelector('#invoice-editor');
if (editor) {
  const collect = () => {
    const values = Object.fromEntries(new FormData(editor));
    values.items = Array.from(editor.querySelectorAll('.editor-good'), row => ({
      source_index:row.dataset.sourceIndex === '' ? null : Number(row.dataset.sourceIndex),
      ...Object.fromEntries(Array.from(row.querySelectorAll('[data-field]'), input => [input.dataset.field,input.value]))
    }));
    return values;
  };
  const initial = collect();
  const total = editor.elements.namedItem('total_value');
  let manualTotal = false, lastBody = '', requestId = '';
  total.addEventListener('input', () => { manualTotal = true; });
  const updateTotal = () => {
    manualTotal = false;
    if (['INDIA','JORDAN'].includes(editor.dataset.region)) { total.value = ''; return; }
    const rows = collect().items;
    total.value = rows.length && rows.every(row => row.quantity !== '' && row.unit_price !== '')
      ? String(Math.round(rows.reduce((sum,row) => sum + Math.round((Number(row.quantity)*Number(row.unit_price)+Number.EPSILON)*100)/100,0))) : '';
  };
  editor.addEventListener('input', event => {
    if (event.target.closest('.editor-good') && (!['INDIA','JORDAN'].includes(editor.dataset.region) || ['quantity','unit','unit_price'].includes(event.target.dataset.field))) updateTotal();
  });
  editor.addEventListener('click', event => {
    if (event.target.closest('.remove-goods')) { event.target.closest('.editor-good').remove(); updateTotal(); }
    if (event.target.closest('#add-goods')) {
      if (editor.querySelectorAll('.editor-good').length >= 200) { text('#editor-result','Use at most 200 goods rows.'); return; }
      document.querySelector('#editor-goods').append(document.querySelector('#goods-row-template').content.cloneNode(true));
      updateTotal();
    }
  });
  editor.addEventListener('submit', async event => {
    event.preventDefault();
    const current = collect();
    const changes = Object.fromEntries(Object.entries(current).filter(([key,value]) => JSON.stringify(value)!==JSON.stringify(initial[key])));
    if (!manualTotal) delete changes.total_value;
    if (!Object.keys(changes).length) { text('#editor-result','No changes to save.'); return; }
    const body = JSON.stringify(changes);
    if (body !== lastBody) { requestId = crypto.randomUUID(); lastBody = body; }
    const button = editor.querySelector('[type="submit"]'); button.disabled = true;
    text('#editor-result','Saving your changes…');
    try {
      const response = await fetch('/api/jobs/' + editor.dataset.jobId + '/edit', {method:'POST',cache:'no-store',
        signal:AbortSignal.timeout(15000),headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},
        body:JSON.stringify({request_id:requestId,attempt_id:Number(editor.dataset.attemptId),changes})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Changes could not be saved.');
      location.assign('/jobs/' + result.job_id);
    } catch (error) {
      text('#editor-result',error.name==='TimeoutError' || error.name==='TypeError' ? 'No response received. Try again; identical requests do not create duplicate invoices.' : error.message);
      button.disabled = false;
    }
  });
}

const settingsEditor = document.querySelector('#settings-editor');
function updateIntakeStatus(control) {
  const badge = document.querySelector('[data-intake-status="' + control.dataset.intakeControl + '"]');
  const enabled = control.value === 'true';
  badge.textContent = (enabled ? 'Enabled' : 'Disabled') + (control.value !== control.dataset.current ? ' · unsaved' : '');
  badge.className = 'badge' + (enabled ? ' state-completed' : '');
}
if (settingsEditor) settingsEditor.addEventListener('change',event => {
  if (event.target.matches('[data-intake-control]')) updateIntakeStatus(event.target);
});
function settingsChanges(form) {
  const changes = Object.fromEntries(new FormData(form));
  for (const kind of ['incoming','output']) {
    const root = form.querySelector('[data-folder-root="' + kind + '"]').value;
    if (root) {
      changes[kind + '_dir'] = root.replace(/[\\/]+$/, '') + '/bangladesh';
      changes['india_' + kind + '_dir'] = root.replace(/[\\/]+$/, '') + '/india';
      changes['jordan_' + kind + '_dir'] = root.replace(/[\\/]+$/, '') + '/jordan';
    }
  }
  changes.local_model = changes.local_model.trim() || null;
  changes.india_enabled = changes.india_enabled === 'true';
  changes.bangladesh_enabled = changes.bangladesh_enabled === 'true';
  changes.jordan_enabled = changes.jordan_enabled === 'true';
  for (const field of ['india_incoming_dir','india_output_dir','jordan_incoming_dir','jordan_output_dir']) changes[field] = changes[field].trim() || null;
  for (const field of ['scan_interval_seconds','vision_output_tokens','vision_context_tokens','vision_timeout_seconds']) changes[field] = Number(changes[field]);
  return changes;
}
const folderBrowser = document.querySelector('#folder-browser');
if (settingsEditor && folderBrowser) {
  let browsing;
  const useFolder = document.querySelector('#folder-use');
  const loadFolders = async path => {
    if (browsing) browsing.abort();
    const request = new AbortController(); browsing = request;
    useFolder.disabled = true; delete folderBrowser.dataset.path;
    text('#folder-browser-result','Loading folders…');
    document.querySelector('#folder-list').replaceChildren();
    try {
      const response = await fetch('/api/folders/browse',{method:'POST',cache:'no-store',signal:request.signal,
        headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},
        body:JSON.stringify({kind:folderBrowser.dataset.kind,path})});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'This folder could not be opened.');
      if (request.signal.aborted || !folderBrowser.open) return;
      folderBrowser.dataset.path = result.path; folderBrowser.dataset.name = result.name;
      document.querySelector('#folder-location').value = result.path;
      text('#folder-current',result.name);
      const up = document.querySelector('#folder-up');
      up.disabled = !result.parent; up.dataset.folderPath = result.parent || '';
      document.querySelector('#folder-locations').replaceChildren(new Option('Go to…',''),
        ...result.locations.map(location => new Option(location.name,location.path)));
      document.querySelector('#folder-list').replaceChildren(...result.directories.map(directory => {
        const item = document.createElement('button');
        item.type = 'button'; item.className = 'folder-entry';
        item.textContent = '▸ ' + directory.name; item.dataset.folderPath = directory.path;
        return item;
      }));
      text('#folder-browser-result',result.directories.length ? 'Open a subfolder, or use this folder.' : 'No subfolders. You can use this folder.');
      useFolder.disabled = false;
    } catch (error) {
      if (error.name !== 'AbortError') text('#folder-browser-result',error.message);
    }
  };
  settingsEditor.addEventListener('click',event => {
    const button = event.target.closest('[data-folder-kind]');
    if (!button || button.disabled) return;
    folderBrowser.dataset.kind = button.dataset.folderKind;
    folderBrowser.returnValue = '';
    text('#folder-browser-title',button.dataset.folderKind === 'incoming' ? 'Choose PDF intake folder' : 'Choose invoice output folder');
    settingsEditor.querySelector('[type="submit"]').disabled = true;
    folderBrowser.showModal();
    loadFolders(settingsEditor.querySelector('[data-folder-root="' + button.dataset.folderKind + '"]').value || null);
  });
  folderBrowser.addEventListener('click',event => {
    const directory = event.target.closest('[data-folder-path]');
    if (directory && !directory.disabled && directory.dataset.folderPath) loadFolders(directory.dataset.folderPath);
    if (event.target.closest('#folder-cancel')) folderBrowser.close();
  });
  document.querySelector('#folder-locations').addEventListener('change',event => {
    if (event.target.value) loadFolders(event.target.value);
  });
  document.querySelector('#folder-open').addEventListener('click',() => loadFolders(document.querySelector('#folder-location').value));
  document.querySelector('#folder-location').addEventListener('keydown',event => {
    if (event.key === 'Enter') { event.preventDefault(); loadFolders(event.target.value); }
  });
  useFolder.addEventListener('click',() => {
    if (!folderBrowser.dataset.path) return;
    settingsEditor.querySelector('[data-folder-root="' + folderBrowser.dataset.kind + '"]').value = folderBrowser.dataset.path;
    text('#' + folderBrowser.dataset.kind + '-folder-name',folderBrowser.dataset.name);
    folderBrowser.close('selected');
  });
  folderBrowser.addEventListener('close',() => {
    if (browsing) browsing.abort();
    settingsEditor.querySelector('[type="submit"]').disabled = false;
    text('#folder-picker-result',folderBrowser.returnValue === 'selected' ? 'Folder selected. Save settings to apply it.' : 'Selection cancelled. Your folders have not changed.');
  });
}
if (settingsEditor) settingsEditor.addEventListener('submit', async event => {
  event.preventDefault();
  const button = settingsEditor.querySelector('button[type="submit"]');
  if (button.disabled) return;
  const changes = settingsChanges(settingsEditor);
  if (['india','jordan'].some(country => Boolean(changes[country + '_incoming_dir']) !== Boolean(changes[country + '_output_dir']))) {
    text('#settings-result','Choose both parent folders before saving: PDF intake and invoice output.');
    return;
  }
  const signature = JSON.stringify(changes);
  if (settingsEditor.dataset.signature !== signature) {
    settingsEditor.dataset.requestId = crypto.randomUUID();
    settingsEditor.dataset.signature = signature;
  }
  button.disabled = true;
  text('#settings-result','Saving settings…');
  try {
    const response = await fetch('/api/settings', {method:'POST',cache:'no-store',signal:AbortSignal.timeout(15000),
      headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},
      body:JSON.stringify({request_id:settingsEditor.dataset.requestId,changes})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Settings could not be saved.');
    window.location.assign('/system?saved=1');
  } catch (error) {
    text('#settings-result',error.name === 'TimeoutError' || error.name === 'TypeError' ? 'No response received. Save again to check the same request safely.' : error.message);
  } finally { button.disabled = false; }
});

const pdfUpload = document.querySelector('#pdf-upload');
if (pdfUpload) {
  pdfUpload.addEventListener('submit', async event => {
    event.preventDefault();
    const feedback = document.querySelector('#upload-result');
    const button = pdfUpload.querySelector('button[type="submit"]');
    const file = pdfUpload.elements.namedItem('file').files[0];
    feedback.className = 'upload-result error';
    if (!file || !pdfUpload.elements.namedItem('region').value) {
      feedback.textContent = 'Choose one PDF and a country.'; return;
    }
    if (file.size > Number(pdfUpload.dataset.maxBytes)) {
      feedback.textContent = 'The PDF must be 100 MB or smaller.'; return;
    }
    button.disabled = true; button.textContent = 'Uploading…';
    feedback.className = 'upload-result'; feedback.textContent = 'Uploading your PDF…';
    try {
      const response = await fetch(pdfUpload.action, {method:'POST', cache:'no-store',
        signal:AbortSignal.timeout(120000), headers:{'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},
        body:new FormData(pdfUpload)});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'The PDF could not be uploaded.');
      feedback.className = 'upload-result success'; feedback.textContent = 'Uploaded. Opening the queue…';
      location.assign(result.jobs_url);
    } catch (error) {
      feedback.className = 'upload-result error';
      feedback.textContent = error.name === 'TimeoutError' || error.name === 'TypeError'
        ? 'No response received. Check the jobs list before retrying; existing files will not be overwritten.' : error.message;
    } finally { button.disabled = false; button.textContent = 'Upload PDF'; }
  });
}
