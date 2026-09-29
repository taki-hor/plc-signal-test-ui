let writeToken = null; // In-memory only: refresh and restart return to read-only.
let writeExpiry = 0;
export function modeEnabled() {
  if (writeToken && Date.now() >= writeExpiry) { writeToken = null; writeExpiry = 0; }
  return Boolean(writeToken);
}
export async function request(path, options = {}) {
  const headers = {'Accept': 'application/json', ...(options.body ? {'Content-Type': 'application/json'} : {}), ...options.headers};
  if (modeEnabled() && options.method === 'POST') headers['X-Write-Token'] = writeToken;
  let response;
  try { response = await fetch(path, {...options, headers, cache: 'no-store'}); }
  catch (error) { throw new Error(`Local backend connection failed: ${error.message}`); }
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    const error = new Error(data.error || data.detail || `HTTP ${response.status}`);
    error.detail = data.detail || '';
    error.status = response.status;
    throw error;
  }
  return data;
}
export const get = path => request(path);
export const post = (path, body = {}) => request(path, {method: 'POST', body: JSON.stringify(body)});
export async function enableMode() { const data = await post('/api/mode/enable'); writeToken = data.write_token; writeExpiry = Date.now() + data.expires_seconds * 1000; return data; }
export async function disableMode() { try { if (writeToken) await post('/api/mode/disable'); } finally { writeToken = null; writeExpiry = 0; } }

window.addEventListener('pagehide', () => { if (writeToken) fetch('/api/mode/disable', {method:'POST', headers:{'X-Write-Token':writeToken}, keepalive:true}).catch(() => {}); });
