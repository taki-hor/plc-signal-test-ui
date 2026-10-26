import {setApiChecks, renderApiSummary} from './api-checks.js';
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
let tags = [], poll = null, status = null, busy = false, timer = null, catalogLoaded = false, catalogLoading = false;
async function loadCatalog() {
  if (catalogLoading) return;
  catalogLoading = true;
  try {
    tags = (await get('/api/tags')).tags; catalogLoaded = true;
    setSignalData(tags, poll); updateControls(tags, poll, status); updateChecklist(tags, poll, status, null, {loaded:true, error:null}); updateWriteFeedback(tags, poll, status); updateVerifier(null, status, poll, tags);
  } catch (error) { $('system-error').textContent = `Catalog: ${error.message}`; $('system-error').classList.remove('hidden'); updateChecklist(null, poll, status, null, {loaded:catalogLoaded, error:error.message}); }
  try { const cases = (await get('/api/test/cases')).tests; updateVerifier(cases, status, poll, tags); updateChecklist(null, null, status, cases); updateWriteFeedback(null,null,status,cases); } catch (error) { $('test-list').textContent = error.message; }
  finally { catalogLoading = false; }
}
function renderHealth(nextStatus) {
  status = nextStatus; setSignalHealth(status); renderStatus(status, modeEnabled());
  updateControls(null, poll, status); updateChecklist(null, poll, status); updateVerifier(null, status, poll, tags);
  updateWriteFeedback(null,poll,status); renderApiSummary(status,tags);
}
let checkBusy=false;
async function refreshApiChecks() {
  if (checkBusy || !status?.api_address) return;
  checkBusy=true; const context={mode:status.mode,api_address:status.api_address};
  try {
    const data=await get('/api/checks');
    if (context.mode!==status?.mode || context.api_address!==status?.api_address) return;
    setApiChecks(data,context,tags);
  } catch { setApiChecks({records:[],error:'API check results are unavailable. Use Refresh now to retry.'},context,tags); }
  finally {
    if (context.mode!==status?.mode || context.api_address!==status?.api_address) setApiChecks({records:[]},status,tags);
    checkBusy=false; updateControls(null,poll,status); updateChecklist(null,poll,status); updateVerifier(null,status,poll,tags); updateWriteFeedback(null,poll,status);
  }
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
    if (!catalogLoaded && nextStatus.supplier_api_connected) loadCatalog();
  } catch (error) { refreshFailed(`Refresh failed: ${error.message}${error.detail ? ` · ${error.detail}` : ''}`); }
  finally { clearTimeout(watchdog); busy = false; refreshApiChecks(); }
}
function modeChanged() { if (status) renderStatus(status, modeEnabled()); updateControls(null,poll,status); updateChecklist(null,poll,status); updateVerifier(null,status,poll,tags); refreshLogs(); }
async function start() {
  initSignalEvents(); initControls(modeChanged); initChecklist(modeChanged); initLogger(); initWriteFeedback();
  window.addEventListener('signal-results-changed',()=>renderHealth(status));
  initRouter(page => { $('shared-write-signals').classList.toggle('hidden',!['verify','commands','write'].includes(page)); if (page === 'logs') refreshLogs(); });
  $('refresh-btn').addEventListener('click', async () => { await loadCatalog(); await refresh(); refreshLogs(); });
  await loadCatalog(); await refresh(); await refreshLogs();
  const interval = Math.max(250, status?.poll_interval_ms ?? 1000);
  timer = setInterval(refresh, interval);
}
start();
