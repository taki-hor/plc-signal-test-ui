import {$, node, formatTime} from './dom.js';
import {get} from './api.js';
export async function refreshLogs() {
  try {
    const kind = $('log-kind').value, data = await get(`/api/logs?kind=${encodeURIComponent(kind)}`);
    const list = $('log-list'); list.replaceChildren();
    for (const entry of data.logs.slice(-150).reverse()) {
      const row = node('div','log-row'), detail = node('details'), summary = node('summary','',`${entry.result ?? ''} ${entry.test_name ?? entry.tag_name ?? ''} ${entry.error ?? ''}`);
      detail.append(summary,node('pre','',JSON.stringify(entry,null,2)));
      row.append(node('span','',formatTime(entry.timestamp)),node('span','event',entry.event),detail); list.append(row);
    }
    if (!data.logs.length) list.textContent = 'No entries yet.';
  } catch (error) { $('log-list').textContent = error.message; }
}
export function initLogger() {
  $('log-refresh').addEventListener('click',refreshLogs);
  $('log-kind').addEventListener('change',() => {
    const kind = $('log-kind').value;
    $('export-csv').href = `/api/logs/export?format=csv&kind=${encodeURIComponent(kind)}`;
    $('export-json').href = `/api/logs/export?format=json&kind=${encodeURIComponent(kind)}`;
    refreshLogs();
  });
}
