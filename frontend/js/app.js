import {$} from './dom.js';
import {get, modeEnabled} from './api.js';
import {renderStatus} from './dashboard.js';
import {setSignalData, setSignalHealth, initSignalEvents} from './signals.js';
import {updateControls, initControls} from './controls.js';
import {updateVerifier} from './verifier.js';
import {refreshLogs, initLogger} from './logger.js';
let tags = [], poll = null, status = null, busy = false, timer = null;
async function loadCatalog() {
  try {
    tags = (await get('/api/tags')).tags;
    setSignalData(tags, poll); updateControls(tags, poll, status);
  } catch (error) { $('system-error').textContent = `Catalog: ${error.message}`; $('system-error').classList.remove('hidden'); }
  try { updateVerifier((await get('/api/test/cases')).tests, status); } catch (error) { $('test-list').textContent = error.message; }
}
async function refresh() {
  if (busy) return; busy = true;
  try { poll = await get('/api/signals'); setSignalData(null, poll); }
  catch (error) { $('system-error').textContent = `Poll failed: ${error.message}${error.detail ? ` · ${error.detail}` : ''}`; $('system-error').classList.remove('hidden'); }
  try {
    status = await get('/api/status'); setSignalHealth(status); renderStatus(status, modeEnabled());
    updateControls(null, poll, status); updateVerifier(null, status);
  } catch (error) { $('system-error').textContent = error.message; $('system-error').classList.remove('hidden'); }
  busy = false;
}
function modeChanged() { if (status) renderStatus(status, modeEnabled()); updateControls(null,poll,status); updateVerifier(null,status); refreshLogs(); }
async function start() {
  initSignalEvents(); initControls(modeChanged); initLogger();
  $('refresh-btn').addEventListener('click', async () => { await loadCatalog(); await refresh(); refreshLogs(); });
  await loadCatalog(); await refresh(); await refreshLogs();
  const interval = Math.max(250, status?.poll_interval_ms ?? 1000);
  timer = setInterval(refresh, interval);
}
start();
