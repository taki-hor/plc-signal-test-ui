import {$, node, groupFor, valueText, formatTime, setText} from './dom.js';

let tags = [], poll = null, status = null, cases = [], records = [], storageKey = null;
let selectedTag = null, selectedRecord = '';
const MAX_RECORDS = 50;
const selected = () => tags.find(t => t.tag_name === $('write-tag').value);
const reads = () => tags.filter(t => t.read_write === 'R');
const includes = (r, name) => r.writes.some(w => w.tag_name === name);
const currentRecord = () => records.find(r => r.id === selectedRecord);
function operatorResult(r) {
  if (r?.operatorResult === 'fail' || r?.operatorResult === 'unchecked') return r.operatorResult;
  const stamp = r?.operatorCompletedAt;
  const valid = typeof stamp === 'number' ? Number.isFinite(stamp) && stamp > 0 : typeof stamp === 'string' && stamp.trim() !== '' && Number.isFinite(Date.parse(stamp));
  return valid ? 'pass' : 'unchecked';
}
const operatorLabel = result => result === 'pass' ? 'Pass' : result === 'fail' ? 'Fail' : 'Not checked';
function persist() {
  if (!storageKey) return;
  try { localStorage.setItem(storageKey, JSON.stringify(records)); }
  catch { $('write-feedback-storage').textContent = 'Feedback history could not be saved. Export it before leaving this page.'; $('write-feedback-storage').classList.remove('hidden'); }
}
function interrupt(reason) {
  let changed = false;
  for (const r of records) if (r.state === 'WAITING') { r.state = 'MONITORING INTERRUPTED'; r.reason = reason; changed = true; }
  if (changed) persist();
}
function loadHistory() {
  if (!status?.mode || !status.api_address) return;
  const key = `plc-value-feedback:v1:${status.mode}:${status.api_address}`;
  if (key === storageKey) return;
  interrupt('API context changed'); storageKey = key; records = []; selectedRecord = ''; selectedTag = null;
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? '[]');
    if (!Array.isArray(saved)) throw new Error('Invalid saved history');
    records = saved.filter(r => r && typeof r.id === 'string' && Array.isArray(r.writes) && r.writes.every(w => typeof w.tag_name === 'string') && Array.isArray(r.feedback)).slice(-MAX_RECORDS);
    for (const r of records) {
      if (r.state === 'SENDING') { r.state = 'OUTCOME UNKNOWN'; r.reason = 'Page reloaded before the write receipt arrived'; }
    }
    interrupt('Page reloaded before feedback was observed');
    persist();
  } catch { $('write-feedback-storage').textContent = 'Saved feedback history could not be read.'; $('write-feedback-storage').classList.remove('hidden'); }
}
export function beginWriteObservation(writes) {
  loadHistory();
  // A subsequent write can interfere with an unfinished observation.
  interrupt('Another Value write was requested before feedback was observed');
  const r = {id:crypto.randomUUID(), requested_at:new Date().toISOString(), writes:structuredClone(writes), state:'SENDING', feedback:[], before:null, after:null};
  records.push(r); records = records.slice(-MAX_RECORDS); selectedRecord = r.id;
  if (!includes(r, selected()?.tag_name)) {
    $('write-tag').value = writes[0].tag_name;
    $('write-tag').dispatchEvent(new Event('change'));
  }
  persist(); render(); return r;
}
export function finishWriteObservation(r, response, error = null) {
  if (!records.includes(r)) return; // Do not attach an old API context's receipt to a new history.
  if (error) {
    r.state = error.writeDispatched === false ? 'BLOCKED BEFORE DISPATCH' : 'OUTCOME UNKNOWN'; r.reason = error.message;
  } else {
    r.accepted_at = response.console_accepted_at ?? null;
    r.before = response.console_read_baseline ?? null;
    const accepted = (r.writes.length === 1 && response.written === true) || response.console_batch_accepted === true;
    r.feedback = (r.before?.mappings ?? []).map(m => ({...m, before:r.before.values[m.feedback_tag],
      state:m.requires_confirmation ? 'NEEDS CONFIRMATION' : r.before.values[m.feedback_tag] === m.expected_feedback ? 'ALREADY SET BEFORE WRITE' : 'WAITING'}));
    r.state = !accepted ? 'ACCEPTANCE NOT CONFIRMED' :
      !Number.isFinite(Date.parse(r.accepted_at)) || !Number.isFinite(Date.parse(r.before?.supplier_timestamp_utc)) ? 'MISSING BASELINE' : 'WAITING';
    if (r.state === 'MISSING BASELINE') r.reason = 'Update/restart the backend to record final pre-write evidence. Check the equipment state before another write.';
  }
  persist(); render();
}
function observe() {
  const healthy = poll && status?.supplier_api_connected && status.data_fresh && status.plc_mode === 'REMOTE' && poll.timestamp === status.supplier_timestamp;
  if (!healthy) { interrupt('Fresh, matching Remote data was lost'); return; }
  const stamp = Date.parse(status.supplier_timestamp_utc);
  for (const r of records) {
    if (r.state !== 'WAITING' || !(stamp > Date.parse(r.accepted_at) && stamp > Date.parse(r.before?.supplier_timestamp_utc))) continue;
    const confirmed = r.feedback.filter(f => !f.requires_confirmation);
    // Missing read values cannot qualify as an observation.
    if (Object.keys(r.before.values).some(name => poll[name] == null)) continue;
    let changed = !r.after;
    for (const f of confirmed) {
      if (f.state === 'WAITING' && poll[f.feedback_tag] === f.expected_feedback) {
        f.state = 'EXPECTED FEEDBACK OBSERVED'; f.observed_at = status.supplier_timestamp_utc; f.value = poll[f.feedback_tag]; changed = true;
      }
    }
    if (changed) {
      r.after = {supplier_timestamp:poll.timestamp, supplier_timestamp_utc:status.supplier_timestamp_utc,
        recorded_at:new Date().toISOString(), values:Object.fromEntries(Object.keys(r.before.values).map(name => [name,poll[name]]))};
      if (!confirmed.some(f => f.state === 'WAITING')) r.state = confirmed.some(f => f.state === 'EXPECTED FEEDBACK OBSERVED') ? 'EXPECTED FEEDBACK OBSERVED' : 'READ SNAPSHOT RECORDED';
      persist();
    }
  }
}
function canSetResult(r) {
  return Boolean(r && records.includes(r) && !records.some(item => item.state === 'SENDING') &&
    r.state !== 'BLOCKED BEFORE DISPATCH' && (r.accepted_at || ['OUTCOME UNKNOWN','ACCEPTANCE NOT CONFIRMED','MISSING BASELINE'].includes(r.state)));
}
function setOperatorResult(value) {
  const r = currentRecord();
  if (!canSetResult(r) || !['unchecked','pass','fail'].includes(value) || operatorResult(r) === value) return;
  const at = new Date().toISOString(), previous = operatorResult(r), previousAt = r.operatorResultAt ?? r.operatorCompletedAt ?? null,
    previousComplete = r.operatorCompletedAt ?? null;
  Object.assign(r,{operatorResult:value,operatorResultAt:at,operatorCompletedAt:value === 'pass' ? at : null});
  if (!Array.isArray(r.operatorEvents)) r.operatorEvents = [];
  r.operatorEvents.push({action:`Marked ${operatorLabel(value)} by operator`,at,
    write_id:r.id,mode:status?.mode,api_address:status?.api_address,writes:structuredClone(r.writes),
    api_result:r.state,operator_result:value,operator_result_at:at,previous_operator_result:previous,
    previous_operator_result_at:previousAt,previous_operator_completed_at:previousComplete,write_sent:false});
  persist(); render();
}
function canCapture(r) {
  const stamp = Date.parse(status?.supplier_timestamp_utc);
  return Boolean(r?.accepted_at && r.before?.values && status?.supplier_api_connected && status.data_fresh &&
    poll?.timestamp === status.supplier_timestamp && stamp > Date.parse(r.accepted_at) && stamp > Date.parse(r.before.supplier_timestamp_utc) &&
    Object.keys(r.before.values).every(name => poll[name] != null));
}
function captureCurrent() {
  const r = currentRecord();
  if (!canCapture(r)) return;
  r.after = {supplier_timestamp:poll.timestamp, supplier_timestamp_utc:status.supplier_timestamp_utc,
    recorded_at:new Date().toISOString(), source:'Operator snapshot', plc_mode:status.plc_mode,
    values:Object.fromEntries(Object.keys(r.before.values).map(name => [name,poll[name]]))};
  // Capturing telemetry never resumes an interrupted completion monitor or certifies a mapping.
  persist(); render();
}
export function updateWriteFeedback(nextTags, nextPoll, nextStatus, nextCases) {
  if (nextTags) tags = nextTags;
  if (nextPoll) poll = nextPoll;
  if (nextStatus) status = nextStatus;
  if (nextCases) cases = nextCases;
  loadHistory(); observe(); render();
}
function related(tag, item) {
  return Boolean(tag && (groupFor(tag) === groupFor(item) || cases.some(c => c.command_tag === tag.tag_name && c.feedback_tag === item.tag_name)));
}
function render() {
  const tag = selected(), name = tag?.tag_name;
  if (name !== selectedTag) { selectedTag = name; selectedRecord = records.findLast(r => includes(r,name))?.id ?? ''; }
  const available = records.filter(r => includes(r,name)).slice().reverse();
  const select = $('write-feedback-record'), optionVersion = available.map(r => `${r.id}:${r.state}:${operatorResult(r)}:${r.operatorResultAt ?? r.operatorCompletedAt ?? ''}`).join('|');
  if (select.dataset.version !== optionVersion) {
    select.dataset.version = optionVersion;
    const live = node('option','','Live values only'); live.value = '';
    select.replaceChildren(live, ...available.map(r => { const opt = node('option','',`${formatTime(r.requested_at)} · ${r.writes.map(w => `${w.tag_name}=${w.value}`).join(', ')} · ${r.state} · ${operatorLabel(operatorResult(r))}`); opt.value = r.id; return opt; }));
  }
  select.value = selectedRecord;
  const r = currentRecord(), human = operatorResult(r), choice = $('write-feedback-operator-result');
  const operatorState = $('write-feedback-operator-state');
  setText('write-feedback-operator-state',!r ? 'NO RECORD SELECTED' : human === 'pass' ? 'PASS — YOUR CHECK' : human === 'fail' ? 'FAIL — YOUR CHECK' : 'AWAITING YOUR CHECK');
  operatorState.className = 'pill manual-result-badge'; operatorState.dataset.cardResult = human;
  operatorState.title = r && human !== 'unchecked' ? `Your ${operatorLabel(human)} result set at ${formatTime(r.operatorResultAt ?? r.operatorCompletedAt)}` : 'Only your physical check sets this result.';
  if (document.activeElement !== choice) choice.value = human;
  choice.disabled = !canSetResult(r);
  $('write-feedback-capture').disabled = !canCapture(r);
  const fresh = Boolean(status?.supplier_api_connected && status.data_fresh && poll?.timestamp === status.supplier_timestamp);
  $('write-feedback-health').textContent = fresh ? 'LIVE · FRESH' : 'STALE / NO DATA';
  $('write-feedback-health').className = `pill ${fresh ? '' : 'amber'}`;
  const mappings = cases.filter(c => c.command_tag === name);
  $('write-feedback-mapping').textContent = mappings.length ? mappings.map(c => `${c.command_tag}=${c.command_value} → ${c.feedback_tag}=${c.expected_feedback} · ${c.requires_confirmation ? 'Mapping under test — observe the equipment' : 'Local pair'}`).join('; ') : 'No configured completion mapping. Same-group signals provide context. The console does not infer success.';
  const nearby = reads().filter(t => related(tag,t));
  const direct = new Set(mappings.map(c => c.feedback_tag));
  // Both door position signals stay visible when inspecting either door command.
  const cards = nearby.filter(t => direct.has(t.tag_name) || /Door(?:Opened|Closed)$/.test(t.tag_name) && /Door/.test(name ?? ''));
  const container = $('write-feedback-related'); container.replaceChildren();
  for (const item of cards) {
    const card = node('div','feedback-signal'); card.dataset.feedbackTag = item.tag_name;
    card.append(node('span','',item.tag_name),node('strong',fresh ? '' : 'warn',valueText(poll?.[item.tag_name])),node('small','',item.description)); container.append(card);
  }
  setText('write-feedback-result',!r ? 'No write record selected. Live monitoring sends no commands.' :
    `${r.state} · ${r.feedback.map(f => `${f.feedback_tag}: ${f.state}`).join(' · ')}${r.reason ? ` · ${r.reason}` : ''}`);
  $('write-feedback-times').textContent = !r ? '' : `Before: ${r.before?.supplier_timestamp_utc ?? 'not recorded'} · API accepted: ${r.accepted_at ?? 'not confirmed'} · Recorded after: ${r.after?.supplier_timestamp_utc ?? 'not recorded'}${r.after?.source ? ` · ${r.after.source}` : ''}`;
  const query = $('write-feedback-search').value.trim().toLowerCase(), scope = $('write-feedback-scope').value;
  const items = reads().filter(t => (scope === 'all' || related(tag,t)) && [t.tag_name,t.description,t.device_address].some(v => v.toLowerCase().includes(query)))
    .sort((a,b) => Number(direct.has(b.tag_name))-Number(direct.has(a.tag_name)) || Number(related(tag,b))-Number(related(tag,a)) || a.tag_name.localeCompare(b.tag_name));
  const table = $('write-feedback-table'); table.replaceChildren();
  for (const item of items) {
    const tr = node('tr'); tr.dataset.readTag = item.tag_name; tr.dataset.related = String(related(tag,item)); tr.title = item.device_address;
    const fields = [item.tag_name,item.description,r?.before ? valueText(r.before.values[item.tag_name]) : '—',r?.after ? valueText(r.after.values[item.tag_name]) : '—',valueText(poll?.[item.tag_name]),direct.has(item.tag_name) ? 'Mapped feedback' : related(tag,item) ? 'Same group' : 'Read-only'];
    fields.forEach((value,i) => { const td = node('td',i===1 ? 'description' : '',value); td.title = String(value); tr.append(td); }); table.append(tr);
  }
  $('write-feedback-count').textContent = `${items.length} / ${reads().length} read signals · selected command's group first · live values ${fresh ? 'fresh' : 'stale or unavailable'}`;
}
function exportRecords(format) {
  let content, type;
  if (format === 'json') { content = JSON.stringify({exported_at:new Date().toISOString(),api_address:status?.api_address,mode:status?.mode,records},null,2); type = 'application/json'; }
  else {
    const columns = ['write_id','requested_at','commands','result','read_tag','before','before_timestamp_utc','after','after_timestamp_utc','api_accepted_at','feedback_evidence','operator_result','operator_result_at','operator_completed_at','operator_events'];
    const operatorFields = r => [operatorResult(r),r.operatorResultAt ?? r.operatorCompletedAt ?? '',r.operatorCompletedAt ?? '',JSON.stringify(r.operatorEvents ?? [])];
    const rows = records.flatMap(r => Object.keys(r.before?.values ?? {}).map(name => [r.id,r.requested_at,r.writes.map(w => `${w.tag_name}=${w.value}`).join('; '),r.state,name,r.before.values[name],r.before.supplier_timestamp_utc,r.after?.values[name],r.after?.supplier_timestamp_utc,r.accepted_at,JSON.stringify(r.feedback.filter(f => f.feedback_tag === name)),...operatorFields(r)]));
    // Include blocked/unknown writes even when no receipt snapshot exists.
    for (const r of records.filter(r => !r.before)) rows.push([r.id,r.requested_at,r.writes.map(w => `${w.tag_name}=${w.value}`).join('; '),r.state,...Array(7).fill(''),...operatorFields(r)]);
    const cell = v => { let s = String(v ?? ''); if (typeof v === 'string' && /^[=+@\-\t\r]/.test(s)) s = "'"+s; return '"'+s.replaceAll('"','""')+'"'; };
    content = [columns,...rows].map(row => columns.map((_,i) => cell(row[i])).join(',')).join('\r\n'); type = 'text/csv';
  }
  const url = URL.createObjectURL(new Blob([content],{type})), a = document.createElement('a');
  a.href = url; a.download = `plc-value-feedback-${new Date().toISOString().slice(0,10)}.${format}`; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
}
export function initWriteFeedback() {
  $('write-tag').addEventListener('change',render);
  for (const id of ['write-feedback-search','write-feedback-scope']) $(id).addEventListener('input',render);
  $('write-feedback-record').addEventListener('change',() => { selectedRecord = $('write-feedback-record').value; render(); });
  for (const format of ['json','csv']) $(`write-feedback-export-${format}`).addEventListener('click',() => exportRecords(format));
  $('write-feedback-capture').addEventListener('click',captureCurrent);
  $('write-feedback-operator-result').addEventListener('change',() => {
    const choice = $('write-feedback-operator-result'); setOperatorResult(choice.value); choice.value = operatorResult(currentRecord());
  });
  window.addEventListener('pagehide',() => interrupt('Page left before feedback was observed'));
}
