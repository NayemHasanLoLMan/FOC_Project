'use strict';
const text = (selector, value) => document.querySelectorAll(selector).forEach(node => { node.textContent = value; });
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
    text('#web-status', 'Web available');
    text('#queue-state', status.queue.paused ? 'Processing paused' : 'Ready to process');
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
      text('[data-health="' + name + '"]', health.state);
      text('[data-component-error="' + name + '"]', health.error || '');
      text('[data-heartbeat="' + name + '"]', health.heartbeat_at ? 'Heartbeat ' + new Date(health.heartbeat_at).toLocaleString() + ' · ' + seconds(health.age_seconds) + ' ago' : 'No heartbeat recorded');
    }
    const active = status.active;
    text('#activity-title', active ? 'Job #' + active.job_id : 'No active conversion');
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
      text('#detail-state', current.status_label || current.state.replaceAll('_', ' '));
      if (detail.dataset.displayState !== current.state && current.state === 'completed' && !new URLSearchParams(location.search).has('attempt')) {
        location.reload();
      }
      detail.dataset.displayState = current.state;
    }
  } catch (error) {
    text('#web-status', 'Status unavailable');
    text('#refreshed', 'Refresh failed; displayed information may be stale.');
  } finally { refreshing = false; }
}
let checkingModel = false;
async function refreshModel() {
  if (checkingModel || document.hidden) return;
  checkingModel = true;
  try { const result = await getJSON('/api/ollama'); text('[data-health="ollama"]', result.state.replaceAll('_', ' ')); }
  catch (error) { text('[data-health="ollama"]', 'unknown'); }
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
    const rows = collect().items;
    total.value = rows.length && rows.every(row => row.quantity !== '' && row.unit_price !== '')
      ? String(Math.round(rows.reduce((sum,row) => sum + Math.round((Number(row.quantity)*Number(row.unit_price)+Number.EPSILON)*100)/100,0))) : '';
  };
  editor.addEventListener('input', event => { if (event.target.closest('.editor-good')) updateTotal(); });
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
    if (!manualTotal && changes.items) delete changes.total_value;
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
