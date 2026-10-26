import {savedHumanDecision, manualDecisions, signature} from './saved-results.js';
import {apiCheckFor, apiFilterMatches, renderApiBadge, renderSavedResults} from './api-checks.js';
import {commandGuidance} from './command-guidance.js';
import {$, node, groupFor, fillGroups, valueText, setText} from './dom.js';
import {post, modeEnabled} from './api.js';
import {confirmWrite, validate, writeIdentity} from './controls.js';

let tags = [], poll = null, status = null, cases = [], selected = null;
let records = [], storageKey = null, busy = false, draftNote = '', draftMode = 'manual0', changed = () => {};
const rows = new Map();
const feedbackTests = new Set(), feedbackClears = new Set(), deferredFeedback = new Map(), clearPreviousStates = new Map();
let catalogLoaded = false, catalogError = null;
const now = () => Date.now();
function tag() { return tags.find(t => t.tag_name === selected); }
function latest(t = tag()) {
  if (!t) return null;
  for (let i = records.length - 1; i >= 0; i--) {
    if (records[i].tag_name === t.tag_name && records[i].address === t.device_address) return records[i];
  }
  return null;
}
function modeLocked(r = latest()) { return Boolean(r?.oneRequestedAt && !r.oneRejectedAt); }
function endMode(t = tag(), r = latest(t)) {
  if (/door/i.test(t?.tag_name ?? '')) return 'manual0';
  return (modeLocked(r) ? r.endMode : draftMode) === 'hold' ? 'hold' : 'manual0';
}
function modeLabel(mode) { return mode === 'hold' ? 'Hold at 1' : 'Send 1 → manual 0'; }
function apiCycleComplete(r) { return Boolean(r?.oneAcceptedAt && r.zeroAcceptedAt && r.zeroSeenAt); }
export function operatorResult(r) {
  if (r?.issueAt || r?.operatorResult === 'fail') return 'fail';
  if (r?.operatorResult === 'unchecked') return 'unchecked';
  return Number.isFinite(r?.operatorCompletedAt) && r.operatorCompletedAt > 0 ? 'pass' : 'unchecked';
}
export function operatorComplete(r) { return operatorResult(r) === 'pass'; }
export function operatorStatus(r) {
  if (!r) return 'NOT TESTED';
  if (operatorResult(r) === 'fail') return 'ISSUE';
  if (operatorComplete(r)) return 'COMPLETE';
  if (r.oneRejectedAt) return 'BLOCKED';
  if (!r.oneRequestedAt && !r.oneAcceptedAt) return 'NOT TESTED';
  return r.oneAcceptedAt ? 'AWAITING YOUR CHECK' : 'NOT COMPLETE';
}
function needsClear(r) { return Boolean(r && !r.zeroSeenAt && ((r.oneRequestedAt && !r.oneRejectedAt) || (r.zeroOnlyCleanup && r.zeroRequestedAt))); }
function pending() { return records.filter(r => needsClear(r) && (!r.holdOneAt || r.zeroRequestedAt)); }
function held() { return records.filter(r => needsClear(r) && r.holdOneAt && !r.zeroRequestedAt); }
export function pendingCommandNames() { return pending().map(r => r.tag_name); }
export function isFeedbackRunning(r) { return feedbackTests.has(r); }
export function activeCommandNames() {
  // A changed address must leave the old unresolved request visible for review.
  return [...new Set(records.filter(needsClear).map(r => r.tag_name))];
}
export function commandIntent(name) {
  const t = tags.find(item => item.tag_name === name), r = latest(t);
  if (!knownRecord(r) || (!needsClear(r) && !feedbackTests.has(r) && !feedbackClears.has(r))) return null;
  const held = Boolean(r.holdOneAt && !r.zeroRequestedAt && !r.zeroSeenAt);
  return {address:r.address,endMode:r.endMode ?? null,source:r.source ?? 'Manual 0/1',
    held,pending:needsClear(r) && !held,waiting:feedbackTests.has(r),clearRequested:Boolean(r.zeroRequestedAt)};
}
function commandsConflict(t, r, feedbackTag = null) {
  if (!t || !r) return false;
  if (t.tag_name === r.tag_name || t.device_address === r.address) return true;
  const door = name => /^(Tank\d+)_Door(?:Open|Close)Remote$/i.exec(name)?.[1];
  if (door(t.tag_name) && door(t.tag_name) === door(r.tag_name)) return true;
  const feedback = new Set([feedbackTag, ...cases.filter(c => c.command_tag === t.tag_name).map(c => c.feedback_tag)].filter(Boolean));
  return feedback.has(r.feedback_tag) || cases.some(c => c.command_tag === r.tag_name && feedback.has(c.feedback_tag));
}
function conflictingRecord(t, feedbackTag = null) {
  return records.find(r => (needsClear(r) || feedbackTests.has(r) || feedbackClears.has(r)) && commandsConflict(t,r,feedbackTag));
}
function clearConflicts(t) {
  return records.some(r => (needsClear(r) || feedbackTests.has(r) || feedbackClears.has(r)) && commandsConflict(t,r) &&
    t.device_address !== r.address);
}
function result(r) {
  if (!r) return 'NOT TESTED';
  if (r.oneRejectedAt) return 'BLOCKED';
  if (apiCycleComplete(r)) return 'API CYCLE RECORDED';
  if (r.zeroOnlyCleanup && r.zeroAcceptedAt && r.zeroSeenAt) return 'CLEAR VERIFIED';
  if (r.zeroRequestedAt && needsClear(r)) return 'NEEDS 0';
  if (r.holdOneAt) return 'KEPT AT 1';
  if (r.oneRequestedAt && !r.zeroSeenAt) {
    if (/door/i.test(r.tag_name) || !r.oneAcceptedAt || r.endMode === 'manual0' || r.zeroRequestedAt) return 'NEEDS 0';
    return r.endMode === 'hold' ? 'WAITING FOR 1 READBACK' : 'CLEAR / KEEP 1';
  }
  return 'IN PROGRESS';
}
function elapsed(ms) { return `${String(Math.floor(ms / 60000)).padStart(2, '0')}:${((ms % 60000) / 1000).toFixed(1).padStart(4, '0')}`; }
function feedbackTimer(r) {
  if (!r?.oneRequestedAt) return '00:00.0';
  if (!['SENDING','WAITING','CONFIRMED'].includes(r.feedbackState)) return '—';
  return elapsed((r.feedbackStoppedAt ?? now()) - r.oneRequestedAt);
}
function stopFeedback(r, state, detail = {}, stoppedAt = now()) {
  r.feedbackState = state; r.feedbackStoppedAt = stoppedAt;
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
  if (!r.finishedAt && (apiCycleComplete(r) || (r.zeroOnlyCleanup && r.zeroAcceptedAt && r.zeroSeenAt) || (r.issueAt && r.zeroSeenAt))) {
    r.finishedAt = now(); event(r, r.issueAt ? 'Issue recorded; clear verified' : r.zeroOnlyCleanup ? 'Manual cleanup verified 0; no write 1 recorded' : 'API cycle recorded; physical result requires operator observation');
  }
}
function create(t, note = draftNote, mode = endMode(t)) {
  const reference = cases.find(c => c.command_tag === t.tag_name && c.command_value === 1 && !c.requires_confirmation);
  const r = {id:crypto.randomUUID(), tag_name:t.tag_name, address:t.device_address, identity:signature(t), startedAt:now(), note, endMode:mode,
             feedback_tag:reference?.feedback_tag ?? null, events:[]};
  records.push(r); event(r, 'Checklist started'); return r;
}
function healthy() { return modeEnabled() && status?.supplier_api_connected && status?.data_fresh && status?.plc_mode === 'REMOTE'; }
function captureClearIntent(r, requestedAt = now()) {
  Object.assign(r, {zeroRequestedAt:requestedAt, zeroBaselineUtc:status?.supplier_timestamp_utc, zeroAcceptedAt:null,
    zeroServerAt:null, zeroSeenAt:null, zeroCommandBaselineUtc:null, zeroApiElapsedMs:null});
}
function startClear(r, started = now()) {
  clearPreviousStates.set(r,r.feedbackState); feedbackClears.add(r);
  captureClearIntent(r,started);
  if (['WAITING','SENDING'].includes(r.feedbackState)) r.feedbackState = 'CLEARING';
}
function applyFeedbackResult(r, response, receivedAt = now()) {
  stopFeedback(r, response.result === 'PASS' && !r.mappingUnderTest ? 'CONFIRMED' :
    response.result === 'OBSERVED' || response.result === 'PASS' ? 'OBSERVED' : response.result ?? 'OUTCOME UNKNOWN',
    {backend_result:response.result, backend_elapsed_ms:response.elapsed_ms, mapping_under_test:r.mappingUnderTest},receivedAt);
}
function clearBlocked(r) {
  if (r.feedbackInterruptedByClearAt) return;
  const deferred = deferredFeedback.get(r);
  if (deferred?.failure) stopFeedback(r,deferred.failure,{reason:deferred.error?.message ?? deferred.response?.error ?? 'No matching accepted write receipt',backend_result:deferred.response?.result ?? null},deferred.receivedAt);
  else if (deferred) applyFeedbackResult(r,deferred.response,deferred.receivedAt);
  else if (r.feedbackState === 'CLEARING') r.feedbackState = clearPreviousStates.get(r) ?? 'WAITING';
}
function clearDispatched(r) {
  r.feedbackInterruptedByClearAt ??= r.zeroRequestedAt ?? now(); deferredFeedback.delete(r);
}
function releaseClear(r) {
  feedbackClears.delete(r); clearPreviousStates.delete(r); deferredFeedback.delete(r);
}
function canSend(value) {
  const t = tag(), r = latest();
  if (!t || busy || !healthy()) return false;
  if ((value === 1 && conflictingRecord(t)) || (value === 0 && (feedbackClears.has(r) || clearConflicts(t)))) return false;
  if (value === 1 && (poll?.[t.tag_name] !== 0 || needsClear(r) || (r?.oneRequestedAt && !r.oneRejectedAt) || r?.issueAt || (r?.finishedAt && !r.oneRejectedAt))) return false;
  if (value === 0 && r?.zeroSeenAt) return false;
  try { validate(t, String(value)); return true; } catch { return false; }
}
function canKeep(r = latest()) {
  const t = tags.find(item => item.tag_name === r?.tag_name && item.device_address === r.address), stamp = Date.parse(status?.supplier_timestamp_utc);
  return Boolean(t && r === latest(t) && !/door/i.test(t.tag_name) && r.oneAcceptedAt && !r.holdOneAt && !r.zeroAcceptedAt && !busy && healthy() &&
    poll?.timestamp === status.supplier_timestamp && poll[t.tag_name] === 1 && stamp > Date.parse(r.oneServerAt) && stamp > Date.parse(r.oneBaselineUtc) && stamp > Date.parse(r.oneCommandBaselineUtc));
}
function keepAtOne(r, automatic = false) {
  if (!canKeep(r)) return;
  r.holdOneAt = now();
  event(r, automatic ? 'Hold mode recorded Keep at 1; later readback verified 1' : 'Operator chose Keep at 1; later readback verified 1',
    {supplier_timestamp_utc:status.supplier_timestamp_utc, end_mode:r.endMode ?? null, automatic_local_record:automatic, write_sent:false});
}
function select(name) {
  selected = name; draftNote = latest()?.note ?? ''; draftMode = latest()?.endMode === 'hold' && !/door/i.test(name) ? 'hold' : 'manual0';
  $('bool-notes').value = draftNote; render();
}
function buildList() {
  fillGroups($('bool-group'), tags); rows.clear(); $('bool-list').replaceChildren();
  for (const t of tags) {
    const button = node('button', 'bool-tag'); button.type = 'button'; button.dataset.commandTag = t.tag_name;
    const meta = node('span', 'bool-tag-meta'), current = node('span'), progress = node('span');
    const api = node('span','api-check-badge','Unchecked');
    meta.append(current,api,progress); button.append(node('strong', '', t.tag_name), node('small', '', t.description), meta);
    button.addEventListener('click', event => {
      if (busy) return;
      select(t.tag_name);
      const workspace = $('bool-name').closest('.bool-workspace'), bounds = workspace.getBoundingClientRect();
      const offscreen = bounds.top < 0 || bounds.top >= window.innerHeight;
      if (offscreen) workspace.scrollIntoView({block:'start'});
      if (offscreen || event.detail === 0) {
        $('bool-name').setAttribute('tabindex','-1'); $('bool-name').focus({preventScroll:true});
      }
    });
    $('bool-list').append(button); rows.set(t.tag_name, {button, current, progress, api});
  }
  const empty = node('div', 'hint'); empty.id = 'bool-empty'; empty.setAttribute('role', 'status');
  const message = node('p'); message.id = 'bool-empty-message';
  const retry = node('button', 'secondary', 'Retry catalog'); retry.id = 'bool-catalog-retry'; retry.type = 'button';
  retry.addEventListener('click', () => $('refresh-btn').click());
  const clear = node('button', 'secondary', 'Clear filters'); clear.id = 'bool-clear-filters'; clear.type = 'button';
  clear.addEventListener('click', () => { $('bool-search').value = ''; $('bool-group').value = 'all'; $('bool-filter').value = 'all'; $('bool-api-filter').value='all'; render(); });
  empty.append(message, retry, clear); $('bool-list').append(empty);
}
function writeHint(r, active) {
  if (!modeEnabled()) return 'Read-only: enable write test mode to send.';
  if (busy) return 'Write request in progress.';
  if (!status?.supplier_api_connected || !status?.data_fresh) return 'Fresh API data is required to send.';
  if (status.plc_mode !== 'REMOTE') return 'PLC Remote/API mode is required to send.';
  const other = records.find(a => a !== r && (needsClear(a) || feedbackTests.has(a) || feedbackClears.has(a)) && commandsConflict(tag(),a));
  if (other) return `Resolve ${other.tag_name} before operating the same command, address, feedback signal or door actuator.`;
  if ((r?.zeroAcceptedAt && !r.zeroSeenAt && !Number.isFinite(Date.parse(r.zeroCommandBaselineUtc))) ||
      (r?.oneAcceptedAt && !r.zeroAcceptedAt && !r.holdOneAt && !Number.isFinite(Date.parse(r.oneCommandBaselineUtc))))
    return 'The receipt lacks a final pre-write timestamp. The console cannot verify readback. Restart the backend. Check state before you resend 0.';
  if (r?.holdOneAt && !r.zeroSeenAt) return 'Kept at 1. Other tests are available. Send 0 when this state should end.';
  if (needsClear(r)) {
    if (/door/i.test(r?.tag_name)) return commandGuidance(tag()).confirmed ? 'Command 1 is pending. After physical movement finishes, send 0 before repeating this door command.' : 'Door command 1 is pending. Confirm its hold/reset procedure before sending 0. Unrelated commands remain available.';
    if (r?.endMode === 'hold') return r.zeroRequestedAt || r.issueAt || r.holdInterruptedAt ? 'Hold does not resume after a clear request or recorded issue. Check the state before you manually send 0.' : 'Hold 1 selected. This command needs API acceptance and a fresh later readback of 1.';
    return r?.endMode === 'manual0' ? 'Manual 0 selected. Send 0 and verify its readback before repeating this command. Unrelated commands remain available.' : 'Choose the end state using the confirmed command rule: send 0, or explicitly Keep at 1 once its later readback is 1.';
  }
  if (r?.finishedAt && !r.oneRejectedAt) return 'Cycle recorded. Choose New attempt to send 1 again.';
  return '';
}
function render() {
  const t = tag(), r = latest(), guide = commandGuidance(t), query = $('bool-search').value.trim().toLowerCase(), group = $('bool-group').value, filter = $('bool-filter').value;
  let visible = 0, done = 0;
  for (const item of tags) {
    const row = rows.get(item.tag_name), record = latest(item), human = savedHumanDecision(item,status)?.value ?? 'unchecked', isDone = human === 'pass';
    if (isDone) done++;
    const matches = [item.tag_name, item.description, item.device_address].some(v => v.toLowerCase().includes(query)) &&
      (group === 'all' || groupFor(item) === group) && apiFilterMatches(item,$('bool-api-filter').value,human,status) && (filter === 'all' || (filter === 'complete' ? isDone : filter === 'fail' ? human === 'fail' : human === 'unchecked'));
    row.button.classList.toggle('hidden', !matches); if (matches) visible++;
    row.button.classList.toggle('selected', selected === item.tag_name); row.button.setAttribute('aria-pressed', String(selected === item.tag_name));
    row.button.disabled = busy; row.current.textContent = `Value ${valueText(poll?.[item.tag_name])}`;
    row.button.dataset.result = human === 'pass' ? 'COMPLETE' : human === 'fail' ? 'ISSUE' : 'NOT CHECKED'; row.button.dataset.operatorResult = human;
    row.progress.textContent = human === 'pass' ? '✓ Pass' : human === 'fail' ? '✕ Fail' : 'Not checked';
    renderApiBadge(row.api,item,status);
    row.progress.className = 'manual-result-badge'; row.progress.dataset.cardResult = human;
    row.progress.title = human === 'pass' ? 'Operator verified by physical observation' : human === 'fail' ? 'Operator recorded a failed check' : 'No human result has been set';
  }
  $('bool-empty').classList.toggle('hidden', visible > 0);
  $('bool-empty-message').textContent = tags.length ? 'No commands match your filters.' : catalogLoaded ? 'No writable 0/1 commands are available in this catalog. Numeric setpoints are on Setpoints & batch.' : catalogError ? `Command catalog unavailable: ${catalogError}. The console will retry. You can also select Retry catalog.` : 'Loading commands…';
  $('bool-catalog-retry').classList.toggle('hidden', !catalogError || tags.length > 0);
  $('bool-clear-filters').classList.toggle('hidden', !tags.length || visible > 0);
  $('bool-progress').textContent = `${done} / ${tags.length} tests marked complete · ${held().length} kept at 1 · ${visible} shown`;
  const open = pending().length + held().length;
  $('nav-commands-badge').textContent = open ? `${open} open` : `${done}/${tags.length}`; $('nav-commands-badge').classList.toggle('amber', open > 0);
  $('bool-name').textContent = t?.tag_name ?? 'Select a command'; $('bool-description').textContent = t?.description ?? 'Numeric setpoints are on Setpoints & batch.';
  renderApiBadge($('bool-api-state'),t,status); renderSavedResults($('bool-saved-results'),t,status);
  $('bool-value').textContent = valueText(t ? poll?.[t.tag_name] : null); $('bool-address').textContent = t?.device_address ?? '—';
  const reference = r?.feedback_tag ?? cases.find(c => c.command_tag === t?.tag_name && c.command_value === 1 && !c.requires_confirmation)?.feedback_tag;
  $('bool-feedback').textContent = !t ? '' : reference ? `Live feedback (${r?.mappingUnderTest ? 'mapping under test' : 'local pair'}): ${reference} = ${valueText(poll?.[reference])}. Record physical observations.` : 'The feedback mapping is unconfirmed. Record physical observations.';
  $('bool-guidance').classList.toggle('hidden', !t); $('bool-guidance').dataset.kind = guide.kind; $('bool-guidance').dataset.confirmed = String(Boolean(guide.confirmed));
  for (const [id, text] of [['bool-rule-title',guide.title],['bool-rule-evidence',guide.evidence],['bool-rule-one',guide.one],['bool-rule-zero',guide.zero],['bool-rule-procedure',guide.procedure]]) $(id).textContent = text;
  const active = pending(); setText('bool-pending',active.length ? `Checklist commands awaiting a verified 0: ${active.map(a => `${a.tag_name} (${a.address})`).join(', ')}. Select the command to clear it. You can explicitly keep non-door states at 1.` : '');
  $('bool-pending').classList.toggle('hidden', !active.length);
  const maintained = held(); setText('bool-held',maintained.length ? `Operator chose Keep at 1: ${maintained.map(a => `${a.tag_name} (${a.address}) · current ${valueText(poll?.[a.tag_name])}`).join(', ')}. Clear each when finished. The console does not send another write or enforce 1.` : '');
  $('bool-held').classList.toggle('hidden', !maintained.length);
  const mode = endMode(t, r), locked = !t || busy || modeLocked(r), door = /door/i.test(t?.tag_name ?? '');
  $('bool-mode-hold').checked = mode === 'hold'; $('bool-mode-manual').checked = mode === 'manual0';
  $('bool-mode-hold').disabled = locked || door; $('bool-mode-manual').disabled = locked;
  $('bool-hold-hint').classList.toggle('hidden', guide.hint !== 'hold');
  $('bool-manual-confirmed').classList.toggle('hidden', !guide.confirmed);
  $('bool-mode-hint').textContent = !t ? 'Select a command to choose its end state.' : door ? 'Door commands use Manual 0. Hold 1 is unavailable. Confirm this door’s procedure before testing.' :
    modeLocked(r) && !r.endMode ? 'This existing attempt has no captured mode. Use the manual Keep at 1 or Send 0 control after checking its state.' :
    `${modeLocked(r) ? 'Mode locked for this attempt. ' : ''}${mode === 'hold' ? 'After you confirm 1, the console needs a fresh later readback of 1. It then records Keep at 1. It sends no extra write. It does not enforce 1 or prove physical operation.' : 'Observe the equipment after you send 1. Manually send 0 when the confirmed procedure requires it. The console does not send automatic 0.'}`;
  if (guide.hint === 'hold') $('bool-mode-hint').textContent = `Manual suggests Hold 1. Confirm the rule. ${$('bool-mode-hint').textContent}`;
  $('bool-end-mode').title = $('bool-mode-hint').textContent;
  $('bool-one').textContent = mode === 'hold' ? 'Set & hold 1…' : 'Send 1…';
  $('bool-keep').classList.toggle('hidden', !r || Boolean(r.endMode) || door);
  $('bool-keep').disabled = !canKeep();
  const hint = writeHint(r, active); if ($('bool-write-hint').textContent !== hint) $('bool-write-hint').textContent = hint;
  $('bool-one').disabled = !canSend(1); $('bool-zero').disabled = !canSend(0);
  for (const [id, verified, label] of [['bool-sent-one',r?.oneAcceptedAt,'API accepted 1'],['bool-sent-zero',r?.zeroAcceptedAt,'API accepted 0'],['bool-read-zero',r?.zeroSeenAt,'Later poll confirmed 0']]) {
    $(id).textContent = `${verified ? '✓' : '—'} ${label}`; $(id).dataset.verified = String(Boolean(verified));
  }
  $('bool-notes').disabled = !t || busy;
  if (document.activeElement !== $('bool-notes')) $('bool-notes').value = r?.note ?? draftNote;
  $('bool-issue').disabled = !r || busy; $('bool-new').disabled = !r || busy || needsClear(r) || (!r.oneRequestedAt && !r.zeroAcceptedAt && !r.issueAt);
  $('bool-result').textContent = result(r); $('bool-result').className = `pill ${apiCycleComplete(r) ? '' : 'amber'}`;
  const human = savedHumanDecision(t,status)?.value ?? 'unchecked';
  setText('bool-operator-state',human === 'pass' ? 'PASS — YOUR CHECK' : human === 'fail' ? 'FAIL — YOUR CHECK' : r?.oneAcceptedAt ? 'AWAITING YOUR CHECK' : 'NOT CHECKED');
  $('bool-operator-state').className = 'pill manual-result-badge'; $('bool-operator-state').dataset.cardResult = human;
  $('bool-mark-complete').disabled = !canMarkComplete(r); $('bool-mark-incomplete').disabled = !canSetOperatorResult(r) || operatorResult(r) === 'unchecked';
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
  const selectedTag = tag(), guide = commandGuidance(selectedTag), intent = endMode(selectedTag), reviewed = writeIdentity(selectedTag,status);
  confirmWrite(`Confirm checklist write ${value}`, [['Signal',selectedTag.tag_name],['PLC address',selectedTag.device_address],['Current value',valueText(poll?.[selectedTag.tag_name])],['New value',value],['After 1',modeLabel(intent)],['Hold/reset rule',guide.title],['Meaning',value === 1 ? guide.one : guide.zero],['Operation','One write only. No automatic pulse, clear or retry.']], async () => {
    if (!reviewed || writeIdentity(tag(),status) !== reviewed || !canSend(value) || (value === 1 && endMode() !== intent)) return;
    const r = !latest() || (value === 1 && (latest().oneRejectedAt || latest().zeroOnlyCleanup)) ? create(selectedTag) : latest(), started = now();
    if (value === 1) Object.assign(r, {endMode:intent, endModeConfirmedAt:started, zeroRequestedAt:null, oneRequestedAt:started, oneBaselineUtc:status?.supplier_timestamp_utc, oneCommandBaselineUtc:null, zeroCommandBaselineUtc:null, feedbackState:'SENDING', feedbackStoppedAt:null, feedback_elapsed_ms:null, zeroAcceptedAt:null, zeroServerAt:null, zeroSeenAt:null});
    if (value === 0) {
      startClear(r,started);
    }
    event(r, `Write ${value} requested`, {value, end_mode:r.endMode ?? null, end_mode_confirmed_at:r.endModeConfirmedAt ?? null, zero_requested_at:r.zeroRequestedAt ?? null, zero_baseline_supplier_timestamp_utc:value === 0 ? r.zeroBaselineUtc : null}); busy = true; render();
    try {
      const response = await post('/api/write', {tag_name:selectedTag.tag_name, value});
      if (response.written !== true) throw new Error('Supplier did not confirm written=true; inspect the physical state before retrying.');
      const receiptAddress = response.console_command_address ?? response.device_address;
      if (receiptAddress !== r.address) throw new Error('Write receipt address does not match the confirmed PLC address. Inspect the command before retrying.');
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
        clearDispatched(r);
        if (r.feedbackState === 'CLEARING') completionResult = 'CLEARED BEFORE COMPLETION';
      }
      event(r, `API accepted ${value}`, {value, http_status:200, written:true, api_elapsed_ms:now() - started, console_accepted_at:response.console_accepted_at, console_command_baseline_utc:response.console_command_baseline_utc ?? null, feedback_baseline:response.console_feedback_baseline});
      if (completionResult) stopFeedback(r, completionResult);
    } catch (error) {
      if (value === 1 && error.writeDispatched === false) { r.oneRejectedAt = now(); r.finishedAt = now(); }
      event(r, `Write ${value} ${error.writeDispatched === false ? 'blocked before dispatch' : 'outcome requires review'}: ${error.message}`, {value, http_status:error.status ?? null, write_dispatched:error.writeDispatched, api_elapsed_ms:now() - started});
      if (value === 1) stopFeedback(r, error.writeDispatched === false ? 'BLOCKED' : 'OUTCOME UNKNOWN');
      if (value === 0 && r.feedbackState === 'CLEARING') {
        if (error.writeDispatched === false) { clearBlocked(r); event(r, 'Clear blocked before dispatch; completion observation continues'); }
        else { clearDispatched(r); stopFeedback(r, 'CLEAR OUTCOME UNKNOWN'); }
      }
    } finally { if (value === 0) releaseClear(r); busy = false; persist(); render(); changed(); }
  });
  const details = node('details'), summary = node('summary','','Rule and source');
  details.append(summary,node('p','',guide.evidence),node('p','',guide.procedure)); $('confirm-body').append(details);
}
function feedbackTarget(test) {
  return tags.find(t => t.tag_name === test?.command_tag && test.command_value === 1);
}
export function latestFeedbackRecord(test) {
  const t = feedbackTarget(test);
  if (!t || storageKey !== `plc-command-checklist:v1:${status?.mode}:${status?.api_address}`) return null;
  return records.findLast(r => r.tag_name === t.tag_name && r.address === t.device_address && !r.zeroOnlyCleanup &&
    (!r.feedbackTestId || r.feedbackTestId === test.id) && (!r.feedbackScope || r.feedbackScope === storageKey)) ?? null;
}
function knownRecord(r) {
  return Boolean(storageKey && r && records.includes(r) &&
    tags.some(t => t.tag_name === r.tag_name && t.device_address === r.address));
}
function knownFeedbackRecord(r) { return knownRecord(r) && r.feedbackScope === storageKey; }
export function canSetOperatorResult(r = latest()) {
  return Boolean(knownRecord(r) && !busy && r.oneAcceptedAt && !r.zeroOnlyCleanup);
}
export function setOperatorResult(r, value) {
  if (!canSetOperatorResult(r) || !['unchecked','pass','fail'].includes(value)) return false;
  const previous = {previous_operator_result:operatorResult(r), previous_operator_result_at:r.operatorResultAt ?? r.operatorCompletedAt ?? r.issueAt ?? null,
    previous_operator_completed_at:r.operatorCompletedAt ?? null, previous_issue_at:r.issueAt ?? null}, at = now();
  // A result correction must not resume automatic Hold after an issue.
  if (r.issueAt || value === 'fail') r.holdInterruptedAt ??= r.issueAt ?? at;
  Object.assign(r, {operatorResult:value, operatorResultAt:at, operatorCompletedAt:value === 'pass' ? at : null, issueAt:value === 'fail' ? at : null});
  event(r, value === 'pass' ? 'Operator marked test complete' : value === 'fail' ? 'Operator recorded an issue' : 'Operator removed test completion',
    {operator_result:value, operator_result_at:at, operator_completed_at:r.operatorCompletedAt, ...previous, write_sent:false});
  render(); changed(); return true;
}
export function canMarkComplete(r = latest()) { return canSetOperatorResult(r) && !operatorComplete(r); }
export function markComplete(r = latest()) { return canMarkComplete(r) && setOperatorResult(r,'pass'); }
export function markIncomplete(r = latest()) { return operatorResult(r) !== 'unchecked' && setOperatorResult(r,'unchecked'); }
export function canStartFeedbackTest(test) {
  const t = feedbackTarget(test);
  return Boolean(t && storageKey && !busy && healthy() && poll?.timestamp === status.supplier_timestamp &&
    poll[t.tag_name] === 0 && !conflictingRecord(t,test.feedback_tag) && !needsClear(latest(t)));
}
export function beginFeedbackTest(test, mode = 'manual0', timeoutMs = test?.timeout_ms) {
  if (!canStartFeedbackTest(test) || !['manual0','hold'].includes(mode) || (mode === 'hold' && /door/i.test(test.command_tag)) ||
      !Number.isInteger(timeoutMs) || timeoutMs < 1000 || timeoutMs > 300000) return null;
  const r = create(feedbackTarget(test), '', mode), started = now();
  Object.assign(r, {source:'Feedback tests', feedbackScope:storageKey, feedbackTestId:test.id,
    mappingUnderTest:Boolean(test.requires_confirmation), timeout_ms:timeoutMs, feedback_tag:test.feedback_tag, feedback_expected:test.expected_feedback,
    endModeConfirmedAt:started, oneRequestedAt:started, oneBaselineUtc:status.supplier_timestamp_utc, feedbackState:'SENDING'});
  event(r, 'Feedback test requested', {test_id:test.id, mapping_under_test:r.mappingUnderTest, end_mode:mode, timeout_ms:timeoutMs});
  feedbackTests.add(r); render(); return r;
}
export function finishFeedbackTest(r, response, error = null) {
  if (!r || !feedbackTests.has(r)) return;
  try {
    if (!knownFeedbackRecord(r)) return;
    if (typeof response?.run_id === 'string') r.backendRunId = response.run_id;
    const receipt = response?.write_response;
    if (receipt?.written === true && response.command_address === r.address) {
      Object.assign(r, {oneAcceptedAt:now(), oneServerAt:receipt.console_accepted_at,
        oneCommandBaselineUtc:receipt.console_command_baseline_utc ?? null, feedback_baseline_utc:receipt.console_command_baseline_utc ?? null});
      r.mappingUnderTest ||= response.mapping_under_test === true;
      event(r, 'Feedback test write accepted', {written:true, console_accepted_at:r.oneServerAt,
        console_command_baseline_utc:r.oneCommandBaselineUtc, backend_result:response.result, backend_elapsed_ms:response.elapsed_ms,
        mapping_under_test:r.mappingUnderTest, end_mode:r.endMode, backend_run_id:r.backendRunId ?? null});
      if (feedbackClears.has(r)) {
        deferredFeedback.set(r,{response,receivedAt:now()});
        event(r,'API feedback received while manual 0 is pending',{backend_result:response.result,backend_run_id:r.backendRunId ?? null});
      } else if (r.feedbackInterruptedByClearAt) {
        event(r,'API feedback retained after manual clear; completion not awarded',{backend_result:response.result,backend_run_id:r.backendRunId ?? null});
      } else applyFeedbackResult(r,response);
    } else {
      const rejected = receipt?.written !== true && (response?.write_dispatched === false || error?.writeDispatched === false);
      if (rejected) { r.oneRejectedAt = now(); r.finishedAt = now(); if (r.zeroRequestedAt) r.zeroOnlyCleanup = true; }
      if (!feedbackClears.has(r) && !r.feedbackInterruptedByClearAt) stopFeedback(r, rejected ? 'BLOCKED' : 'OUTCOME UNKNOWN', {reason:error?.message ?? response?.error ?? 'No matching accepted write receipt', backend_result:response?.result ?? null, backend_run_id:r.backendRunId ?? null});
      else {
        if (feedbackClears.has(r)) deferredFeedback.set(r,{response,error,receivedAt:now(),failure:rejected ? 'BLOCKED' : 'OUTCOME UNKNOWN'});
        event(r,'Feedback request outcome retained after clear intent',{backend_result:response?.result ?? null,backend_run_id:r.backendRunId ?? null});
      }
    }
  } finally { feedbackTests.delete(r); if (knownRecord(r)) finish(r); else deferredFeedback.delete(r); persist(); render(); changed(); }
}
function clearTarget(target) {
  return typeof target === 'string' ? tags.find(t => t.tag_name === target) : knownRecord(target) ? tags.find(t => t.tag_name === target.tag_name && t.device_address === target.address) : null;
}
export function canStartFeedbackClear(target) {
  const t = clearTarget(target), r = latest(t);
  if (!t || !storageKey || busy || feedbackClears.has(r) || clearConflicts(t) || !healthy() || poll?.timestamp !== status.supplier_timestamp || ![0,1].includes(poll?.[t.tag_name])) return false;
  if (poll[t.tag_name] === 0 && !needsClear(r)) return false;
  if (r?.zeroAcceptedAt && !r.zeroSeenAt && [r.zeroServerAt,r.zeroBaselineUtc,r.zeroCommandBaselineUtc].every(stamp => Number.isFinite(Date.parse(stamp)))) return false;
  try { validate(t, '0'); return true; } catch { return false; }
}
export function beginFeedbackClear(target) {
  if (!canStartFeedbackClear(target)) return null;
  const t = clearTarget(target);
  let r = latest(t);
  if (!needsClear(r)) {
    r = create(t, '', 'manual0');
    Object.assign(r, {source:'Manual cleanup', zeroOnlyCleanup:true, feedback_tag:null, feedbackState:'CLEARING'});
  }
  startClear(r);
  event(r, r.zeroOnlyCleanup ? 'Manual cleanup 0 requested; no write 1 recorded' : 'Feedback test manual 0 requested', {value:0, zero_requested_at:r.zeroRequestedAt, end_mode:r.endMode, zero_only_cleanup:Boolean(r.zeroOnlyCleanup)});
  busy = true; render(); return r;
}
export function finishFeedbackClear(r, response, error = null) {
  if (!r || !feedbackClears.has(r)) return;
  try {
    if (!knownRecord(r)) return;
    const address = response?.console_command_address ?? response?.device_address;
    if (response?.written === true && address === r.address) {
      Object.assign(r, {zeroAcceptedAt:now(), zeroServerAt:response.console_accepted_at,
        zeroCommandBaselineUtc:response.console_command_baseline_utc ?? null, zeroSeenAt:null, zeroApiElapsedMs:now()-r.zeroRequestedAt});
      event(r, r.zeroOnlyCleanup ? 'Manual cleanup 0 accepted' : 'Feedback test manual 0 accepted', {value:0, written:true, console_accepted_at:r.zeroServerAt,
        console_command_baseline_utc:r.zeroCommandBaselineUtc, api_elapsed_ms:r.zeroApiElapsedMs});
      clearDispatched(r);
      if (r.zeroOnlyCleanup) stopFeedback(r, 'CLEAR ACCEPTED');
      else if (r.feedbackState === 'CLEARING') stopFeedback(r, 'CLEARED BEFORE COMPLETION');
    } else {
      event(r, r.zeroOnlyCleanup ? 'Manual cleanup 0 requires review' : 'Feedback test manual 0 requires review', {value:0, reason:error?.message ?? 'No matching accepted clear receipt', write_dispatched:error?.writeDispatched});
      if (r.zeroOnlyCleanup) stopFeedback(r, error?.writeDispatched === false ? 'CLEAR BLOCKED' : 'CLEAR OUTCOME UNKNOWN');
      else if (r.feedbackState === 'CLEARING') {
        if (error?.writeDispatched === false) clearBlocked(r);
        else { clearDispatched(r); stopFeedback(r, 'CLEAR OUTCOME UNKNOWN'); }
      }
    }
  } finally { releaseClear(r); busy = false; persist(); render(); changed(); }
}
export function updateChecklist(nextTags, nextPoll, nextStatus, nextCases, catalog) {
  if (catalog) { catalogLoaded = catalog.loaded; catalogError = catalog.error; }
  if (nextTags) { if (tag()?.device_address !== nextTags.find(t => t.tag_name === selected)?.device_address) draftMode = 'manual0'; tags = nextTags.filter(t => t.read_write === 'W' && t.data_type === 'Bool').sort((a,b) => a.tag_name.localeCompare(b.tag_name)); buildList(); }
  if (nextPoll) poll = nextPoll;
  if (nextStatus) status = nextStatus;
  if (nextCases) cases = nextCases;
  if (status?.mode && status?.api_address) {
    const key = `plc-command-checklist:v1:${status.mode}:${status.api_address}`;
    if (key !== storageKey) {
      storageKey = key; records = []; draftMode = 'manual0';
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
      if (r.zeroAcceptedAt && !r.zeroSeenAt && tags.some(t => t.tag_name === r.tag_name && t.device_address === r.address) && poll[r.tag_name] === 0 && Number.isFinite(stamp) && stamp > Date.parse(r.zeroServerAt) && stamp > Date.parse(r.zeroBaselineUtc) && stamp > Date.parse(r.zeroCommandBaselineUtc)) {
        r.zeroSeenAt = now(); event(r, 'Later supplier poll verified command 0', {supplier_timestamp_utc:status.supplier_timestamp_utc}); finish(r);
      }
    }
  }
  for (const r of records) {
    if (r.endMode === 'hold' && r.endModeConfirmedAt && !r.zeroRequestedAt && !r.issueAt && !r.holdInterruptedAt) keepAtOne(r, true);
  }
  render();
}
function download(format) {
  const summary = tags.map(t => {
    const decision = savedHumanDecision(t,status), r = latest(t), human = decision?.value ?? 'unchecked';
    return {tag_name:t.tag_name,address:t.device_address,result:human === 'pass' ? 'COMPLETE' : human === 'fail' ? 'ISSUE' : r?.oneRejectedAt ? 'BLOCKED' : 'NOT CHECKED',
      operator_result:human,operator_result_at:decision?.record?.operatorResultAt ?? decision?.record?.operatorCompletedAt ?? decision?.record?.issueAt ?? decision?.at ?? null,
      operator_completed_at:human === 'pass' ? decision?.record?.operatorCompletedAt ?? decision?.at : null,
      api_result:result(r),api_cycle_complete:apiCycleComplete(r),api_check_status:apiCheckFor(t,status).api_status,
      end_mode:r?.endMode ?? null,current_value:poll?.[t.tag_name] ?? null};
  });
  let content, type;
  if (format === 'json') { content = JSON.stringify({exported_at:new Date().toISOString(), mode:status?.mode, api_address:status?.api_address, checklist:summary, attempts:records, manual_decisions:manualDecisions(status)}, null, 2); type = 'application/json'; }
  else {
    const columns = ['tag_name','address','attempt_id','result','operator_result','operator_result_at','operator_completed_at','api_result','api_cycle_complete','api_check_status','at','elapsed_ms','since_send_1_ms','end_mode','end_mode_confirmed_at','zero_requested_at','automatic_local_record','source','mapping_under_test','timeout_ms','backend_run_id','backend_result','backend_elapsed_ms','feedback_result','feedback_elapsed_ms','action','value','api_elapsed_ms','http_status','written','console_accepted_at','console_command_baseline_utc','supplier_timestamp_utc','zero_baseline_supplier_timestamp_utc','Remote','Local','command_value','feedback_tag','feedback_value','supplier_timestamp','note'];
    const entries = records.flatMap(r => r.events.map(e => ({tag_name:r.tag_name,address:r.address,attempt_id:r.id,result:operatorStatus(r),operator_result:operatorResult(r),operator_result_at:r.operatorResultAt ?? r.operatorCompletedAt ?? r.issueAt ?? null,operator_completed_at:r.operatorCompletedAt ?? null,api_result:result(r),api_cycle_complete:apiCycleComplete(r),api_check_status:apiCheckFor(tags.find(t=>t.tag_name===r.tag_name),status).api_status,end_mode:r.endMode ?? null,end_mode_confirmed_at:r.endModeConfirmedAt ?? null,zero_requested_at:r.zeroRequestedAt ?? null,source:r.source ?? null,mapping_under_test:r.mappingUnderTest ?? null,timeout_ms:r.timeout_ms ?? null,backend_run_id:r.backendRunId ?? null,note:r.note,...e})));
    for (const item of summary) if (!latest(tags.find(t => t.tag_name === item.tag_name))) entries.push({...item, action:item.api_check_status==='checked' ? 'API pass; no local write attempt' : item.api_check_status==='failed' ? 'API first pass failed; no local write attempt' : 'Not tested'});
    const cell = value => { let s = String(value ?? ''); if (typeof value === 'string' && /^[=+@\-\t\r]/.test(s)) s = "'" + s; return '"' + s.replaceAll('"','""') + '"'; };
    content = [columns.join(','), ...entries.map(e => columns.map(k => cell(e[k])).join(','))].join('\r\n'); type = 'text/csv';
  }
  const url = URL.createObjectURL(new Blob([content], {type})), link = document.createElement('a'); link.href = url; link.download = `plc-command-checklist-${new Date().toISOString().slice(0,10)}.${format}`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function initChecklist(onChange) {
  changed = onChange; buildList();
  const holdHint = node('span', 'command-mode-badge hidden', 'Hint'), manualConfirmed = node('span', 'command-mode-badge confirmed hidden', 'Confirmed');
  holdHint.id = 'bool-hold-hint'; holdHint.title = 'Manual suggests Hold 1. Confirm the rule.';
  manualConfirmed.id = 'bool-manual-confirmed'; manualConfirmed.title = 'Tank 01 procedure confirmed by the operator.';
  $('bool-mode-hold').closest('label').append(holdHint); $('bool-mode-manual').closest('label').append(manualConfirmed);
  const guide = node('section', 'command-rule hidden'); guide.id = 'bool-guidance'; guide.setAttribute('aria-labelledby', 'bool-rule-title');
  const title = node('h3'), evidence = node('p'), one = node('dd'), zero = node('dd'), procedure = node('p'), meanings = node('dl');
  title.id = 'bool-rule-title'; evidence.id = 'bool-rule-evidence'; one.id = 'bool-rule-one'; zero.id = 'bool-rule-zero'; procedure.id = 'bool-rule-procedure';
  meanings.append(node('dt', '', 'Value 1'), one, node('dt', '', 'Value 0'), zero);
  const details = node('details'), summary = node('summary','','Procedure and source'); details.id = 'bool-rule-details';
  details.append(summary,procedure,evidence); guide.append(title,meanings,details); $('bool-feedback').after(guide);
  window.addEventListener('pagehide', () => {
    for (const r of records) {
      if (r.feedbackState === 'WAITING') stopFeedback(r, 'MONITORING INTERRUPTED', {reason:'Page left before completion was observed'});
    }
  });
  for (const id of ['bool-search','bool-group','bool-filter','bool-api-filter']) $(id).addEventListener('input', render);
  $('bool-choose-another').addEventListener('click', () => {
    const input = $('bool-search'); input.focus({preventScroll:true}); input.scrollIntoView({block:'center'});
  });
  for (const id of ['bool-mode-hold','bool-mode-manual']) $(id).addEventListener('change', () => {
    if (!tag() || busy || modeLocked() || (/door/i.test(tag().tag_name) && $(id).value === 'hold')) { render(); return; }
    draftMode = $(id).value; render();
  });
  $('bool-one').addEventListener('click', () => send(1)); $('bool-zero').addEventListener('click', () => send(0));
  $('bool-mark-complete').addEventListener('click', () => markComplete()); $('bool-mark-incomplete').addEventListener('click', () => markIncomplete());
  $('bool-notes').addEventListener('input', () => { if (!tag()) return; draftNote = $('bool-notes').value; const r = latest() ?? create(tag()); r.note = draftNote; persist(); });
  $('bool-notes').addEventListener('change', () => { const r = latest(); if (r) event(r, 'Operator notes updated'); });
  $('bool-keep').addEventListener('click', () => {
    const r = latest(); if (r?.endMode) return;
    keepAtOne(r); render();
  });
  $('bool-issue').addEventListener('click', () => {
    const r = latest(); if (!r || busy) return;
    if (canSetOperatorResult(r)) { setOperatorResult(r,'fail'); return; }
    const at = now(), previous = r.operatorCompletedAt; r.operatorCompletedAt = null; r.issueAt = at; r.holdInterruptedAt ??= at;
    event(r, 'Operator recorded an issue', {operator_result:'fail', operator_result_at:at, operator_completed_at:null, previous_operator_completed_at:previous ?? null, write_sent:false});
    finish(r); render(); changed();
  });
  $('bool-new').addEventListener('click', () => { if (tag() && !busy && !$('bool-new').disabled) { draftNote = ''; draftMode = latest()?.endMode === 'hold' && !/door/i.test(tag().tag_name) ? 'hold' : 'manual0'; create(tag()); render(); } });
  $('bool-export-csv').addEventListener('click', () => download('csv')); $('bool-export-json').addEventListener('click', () => download('json'));
  setInterval(() => { $('bool-timer').textContent = feedbackTimer(latest()); }, 100);
}
