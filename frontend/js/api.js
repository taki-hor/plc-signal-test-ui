let writeToken = null; // In-memory only: refresh and restart return to read-only.
let writeExpiry = 0;
export function modeEnabled() {
  if (writeToken && Date.now() >= writeExpiry) { writeToken = null; writeExpiry = 0; }
  return Boolean(writeToken);
}
export async function request(path, options = {}) {
  const requestToken = modeEnabled() ? writeToken : null;
  const headers = {'Accept': 'application/json', ...(options.body ? {'Content-Type': 'application/json'} : {}), ...options.headers};
  if (requestToken && (options.method === 'POST' || path === '/api/status')) headers['X-Write-Token'] = requestToken;
  let response;
  try { response = await fetch(path, {...options, headers, cache: 'no-store', signal: options.signal ?? AbortSignal.timeout(options.method === 'POST' ? 60000 : 10000)}); }
  catch (error) { throw new Error(`Local backend connection failed: ${error.message}`); }
  let data;
  try { data = await response.json(); } catch {
    if (response.ok) throw new Error('Local backend returned invalid JSON');
    data = {};
  }
  if (!response.ok) {
    if (response.status === 403 && writeToken === requestToken) { writeToken = null; writeExpiry = 0; }
    const error = new Error(data.error || data.detail || `HTTP ${response.status}`);
    error.detail = data.detail || '';
    error.status = response.status;
    error.writeDispatched = data.write_dispatched;
    throw error;
  }
  if (path === '/api/status' && data.write_mode_enabled === false && writeToken === requestToken) { writeToken = null; writeExpiry = 0; }
  return data;
}
export const get = path => request(path);
export const post = (path, body = {}) => request(path, {method: 'POST', body: JSON.stringify(body)});
export async function enableMode() { const data = await post('/api/mode/enable'); writeToken = data.write_token; writeExpiry = Date.now() + data.expires_seconds * 1000; return data; }
export async function disableMode() {
  const token = writeToken; writeToken = null; writeExpiry = 0;
  if (token) await request('/api/mode/disable', {method:'POST', headers:{'X-Write-Token':token}});
}

window.addEventListener('pagehide', () => { if (writeToken) fetch('/api/mode/disable', {method:'POST', headers:{'X-Write-Token':writeToken}, keepalive:true}).catch(() => {}); });
