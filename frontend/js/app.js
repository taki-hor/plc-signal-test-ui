import {$} from './dom.js';
import {get, modeEnabled} from './api.js';
import {renderStatus} from './dashboard.js';
import {setSignalData, setSignalHealth, initSignalEvents} from './signals.js';
import {updateControls, initControls} from './controls.js';
import {updateChecklist, initChecklist} from './command-checklist.js';
import {updateVerifier} from './verifier.js';
import {refreshLogs, initLogger} from './logger.js';
import {initRouter} from './router.js';
import {initWriteFeedback, updateWriteFeedback} from './write-feedback.js';
let tags = [], poll = null, status = null, busy = false, timer = null;
async function loadCatalog() {
  try {
    tags = (await get('/api/tags')).tags;
    setSignalData(tags, poll); updateControls(tags, poll, status); updateChecklist(tags, poll, status); updateWriteFeedback(tags, poll, status);
  } catch (error) { $('system-error').textContent = `Catalog: ${error.message}`; $('system-error').classList.remove('hidden'); }
  try { const cases = (await get('/api/test/cases')).tests; updateVerifier(cases, status); updateChecklist(null, null, status, cases); updateWriteFeedback(null,null,status,cases); } catch (error) { $('test-list').textContent = error.message; }
}
function renderHealth(nextStatus) {
  status = nextStatus; setSignalHealth(status); renderStatus(status, modeEnabled());
  updateControls(null, poll, status); updateVerifier(null, status); updateChecklist(null, poll, status);
  updateWriteFeedback(null,poll,status);
}
function refreshFailed(message) {
  renderHealth({...status, supplier_api_connected:false, data_fresh:false, plc_mode:'UNKNOWN', last_error:message});
}
async function refresh() {
  if (busy) return; busy = true;
  const watchdog = setTimeout(() => refreshFailed('Refresh overdue; live data cannot be verified.'), status?.stale_after_ms ?? 3000);
  try {
    const nextPoll = await get('/api/signals');
    const nextStatus = await get('/api/status');
    poll = nextPoll; setSignalData(null, poll); renderHealth(nextStatus);
  } catch (error) { refreshFailed(`Refresh failed: ${error.message}${error.detail ? ` · ${error.detail}` : ''}`); }
  finally { clearTimeout(watchdog); busy = false; }
}
function modeChanged() { if (status) renderStatus(status, modeEnabled()); updateControls(null,poll,status); updateVerifier(null,status); updateChecklist(null,poll,status); refreshLogs(); }
async function start() {
  initSignalEvents(); initControls(modeChanged); initChecklist(modeChanged); initLogger(); initWriteFeedback();
  initRouter(page => { if (page === 'logs') refreshLogs(); });
  $('refresh-btn').addEventListener('click', async () => { await loadCatalog(); await refresh(); refreshLogs(); });
  await loadCatalog(); await refresh(); await refreshLogs();
  const interval = Math.max(250, status?.poll_interval_ms ?? 1000);
  timer = setInterval(refresh, interval);
}
start();
