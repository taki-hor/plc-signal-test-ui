import {$, node, groupFor, fillGroups, valueText} from './dom.js';
import {post, modeEnabled} from './api.js';
import {confirmWrite, validate} from './controls.js';

let tags = [], poll = null, status = null, cases = [], selected = null;
let records = [], storageKey = null, busy = false, draftNote = '', changed = () => {};
const rows = new Map();
const now = () => Date.now();
function tag() { return tags.find(t => t.tag_name === selected); }
function latest(t = tag()) {
  if (!t) return null;
  for (let i = records.length - 1; i >= 0; i--) {
    if (records[i].tag_name === t.tag_name && records[i].address === t.device_address) return records[i];
  }
  return null;
}
function complete(r) { return Boolean(r?.oneAcceptedAt && r.zeroAcceptedAt && r.zeroSeenAt); }
function needsClear(r) { return Boolean(r?.oneRequestedAt && !r.oneRejectedAt && !r.zeroSeenAt); }
function pending() { return records.filter(r => needsClear(r) && !r.holdOneAt); }
function held() { return records.filter(r => needsClear(r) && r.holdOneAt); }
function result(r) { return !r ? 'NOT TESTED' : r.issueAt ? 'ISSUE' : r.oneRejectedAt ? 'BLOCKED' : complete(r) ? 'API CYCLE COMPLETE' : r.holdOneAt ? 'KEPT AT 1' : r.oneRequestedAt && !r.zeroSeenAt ? (/door/i.test(r.tag_name) || !r.oneAcceptedAt ? 'NEEDS 0' : 'CLEAR / KEEP 1') : 'IN PROGRESS'; }
function elapsed(ms) { return `${String(Math.floor(ms / 60000)).padStart(2, '0')}:${((ms % 60000) / 1000).toFixed(1).padStart(4, '0')}`; }
function feedbackTimer(r) {
  if (!r?.oneRequestedAt) return '00:00.0';
  if (!['SENDING','WAITING','CONFIRMED'].includes(r.feedbackState)) return '—';
  return elapsed((r.feedbackStoppedAt ?? now()) - r.oneRequestedAt);
}
function stopFeedback(r, state, detail = {}) {
  r.feedbackState = state; r.feedbackStoppedAt = now();
  if (state === 'CONFIRMED') r.feedback_elapsed_ms = r.feedbackStoppedAt - r.oneRequestedAt;
  event(r, `Completion feedback: ${state}`, {...detail, feedback_elapsed_ms:r.feedback_elapsed_ms ?? null});
}
function persist() {
  if (!storageKey) return;
  try { localStorage.setItem(storageKey, JSON.stringify(records)); }
  catch { $('bool-storage-warning').textContent = 'This browser could not save the checklist. Export the record before leaving this page.'; $('bool-storage-warning').classList.remove('hidden'); }
}
function snapshot(r) {
  return {supplier_timestamp:poll?.timestamp, command_value:poll?.[r.tag_name], Remote:poll?.Remote, Local:poll?.Local,
          feedback_tag:r.feedback_tag, feedback_value:r.feedback_tag ? poll?.[r.feedback_tag] : null, feedback_result:r.feedbackState};
}
function event(r, action, detail = {}) {
  r.events.push({at:new Date().toISOString(), elapsed_ms:now() - r.startedAt, since_send_1_ms:r.oneRequestedAt ? now() - r.oneRequestedAt : null, action, ...snapshot(r), ...detail});
  persist();
}
function finish(r) {
  if (!r.finishedAt && (complete(r) || (r.issueAt && r.zeroSeenAt))) {
    r.finishedAt = now(); event(r, r.issueAt ? 'Issue recorded; clear verified' : 'API cycle complete; physical result requires operator observation');
  }
}
function create(t) {
  const reference = cases.find(c => c.command_tag === t.tag_name && c.command_value === 1 && !c.requires_confirmation);
  const r = {id:crypto.randomUUID(), tag_name:t.tag_name, address:t.device_address, startedAt:now(), note:draftNote,
             feedback_tag:reference?.feedback_tag ?? null, events:[]};
  records.push(r); event(r, 'Checklist started'); return r;
}
function healthy() { return modeEnabled() && status?.supplier_api_connected && status?.data_fresh && status?.plc_mode === 'REMOTE'; }
function canSend(value) {
  const t = tag(), r = latest();
  if (!t || busy || !healthy()) return false;
  if (pending().some(p => p !== r) && !(value === 0 && needsClear(r))) return false;
  if (value === 1 && (poll?.[t.tag_name] !== 0 || (r?.oneRequestedAt && !r.oneRejectedAt) || r?.issueAt || (r?.finishedAt && !r.oneRejectedAt))) return false;
  if (value === 0 && r?.zeroSeenAt) return false;
  try { validate(t, String(value)); return true; } catch { return false; }
}
function canKeep() {
  const t = tag(), r = latest(), stamp = Date.parse(status?.supplier_timestamp_utc);
  return Boolean(t && !/door/i.test(t.tag_name) && r?.oneAcceptedAt && !r.holdOneAt && !r.zeroAcceptedAt && !busy && healthy() &&
    poll?.timestamp === status.supplier_timestamp && poll[t.tag_name] === 1 && stamp > Date.parse(r.oneServerAt) && stamp > Date.parse(r.oneBaselineUtc) && stamp > Date.parse(r.oneCommandBaselineUtc));
}
function select(name) {
  selected = name; draftNote = latest()?.note ?? '';
  $('bool-notes').value = draftNote; render();
}
function buildList() {
  fillGroups($('bool-group'), tags); rows.clear(); $('bool-list').replaceChildren();
  for (const t of tags) {
    const button = node('button', 'bool-tag'); button.type = 'button'; button.dataset.commandTag = t.tag_name;
    const meta = node('span', 'bool-tag-meta'), current = node('span'), progress = node('span');
    meta.append(current, progress); button.append(node('strong', '', t.tag_name), node('small', '', t.description), meta);
    button.addEventListener('click', () => { if (!busy) select(t.tag_name); });
    $('bool-list').append(button); rows.set(t.tag_name, {button, current, progress});
  }
}
function writeHint(r, active) {
  if (!modeEnabled()) return 'Read-only: enable write test mode to send.';
  if (busy) return 'Write request in progress.';
  if (!status?.supplier_api_connected || !status?.data_fresh) return 'Fresh API data is required to send.';
  if (status.plc_mode !== 'REMOTE') return 'PLC Remote/API mode is required to send.';
  const other = active.find(a => a !== r);
  if (other) return needsClear(r) ? `Only clearing this command to 0 is available while ${other.tag_name} is pending.` : `Clear ${other.tag_name} to 0, or explicitly keep a non-door state at 1, before another command.`;
  if ((r?.zeroAcceptedAt && !r.zeroSeenAt && !Number.isFinite(Date.parse(r.zeroCommandBaselineUtc))) ||
      (r?.oneAcceptedAt && !r.zeroAcceptedAt && !r.holdOneAt && !Number.isFinite(Date.parse(r.oneCommandBaselineUtc))))
    return 'Readback cannot be verified: the receipt lacks a final pre-write timestamp. Update/restart the backend; check state before resending 0.';
  if (r?.holdOneAt && !r.zeroSeenAt) return 'Kept at 1. Other tests are available; send 0 when this state should end.';
  if (active.length) return /door/i.test(r?.tag_name) ? 'Command 1 is pending. After movement finishes, send 0 to release the other commands.' : 'Choose the end state: send 0, or explicitly Keep at 1 once its later readback is 1.';
  if (r?.finishedAt && !r.oneRejectedAt) return 'Cycle recorded. Choose New attempt to send 1 again.';
  return '';
}
function render() {
  const t = tag(), r = latest(), query = $('bool-search').value.trim().toLowerCase(), group = $('bool-group').value, filter = $('bool-filter').value;
  let visible = 0, done = 0;
  for (const item of tags) {
    const row = rows.get(item.tag_name), record = latest(item), isDone = complete(record) && !record.issueAt;
    if (isDone) done++;
    const matches = [item.tag_name, item.description, item.device_address].some(v => v.toLowerCase().includes(query)) &&
      (group === 'all' || groupFor(item) === group) && (filter === 'all' || (filter === 'complete' ? isDone : !isDone));
    row.button.classList.toggle('hidden', !matches); if (matches) visible++;
    row.button.classList.toggle('selected', selected === item.tag_name); row.button.setAttribute('aria-pressed', String(selected === item.tag_name));
    row.button.disabled = busy; row.current.textContent = `Value ${valueText(poll?.[item.tag_name])}`; row.progress.textContent = row.button.dataset.result = result(record);
  }
  $('bool-progress').textContent = `${done} / ${tags.length} API cycles complete · ${held().length} kept at 1 · ${visible} shown`;
  const open = pending().length + held().length;
  $('nav-commands-badge').textContent = open ? `${open} open` : `${done}/${tags.length}`; $('nav-commands-badge').classList.toggle('amber', open > 0);
  $('bool-name').textContent = t?.tag_name ?? 'Select a command'; $('bool-description').textContent = t?.description ?? 'Numeric setpoints are on the Value write page.';
  $('bool-value').textContent = valueText(t ? poll?.[t.tag_name] : null); $('bool-address').textContent = t?.device_address ?? '—';
  const reference = r?.feedback_tag ?? cases.find(c => c.command_tag === t?.tag_name && c.command_value === 1 && !c.requires_confirmation)?.feedback_tag;
  $('bool-feedback').textContent = !t ? '' : reference ? `Configured feedback reference: ${reference} = ${valueText(poll?.[reference])}. Record physical observations in your notes.` : 'No confirmed feedback mapping is assumed. Record physical observations below.';
  const active = pending(); $('bool-pending').textContent = active.length ? `Checklist commands awaiting a verified 0: ${active.map(a => `${a.tag_name} (${a.address})`).join(', ')}. Select the command to clear it; non-door states can explicitly be kept at 1.` : '';
  $('bool-pending').classList.toggle('hidden', !active.length);
  const maintained = held(); $('bool-held').textContent = maintained.length ? `Operator chose Keep at 1: ${maintained.map(a => `${a.tag_name} (${a.address}) · current ${valueText(poll?.[a.tag_name])}`).join('; ')}. Clear each when finished; these decisions do not re-send or enforce 1.` : '';
  $('bool-held').classList.toggle('hidden', !maintained.length);
  $('bool-keep').disabled = !canKeep();
  const hint = writeHint(r, active); if ($('bool-write-hint').textContent !== hint) $('bool-write-hint').textContent = hint;
  $('bool-one').disabled = !canSend(1); $('bool-zero').disabled = !canSend(0);
  for (const [id, verified, label] of [['bool-sent-one',r?.oneAcceptedAt,'API accepted 1'],['bool-sent-zero',r?.zeroAcceptedAt,'API accepted 0'],['bool-read-zero',r?.zeroSeenAt,'Later poll confirmed 0']]) {
    $(id).textContent = `${verified ? '✓' : '—'} ${label}`; $(id).dataset.verified = String(Boolean(verified));
  }
  $('bool-notes').disabled = !t || busy;
  if (document.activeElement !== $('bool-notes')) $('bool-notes').value = r?.note ?? draftNote;
  $('bool-issue').disabled = !r || busy; $('bool-new').disabled = !r || busy || needsClear(r) || (!r.oneRequestedAt && !r.zeroAcceptedAt && !r.issueAt);
  $('bool-result').textContent = result(r); $('bool-result').className = `pill ${complete(r) && !r.issueAt ? '' : 'amber'}`;
  $('bool-timer').textContent = feedbackTimer(r);
  $('bool-completion').textContent = r?.feedbackState ?? (r?.oneRequestedAt ? 'NOT RECORDED' : 'NOT STARTED');
  $('bool-api-latency').textContent = `API response · 1: ${r?.oneApiElapsedMs ?? '—'} ms · 0: ${r?.zeroApiElapsedMs ?? '—'} ms`;
  const list = $('bool-log'), logVersion = `${r?.id ?? ''}:${r?.events.length ?? 0}`;
  if (list.dataset.version !== logVersion) {
    list.dataset.version = logVersion; list.replaceChildren();
    for (const e of r?.events ?? []) {
      const li = node('li'), time = node('time', '', `${e.since_send_1_ms != null ? '1+' + elapsed(e.since_send_1_ms) : 'Attempt+' + elapsed(e.elapsed_ms)} · ${new Date(e.at).toLocaleTimeString()}`);
      li.append(time, node('div', '', e.action));
      const details = node('details'); details.append(node('summary', '', 'Read snapshot / details'), node('pre', '', JSON.stringify(e, null, 2))); li.append(details); list.append(li);
    }
    if (!r?.events.length) list.append(node('li', '', 'No command sent.'));
  }
}
async function send(value) {
  if (!canSend(value)) return;
  const selectedTag = tag();
  confirmWrite(`Confirm checklist write ${value}`, [['Signal',selectedTag.tag_name],['PLC address',selectedTag.device_address],['Current value',valueText(poll?.[selectedTag.tag_name])],['New value',value],['Operation','One write only. No automatic pulse, clear or retry.']], async () => {
    if (!canSend(value) || tag()?.device_address !== selectedTag.device_address) return;
    const r = !latest() || (value === 1 && latest().oneRejectedAt) ? create(selectedTag) : latest(), started = now();
    if (value === 1) Object.assign(r, {oneRequestedAt:started, oneBaselineUtc:status?.supplier_timestamp_utc, oneCommandBaselineUtc:null, zeroCommandBaselineUtc:null, feedbackState:'SENDING', feedbackStoppedAt:null, feedback_elapsed_ms:null, zeroAcceptedAt:null, zeroServerAt:null, zeroSeenAt:null});
    if (value === 0) {
      r.zeroBaselineUtc = status?.supplier_timestamp_utc;
      if (r.feedbackState === 'WAITING') r.feedbackState = 'CLEARING';
    }
    event(r, `Write ${value} requested`, {value, zero_baseline_supplier_timestamp_utc:value === 0 ? r.zeroBaselineUtc : null}); busy = true; render();
    try {
      const response = await post('/api/write', {tag_name:selectedTag.tag_name, value});
      if (response.written !== true) throw new Error('Supplier did not confirm written=true; inspect the physical state before retrying.');
      let completionResult = null;
      if (value === 1) {
        r.oneAcceptedAt = now(); r.oneServerAt = response.console_accepted_at; r.oneApiElapsedMs = now() - started;
        r.oneCommandBaselineUtc = response.console_command_baseline_utc ?? null;
        const baseline = response.console_feedback_baseline;
        r.feedback_tag = baseline?.feedback_tag ?? null; r.feedback_expected = baseline?.expected_feedback;
        r.feedback_baseline_utc = baseline?.supplier_timestamp_utc; r.feedback_before = baseline?.value_before;
        r.feedbackState = 'WAITING';
        if (!baseline) completionResult = 'NO CONFIRMED MAPPING';
        else if (baseline.value_before === baseline.expected_feedback) completionResult = 'ALREADY SET BEFORE WRITE';
      } else {
        r.zeroAcceptedAt = now(); r.zeroServerAt = response.console_accepted_at; r.zeroSeenAt = null; r.zeroApiElapsedMs = now() - started;
        r.zeroCommandBaselineUtc = response.console_command_baseline_utc ?? null;
        if (r.feedbackState === 'CLEARING') completionResult = 'CLEARED BEFORE COMPLETION';
      }
      event(r, `API accepted ${value}`, {value, http_status:200, written:true, api_elapsed_ms:now() - started, console_accepted_at:response.console_accepted_at, console_command_baseline_utc:response.console_command_baseline_utc ?? null, feedback_baseline:response.console_feedback_baseline});
      if (completionResult) stopFeedback(r, completionResult);
    } catch (error) {
      if (value === 1 && error.writeDispatched === false) { r.oneRejectedAt = now(); r.finishedAt = now(); }
      event(r, `Write ${value} ${error.writeDispatched === false ? 'blocked before dispatch' : 'outcome requires review'}: ${error.message}`, {value, http_status:error.status ?? null, write_dispatched:error.writeDispatched, api_elapsed_ms:now() - started});
      if (value === 1) stopFeedback(r, error.writeDispatched === false ? 'BLOCKED' : 'OUTCOME UNKNOWN');
      if (value === 0 && r.feedbackState === 'CLEARING') {
        if (error.writeDispatched === false) { r.feedbackState = 'WAITING'; event(r, 'Clear blocked before dispatch; completion observation continues'); }
        else stopFeedback(r, 'CLEAR OUTCOME UNKNOWN');
      }
    } finally { busy = false; persist(); render(); changed(); }
  });
}
export function updateChecklist(nextTags, nextPoll, nextStatus, nextCases) {
  if (nextTags) { tags = nextTags.filter(t => t.read_write === 'W' && t.data_type === 'Bool').sort((a,b) => a.tag_name.localeCompare(b.tag_name)); buildList(); }
  if (nextPoll) poll = nextPoll;
  if (nextStatus) status = nextStatus;
  if (nextCases) cases = nextCases;
  if (status?.mode && status?.api_address) {
    const key = `plc-command-checklist:v1:${status.mode}:${status.api_address}`;
    if (key !== storageKey) {
      storageKey = key; records = [];
      try {
        const saved = JSON.parse(localStorage.getItem(key) ?? '[]');
        if (Array.isArray(saved)) records = saved.filter(r => r && typeof r.tag_name === 'string' && typeof r.address === 'string' && Number.isFinite(r.startedAt) && Array.isArray(r.events) && r.events.every(e => e && typeof e.action === 'string' && Number.isFinite(e.elapsed_ms)));
        for (const r of records) {
          if (r.feedbackState === 'SENDING' || r.feedbackState === 'CLEARING') stopFeedback(r, r.feedbackState === 'SENDING' ? 'OUTCOME UNKNOWN' : 'CLEAR OUTCOME UNKNOWN', {reason:'Page reloaded before request outcome was recorded'});
          else if (r.feedbackState === 'WAITING') stopFeedback(r, 'MONITORING INTERRUPTED', {reason:'Page reloaded before completion was observed'});
          const rejected = !r.oneAcceptedAt && r.events.find(e => e.http_status === 403 && e.action === 'Write 1 outcome requires review: WRITE TEST MODE is disabled or expired');
          if (rejected && !r.oneRejectedAt) { r.oneRejectedAt = Date.parse(rejected.at); r.feedbackState = 'BLOCKED'; event(r, 'Recovered historical authorization rejection; no clear required'); }
        }
      } catch { $('bool-storage-warning').textContent = 'Saved checklist could not be read. Export records regularly.'; $('bool-storage-warning').classList.remove('hidden'); }
    }
  }
  for (const r of records) {
    if (r.feedbackState !== 'WAITING') continue;
    if (!status?.data_fresh || !status.supplier_api_connected || status.plc_mode !== 'REMOTE') { stopFeedback(r, 'MONITORING INTERRUPTED'); continue; }
    const stamp = Date.parse(status.supplier_timestamp_utc);
    if (poll?.timestamp === status.supplier_timestamp && stamp > Date.parse(r.oneServerAt) && stamp > Date.parse(r.feedback_baseline_utc) && poll[r.feedback_tag] === r.feedback_expected) {
      stopFeedback(r, 'CONFIRMED', {supplier_timestamp_utc:status.supplier_timestamp_utc, expected_feedback:r.feedback_expected});
    }
  }
  if (poll && status?.data_fresh && status.supplier_api_connected && poll.timestamp === status.supplier_timestamp) {
    const stamp = Date.parse(status.supplier_timestamp_utc);
    for (const r of records) {
      if (r.zeroAcceptedAt && !r.zeroSeenAt && poll[r.tag_name] === 0 && Number.isFinite(stamp) && stamp > Date.parse(r.zeroServerAt) && stamp > Date.parse(r.zeroBaselineUtc) && stamp > Date.parse(r.zeroCommandBaselineUtc)) {
        r.zeroSeenAt = now(); event(r, 'Later supplier poll verified command 0', {supplier_timestamp_utc:status.supplier_timestamp_utc}); finish(r);
      }
    }
  }
  render();
}
function download(format) {
  const summary = tags.map(t => ({tag_name:t.tag_name, address:t.device_address, result:result(latest(t)), current_value:poll?.[t.tag_name] ?? null}));
  let content, type;
  if (format === 'json') { content = JSON.stringify({exported_at:new Date().toISOString(), mode:status?.mode, api_address:status?.api_address, checklist:summary, attempts:records}, null, 2); type = 'application/json'; }
  else {
    const columns = ['tag_name','address','attempt_id','result','at','elapsed_ms','since_send_1_ms','feedback_result','feedback_elapsed_ms','action','value','api_elapsed_ms','http_status','written','console_accepted_at','console_command_baseline_utc','supplier_timestamp_utc','zero_baseline_supplier_timestamp_utc','Remote','Local','command_value','feedback_tag','feedback_value','supplier_timestamp','note'];
    const entries = records.flatMap(r => r.events.map(e => ({tag_name:r.tag_name,address:r.address,attempt_id:r.id,result:result(r),note:r.note,...e})));
    for (const item of summary) if (!latest(tags.find(t => t.tag_name === item.tag_name))) entries.push({...item, action:'Not tested'});
    const cell = value => { let s = String(value ?? ''); if (typeof value === 'string' && /^[=+@\-\t\r]/.test(s)) s = "'" + s; return '"' + s.replaceAll('"','""') + '"'; };
    content = [columns.join(','), ...entries.map(e => columns.map(k => cell(e[k])).join(','))].join('\r\n'); type = 'text/csv';
  }
  const url = URL.createObjectURL(new Blob([content], {type})), link = document.createElement('a'); link.href = url; link.download = `plc-command-checklist-${new Date().toISOString().slice(0,10)}.${format}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function initChecklist(onChange) {
  changed = onChange;
  window.addEventListener('pagehide', () => {
    for (const r of records) {
      if (r.feedbackState === 'WAITING') stopFeedback(r, 'MONITORING INTERRUPTED', {reason:'Page left before completion was observed'});
    }
  });
  for (const id of ['bool-search','bool-group','bool-filter']) $(id).addEventListener('input', render);
  $('bool-one').addEventListener('click', () => send(1)); $('bool-zero').addEventListener('click', () => send(0));
  $('bool-notes').addEventListener('input', () => { if (!tag()) return; draftNote = $('bool-notes').value; const r = latest() ?? create(tag()); r.note = draftNote; persist(); });
  $('bool-notes').addEventListener('change', () => { const r = latest(); if (r) event(r, 'Operator notes updated'); });
  $('bool-keep').addEventListener('click', () => {
    if (!canKeep()) return;
    const r = latest(); r.holdOneAt = now();
    event(r, 'Operator chose Keep at 1; later readback verified 1', {supplier_timestamp_utc:status.supplier_timestamp_utc}); render();
  });
  $('bool-issue').addEventListener('click', () => { const r = latest(); if (r) { r.issueAt = now(); event(r, 'Operator recorded an issue'); finish(r); render(); } });
  $('bool-new').addEventListener('click', () => { if (tag() && !busy && !$('bool-new').disabled) { draftNote = ''; create(tag()); render(); } });
  $('bool-export-csv').addEventListener('click', () => download('csv')); $('bool-export-json').addEventListener('click', () => download('json'));
  setInterval(() => { $('bool-timer').textContent = feedbackTimer(latest()); }, 100);
}
