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
    text('#activity-detail', active ? active.stage + ' · ' + (active.stage_status || 'starting') + (active.last_observed_page ? ' · last observed page ' + active.last_observed_page : '') : 'The worker will claim the next queued PDF when running.');
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
