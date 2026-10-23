import {$, node, setText, formatTime} from './dom.js';
export function renderStatus(status, writeMode) {
  setText('api-state', status.supplier_api_connected ? 'CONNECTED' : 'DISCONNECTED');
  $('api-state').className = status.supplier_api_connected ? 'good' : 'bad';
  setText('plc-mode', status.plc_mode);
  $('plc-mode').className = status.plc_mode === 'REMOTE' ? 'good' : 'warn';
  setText('freshness', status.data_fresh ? 'FRESH' : status.supplier_timestamp ? 'STALE' : 'NO DATA');
  $('freshness').className = status.data_fresh ? 'good' : 'warn';
  setText('tag-counts', `${status.tags_ok ?? '—'} / ${status.tags_failed ?? '—'}`);
  setText('api-address', status.api_address);
  setText('last-api', formatTime(status.last_successful_request));
  setText('poll-time', formatTime(status.supplier_timestamp));
  setText('data-age', status.data_age_ms == null ? 'UNKNOWN' : `${(status.data_age_ms / 1000).toFixed(1)} s`);
  const offset = status.timestamp_offset_seconds ?? 0;
  $('clock-offset-detail').classList.toggle('hidden', offset === 0);
  setText('clock-offset', `${offset > 0 ? '+' : ''}${offset} s`);
  const healthy = status.supplier_api_connected && status.data_fresh && status.plc_mode === 'REMOTE';
  const badge = $('global-health'); badge.textContent = healthy ? (writeMode ? 'READY TO TEST' : 'MONITORING READY') : status.supplier_api_connected ? 'ATTENTION REQUIRED' : 'CONNECTION ERROR';
  badge.className = `pill ${healthy ? '' : status.supplier_api_connected ? 'amber' : 'red'}`;
  $('mock-badge').classList.toggle('hidden', status.mode !== 'MOCK');
  const error = $('system-error');
  error.textContent = status.last_error || (status.plc_mode !== 'REMOTE' ? 'PLC is not in Remote/API mode. Write commands are disabled.' : !status.data_fresh ? 'Supplier poll data is stale, incomplete or unavailable. Write commands are disabled.' : '');
  error.classList.toggle('hidden', !error.textContent);
  const catalog = $('catalog-warning');
  const warnings = status.catalog_warnings || [];
  setText('catalog-warning-summary',`${warnings.length} catalog ${warnings.length === 1 ? 'warning' : 'warnings'} — review details`);
  setText('catalog-warning-detail',warnings.map(w => w.message).join('\n'));
  catalog.classList.toggle('hidden', !warnings.length);
  $('write-banner').className = `write-mode-control ${writeMode ? 'enabled' : 'readonly'}`;
  setText('write-mode-state',writeMode ? 'WRITE MODE ON' : 'WRITE MODE OFF');
  setText('write-banner-title', writeMode ? 'WRITE TEST MODE ENABLED' : 'READ-ONLY MODE');
  setText('write-banner-note', writeMode ? 'Manual commands require confirmation. Mode expires after 30 minutes.' : 'Monitoring is active. Physical commands are locked.');
  $('mode-btn').title = $('write-banner-note').textContent;
  setText('mode-btn', writeMode ? 'Disable write mode' : 'Enable write test mode');
  const checks = [['Write test mode', writeMode], ['API connected', status.supplier_api_connected], ['Data fresh', status.data_fresh], ['PLC Remote', status.plc_mode === 'REMOTE']];
  const open = checks.every(([, ok]) => ok);
  for (const gate of document.querySelectorAll('[data-gate]')) {
    gate.className = `write-gate ${open ? 'open' : 'locked'}`;
    gate.replaceChildren(node('strong', '', open ? 'WRITES AVAILABLE' : 'WRITES LOCKED'), ...checks.map(([label, ok]) => node('span', `gate-check${ok ? ' ok' : ''}`, label)));
  }
  return healthy;
}
