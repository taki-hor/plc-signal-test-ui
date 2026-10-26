import {savedHumanDecision} from './saved-results.js';
import {apiFilterMatches, renderApiBadge, renderSavedResults} from './api-checks.js';
import {$, node, groupFor, fillGroups, valueText, setText} from './dom.js';
import {post, request, modeEnabled} from './api.js';
import {confirmWrite, validate} from './controls.js';
import {beginWriteObservation, finishWriteObservation} from './write-feedback.js';
import {commandGuidance} from './command-guidance.js';
import {canStartFeedbackTest, beginFeedbackTest, finishFeedbackTest, beginFeedbackClear, finishFeedbackClear, pendingCommandNames, canStartFeedbackClear, operatorStatus, operatorResult, canSetOperatorResult, setOperatorResult, activeCommandNames, commandIntent} from './command-checklist.js';
let cases = [], tags = [], status = null, poll = null, clearing = false, clearAttempt = null, activeAttempt = null;
const attempts = [], attemptOptions = new Map(), inventoryRows = new Map(), cardIndicators = new Map();
let selectedTestTank = 'all', selectedTestId = null;
function humanDecision(test) { return savedHumanDecision(tags.find(tag => tag.tag_name === test?.command_tag),status,test); }
function humanResult(test) { return humanDecision(test)?.value ?? 'unchecked'; }
function selectedTimeout() {
  const input = $('test-timeout'), seconds = Number(input.value);
  return input.validity.valid && Number.isInteger(seconds) && seconds >= 1 && seconds <= 300 ? seconds * 1000 : null;
}
export function updateVerifier(nextCases, nextStatus, nextPoll, nextTags) {
  if (nextTags) tags = nextTags;
  if (nextCases) { cases = nextCases; renderCases(); }
  if (nextStatus) status = nextStatus;
  if (nextPoll) poll = nextPoll;
  const timeout = selectedTimeout();
  $('test-timeout').oninput = () => updateVerifier();
  $('test-timeout').setAttribute('aria-invalid',String(timeout === null));
  setText('test-timeout-hint',timeout === null ? 'Enter a whole number from 1 to 300.' : '1–300 seconds. Applies to the next test.');
  for (const value of $('test-list').querySelectorAll('[data-wait-limit]')) {
    const label = timeout === null ? '—' : `${timeout / 1000} s`;
    if (value.textContent !== label) value.textContent = label;
  }
  $('test-search').oninput = () => updateVerifier(); $('test-result-filter').onchange = () => updateVerifier();
  $('test-choose-another').onclick = () => { const search = $('test-search'); search.focus({preventScroll:true}); search.scrollIntoView({block:'center'}); };
  $('test-api-filter').onchange = filterCases;
  $('test-tank-select').onchange = () => { selectedTestTank = $('test-tank-select').value; filterCases(); };
  $('test-clear-filters').onclick = () => { $('test-search').value = ''; $('test-result-filter').value = 'all'; $('test-api-filter').value='all'; selectedTestTank = 'all'; $('test-tank-select').value = 'all'; updateVerifier(); };
  for (const button of $('test-list').querySelectorAll('[data-run-test]')) {
    const test = cases.find(test => test.id === button.closest('[data-test-id]').dataset.testId), reason = runUnavailableReason(test);
    button.disabled = Boolean(reason); button.title = reason || 'Review and confirm this test.';
    setText(`test-run-reason-${test.id}`,reason);
  }
  observeHold(); observeClear(); renderAttempts(); renderInventory(); renderSelectedPair(); renderResult(); renderClear(); renderCardResults(); filterCases();
}
function attemptPhase(attempt) {
  return attempt.running ? 'RUNNING' : attempt.error ? (attempt.error.writeDispatched === false ? 'BLOCKED' : 'COMMUNICATION ERROR') : attempt.result?.result ?? 'OUTCOME UNKNOWN';
}
function renderAttempts() {
  const select = $('test-attempt-select');
  for (const attempt of attempts) {
    let option = attemptOptions.get(attempt.id);
    if (!option) {
      option = node('option'); option.value = attempt.id; option.dataset.runId = attempt.id; option.dataset.caseId = attempt.test.id;
      attemptOptions.set(attempt.id,option); select.append(option);
    }
    const label = `${attemptPhase(attempt)} · ${attempt.test.name}`;
    if (option.textContent !== label) option.textContent = label;
  }
  const empty = select.querySelector('option[value=""]');
  if (empty) empty.textContent = attempts.length ? 'Choose a run' : 'No runs yet';
  select.disabled = !attempts.length; if (document.activeElement !== select) select.value = activeAttempt?.id ?? '';
  select.onchange = () => { activeAttempt = attempts.find(attempt => attempt.id === select.value) ?? null; if (activeAttempt) selectedTestId = activeAttempt.test.id; updateVerifier(); };
  const waiting = attempts.filter(attempt => attempt.running).length;
  setText('test-attempt-count',`${waiting} waiting · ${attempts.length} ${attempts.length === 1 ? 'run' : 'runs'}`);
}
function renderInventory() {
  const boolTags = tags.filter(tag => tag.read_write === 'W' && tag.data_type === 'Bool');
  const ones = boolTags.filter(tag => poll?.[tag.tag_name] === 1).map(tag => tag.tag_name), pending = pendingCommandNames(), active = activeCommandNames();
  const names = [...new Set([...ones,...active])];
  $('test-active-commands').classList.toggle('hidden',!names.length && !clearAttempt);
  const label = `${freshPoll() ? 'Commands currently 1' : 'Last command readbacks 1 — stale/unverified'}: ${ones.join(', ') || 'none'}${pending.length ? `. Pending manual clear: ${pending.join(', ')}` : ''}${active.length ? `. Recorded requests: ${active.join(', ')}` : ''}`;
  if ($('test-active-command-list').textContent !== label) $('test-active-command-list').textContent = label;
  for (const [name,row] of inventoryRows) if (!names.includes(name)) { row.element.remove(); inventoryRows.delete(name); }
  for (const name of names) {
    let row = inventoryRows.get(name);
    if (!row) {
      const element = node('div','test-command-row'), title = node('code','test-command-name',name), intent = node('span','test-status command-intent'), value = node('span','command-readback'), button = node('button','button small secondary','Send 0…');
      element.dataset.clearTag = name; button.dataset.clearCommand = name; button.type = 'button'; button.setAttribute('aria-label',`Send 0 to ${name}`); button.onclick = () => sendZero(name);
      element.append(title,intent,value,button); $('test-active-command-rows').append(element);
      row = {element,intent,value,button}; inventoryRows.set(name,row);
    }
    const recorded = commandIntent(name), intentLabel = recorded?.held ? 'Recorded Hold 1' : recorded?.clearRequested ? 'Needs 0' : recorded?.waiting ? 'Waiting for API' : recorded?.pending ? 'Needs 0' : active.includes(name) ? 'Needs review' : 'Untracked 1';
    if (row.intent.textContent !== intentLabel) row.intent.textContent = intentLabel;
    row.intent.dataset.intent = recorded?.held ? 'held' : recorded?.pending ? 'pending' : active.includes(name) ? 'review' : 'untracked';
    row.intent.title = recorded ? `Recorded plan: ${recorded.endMode === 'hold' ? 'Hold 1' : recorded.endMode === 'manual0' ? 'Manual 0' : 'Unclassified'} · Source: ${recorded.source}. This is request intent, not physical state.` : active.includes(name) ? 'An unresolved request has different or missing current metadata. Inspect its captured address before clearing.' : 'No recorded test intent for this readback.';
    const readback = `${freshPoll() ? '' : 'STALE · '}Readback ${valueText(poll?.[name])}`;
    if (row.value.textContent !== readback) row.value.textContent = readback;
    row.button.disabled = !canClearTarget(name);
  }
}

function filterCases() {
  const query = $('test-search').value.trim().toLowerCase(), result = $('test-result-filter').value;
  let visible = 0;
  for (const test of cases) {
    const item = cardIndicators.get(test.id); if (!item) continue;
    const tag = tags.find(tag => tag.tag_name === test.command_tag), human = humanResult(test);
    const match = (selectedTestTank === 'all' || item.card.dataset.caseTank === selectedTestTank) &&
      (result === 'all' || human === result) && apiFilterMatches(tag,$('test-api-filter').value,human,status) &&
      [test.name,test.command_tag,test.feedback_tag,tag?.description,tag?.device_address].some(value => String(value ?? '').toLowerCase().includes(query));
    item.card.classList.toggle('hidden',!match); if (match) visible++;
  }
  const label = selectedTestTank === 'all' ? 'All groups' : selectedTestTank.replace('Tank','Tank ');
  setText('test-tank-count',`${label} · ${visible} of ${cases.length} pairs`);
  $('test-case-empty').classList.toggle('hidden',visible > 0);
}
function selectedTest() { return cases.find(test => test.id === selectedTestId); }
function selectTest(id, review = false) {
  if (!cases.some(test => test.id === id)) return;
  if (selectedTestId !== id) activeAttempt = attempts.findLast(attempt => attempt.test.id === id) ?? null;
  selectedTestId = id; updateVerifier();
  if (review) {
    const preview = $('test-selected-pair'), rect = preview.getBoundingClientRect();
    preview.focus({preventScroll:true}); if (rect.bottom < 0 || rect.top > innerHeight) preview.scrollIntoView({block:'start'});
  }
}
function renderSelectedPair() {
  const test = selectedTest(), tag = tags.find(tag => tag.tag_name === test?.command_tag), button = $('test-run-selected');
  setText('test-coverage-count',`${cases.length} feedback pairs`);
  setText('test-selected-name',test?.name ?? 'Select a test pair');
  setText('test-selected-description',tag?.description ?? 'Selecting a pair sends no command.');
  setText('test-selected-command',test ? `${test.command_tag} = ${test.command_value}` : '—');
  setText('test-selected-feedback',test ? `${test.feedback_tag} = ${test.expected_feedback}` : '—');
  setText('test-selected-address',tag?.device_address ?? '—');
  setText('test-selected-live',test ? `Command ${valueText(poll?.[test.command_tag])} · Feedback ${valueText(poll?.[test.feedback_tag])}${freshPoll() ? '' : ' · STALE / NO DATA'}` : '—');
  setText('test-selected-mapping',!test ? 'No pair selected' : test.requires_confirmation ? 'Mapping under test' : 'Local pair');
  $('test-selected-mapping').dataset.state = test?.requires_confirmation ? 'MAPPING UNDER TEST' : 'CONFIGURED';
  const human = humanResult(test);
  renderApiBadge($('test-selected-api'),tag,status); renderSavedResults($('test-saved-results'),tag,status);
  setText('test-selected-human',human === 'pass' ? 'Operator verified: Pass' : human === 'fail' ? 'Operator observed: Fail' : 'Your result: Not checked');
  $('test-selected-human').dataset.result = human;
  const guide = commandGuidance(tag);
  setText('test-selected-mode',test ? `After 1 suggestion: ${guide.hint === 'hold' ? 'Hold 1' : 'Manual 0'}. Review the source and mode in the confirmation.` : '');
  setText('test-selected-source',test?.requires_confirmation ? 'The tag table lists these signals separately. This pair is inferred. The reviewed docs do not specify pair behavior, polarity, timing or reset rules.' : 'The tag table lists these signals separately. This is a local test pair. The reviewed docs do not specify pair behavior, polarity, timing or reset rules.');
  const reason = runUnavailableReason(test);
  setText('test-run-hint',reason || 'Ready to run. Review and confirm the command before sending 1.');
  button.disabled = Boolean(reason); button.title = reason; button.onclick = () => { if (test) runTest(test); };
}

function renderTankSelect() {
  const select = $('test-tank-select'), groups = ['all',...new Set(cases.map(test => groupFor({tag_name:test.command_tag})).sort())];
  if (!groups.includes(selectedTestTank)) selectedTestTank = 'all';
  if ([...select.options].map(option => option.value).join('|') !== groups.join('|')) {
    fillGroups(select,cases.map(test => ({tag_name:test.command_tag})));
  }
  if (document.activeElement !== select && select.value !== selectedTestTank) select.value = selectedTestTank;
}
function renderCardResults() {
  for (const test of cases) {
    const item = cardIndicators.get(test.id);
    if (!item) continue;
    const decision = humanDecision(test), result = decision?.value ?? 'unchecked';
    const label = result === 'pass' ? '✓ Pass' : result === 'fail' ? '✕ Fail' : 'Not checked';
    if (item.card.dataset.operatorResult !== result) item.card.dataset.operatorResult = result;
    if (item.badge.textContent !== label) item.badge.textContent = label;
    item.badge.dataset.cardResult = result;
    item.badge.dataset.state = result === 'pass' ? 'COMPLETE' : result === 'fail' ? 'FAIL' : 'NOT CHECKED';
    renderApiBadge(item.api,tags.find(tag=>tag.tag_name===test.command_tag),status);
    item.card.dataset.selected = String(selectedTestId === test.id);
    const stamp = Date.parse(decision?.at);
    item.badge.title = `${result === 'pass' ? 'Operator verified' : result === 'fail' ? 'Operator observed' : 'Your result'}: ${label}${Number.isFinite(stamp) ? ' · '+new Date(stamp).toLocaleString() : ''}`;
    const selected = selectedTestId === test.id; item.card.classList.toggle('selected',selected); item.select.setAttribute('aria-pressed',String(selected));
  }
  const results = cases.map(test => humanResult(test));
  setText('test-result-count',`${results.filter(result => result === 'pass').length} Pass · ${results.filter(result => result === 'fail').length} Fail · ${results.filter(result => result === 'unchecked').length} Not checked`);
}
function renderCases() {
  const list = $('test-list'); list.replaceChildren(); cardIndicators.clear();
  if (!cases.some(test => test.id === selectedTestId)) { selectedTestId = cases[0]?.id ?? null; activeAttempt = null; }
  for (const test of cases) {
    const card = node('div','test-card feedback-case'), heading = node('div','feedback-case-heading');
    card.dataset.testId = test.id; card.dataset.caseTank = groupFor({tag_name:test.command_tag});
    const select = node('button','feedback-case-select'); select.type = 'button'; select.dataset.selectTest = test.id;
    select.append(node('strong','',test.name),node('small','',test.command_tag)); select.onclick = () => selectTest(test.id,true);
    const button = node('button','button small secondary','Run…'); button.type = 'button'; button.dataset.runTest = test.id; button.dataset.needsConfirmation = String(Boolean(test.requires_confirmation));
    button.setAttribute('aria-label',`Run ${test.name}`); button.onclick = () => { selectTest(test.id); runTest(test); };
    heading.append(select,button);
    const marks = node('div','feedback-case-marks'), badge = node('span','test-status',test.requires_confirmation ? 'Mapping under test' : 'Local pair');
    badge.dataset.state = test.requires_confirmation ? 'MAPPING UNDER TEST' : 'CONFIGURED';
    const indicator = node('span','test-status test-card-result','Not checked'); indicator.dataset.cardResult = 'unchecked';
    const api = node('span','api-check-badge','Unchecked');
    marks.append(badge,api,indicator); cardIndicators.set(test.id,{card,badge:indicator,select,api});
    const reason = node('p','sr-only',test.requires_confirmation ? 'Mapping under test. A matching API transition gives OBSERVED. Pair behavior is not specified in the reviewed docs.' : 'Local test pair. Signals are listed separately in the tag table. Pair behavior is not specified in the reviewed docs.');
    const runReason = node('span','sr-only'); runReason.id = `test-run-reason-${test.id}`;
    reason.id = `test-rule-${test.id}`; button.setAttribute('aria-describedby',`${reason.id} ${runReason.id}`);
    card.append(heading,marks,reason,runReason); list.append(card);
  }
  renderTankSelect();
}

function renderResult() {
  if (!activeAttempt) {
    $('test-human-result').classList.add('hidden'); $('test-result-detail').classList.add('hidden');
    $('test-backend-result').classList.add('hidden'); $('test-send-zero').classList.add('hidden'); $('test-send-zero').disabled = true; $('test-send-zero').onclick = null;
    setText('test-observation-timer','—'); setText('test-result-state','No run selected. Review the pair, then run a test when ready.');
    $('test-result-state').dataset.state = 'NOT RUN'; return;
  }
  const {test:activeTest,operation,result,error,running} = activeAttempt;
  const record = operation?.record, sameContext = record && apiContext() === operation.context && currentCommand()?.device_address === record.address;
  $('test-human-result').classList.toggle('hidden',!record);
  const manualResult = operatorResult(record), choice = $('test-operator-result');
  setText('test-operator-state',manualResult === 'pass' ? 'PASS — YOUR CHECK' : manualResult === 'fail' ? 'FAIL — YOUR CHECK' : operatorStatus(record));
  $('test-operator-state').dataset.state = manualResult === 'pass' ? 'COMPLETE' : manualResult === 'fail' ? 'FAIL' : 'NEEDS CONFIRMATION';
  if (document.activeElement !== choice) choice.value = manualResult;
  choice.disabled = running || clearing || !sameContext || !canSetOperatorResult(record);
  choice.onchange = () => {
    if (!running && !clearing && activeAttempt?.operation?.record === record && apiContext() === operation.context) setOperatorResult(record,choice.value);
    choice.value = operatorResult(record); updateVerifier();
  };
  setText('test-observation-timer',`${(Math.max(0,(activeAttempt.finishedAt ?? Date.now())-activeAttempt.startedAt)/1000).toFixed(1)} s`);
  const state = $('test-result-state'), phase = attemptPhase(activeAttempt);
  const label = `${phase} · ${activeTest.name}`;
  if (state.textContent !== label) state.textContent = label;
  state.dataset.state = phase;
  $('test-result-detail').classList.remove('hidden');
  const fresh = Boolean(poll && status?.supplier_api_connected && status.data_fresh && poll.timestamp === status.supplier_timestamp);
  setText('test-active-command',`${activeTest.command_tag} = ${activeTest.command_value}`);
  setText('test-active-timeout',`${(result?.timeout_ms ?? operation?.timeout_ms ?? activeTest.timeout_ms) / 1000} seconds`);
  setText('test-command-readback',valueText(poll?.[activeTest.command_tag]));
  setText('test-expected-feedback',`${activeTest.feedback_tag} = ${activeTest.expected_feedback}`);
  setText('test-live-feedback',`${activeTest.feedback_tag} = ${valueText(poll?.[activeTest.feedback_tag])}`);
  setText('test-live-health',fresh ? 'LIVE · FRESH' : 'STALE / NO DATA');
  $('test-live-health').dataset.state = fresh ? 'CONFIGURED' : 'NEEDS CONFIRMATION';
  setText('test-live-source',`Supplier timestamp: ${poll?.timestamp ?? 'NO DATA'}`);
  $('test-backend-result').classList.toggle('hidden',!result);
  if (result) {
    const diagnostics = [['Command readback','command_readback'],['Remote','Remote'],['Local','Local']]
      .filter(([,key]) => result[key] != null).map(([label,key]) => `${label}: ${valueText(result[key])}`);
    setText('test-backend-result',`Backend result: ${result.result} · Actual feedback: ${valueText(result.actual_feedback)} · Elapsed: ${result.elapsed_ms} ms${diagnostics.length ? ' · '+diagnostics.join(' · ') : ''}`);
  }
  setText('test-result-technical',`HTTP: ${result?.http_status ?? '—'}${result?.error ? ` · ${result.error}` : ''}${error ? ` · ${error.message}` : ''}`);
  $('test-result-error').classList.toggle('hidden',!error && !result?.error);
  setText('test-result-error',error?.message ?? result?.error ?? '');
  const confirmedReset = commandGuidance(currentCommand()).confirmed === true;
  setText('test-operation-mode',`After 1: ${operation?.end_mode === 'hold' ? 'Hold 1' : 'Manual 0'}${operation?.mapping_under_test ? ' · mapping under test; operator choice' : ''}`);
  setText('test-reset-rule',confirmedReset ? `Hold ${activeTest.command_tag}=1 during movement. After physical movement finishes, send 0.` : operation?.mapping_under_test ? 'You choose Hold 1 or Manual 0. The hold/reset procedure is unconfirmed. Value 0 does not guarantee that equipment stops.' : 'This command’s hold/reset procedure is unconfirmed. Manual 0 is your explicitly chosen test plan. Observe physical completion before you clear this command.');
  setText('test-rule-evidence',confirmedReset ? 'The operator confirmed this rule for Tank 01 at M300/M301. The manual does not specify it. The console does not send automatic 0.' : 'The reviewed docs do not specify this hold/reset rule. The selected mode is your test choice. Clearing the request does not guarantee that equipment stops. The console does not send automatic 0.');
  const hold = $('test-hold-state'); hold.classList.toggle('hidden',operation?.end_mode !== 'hold');
  hold.dataset.state = operation?.holdState ?? 'WAITING';
  const holdLabel = operation?.holdState === 'KEPT AT 1' ? `Hold 1 selected. A fresh later readback confirmed 1 at ${operation.heldAt}. The console does not enforce 1.` : `Hold 1: ${operation?.holdState ?? 'WAITING'}. The console needs API acceptance and a fresh later readback of 1.`;
  if (hold.textContent !== holdLabel) hold.textContent = holdLabel;
  const clear = $('test-send-zero'); clear.classList.toggle('hidden',!clearRule()); clear.disabled = !canClear(); clear.onclick = () => sendZero(operation.record);
}
function renderClear() {
  $('test-last-clear').classList.toggle('hidden',!clearAttempt);
  if (!clearAttempt) return;
  setText('test-clear-target',`Last Send 0: ${clearAttempt.tag_name}=0 · ${clearAttempt.address}`);
  const clearState = $('test-clear-state'), clearLabel = clearAttempt.state;
  clearState.classList.toggle('hidden',!clearAttempt);
  if (clearState.textContent !== clearLabel) clearState.textContent = clearLabel;
  clearState.dataset.state = clearAttempt?.state === 'VERIFIED 0' ? 'CONFIGURED' : ['SENDING 0','API ACCEPTED 0 — WAITING FOR READBACK'].includes(clearAttempt?.state) ? 'RUNNING' : 'NEEDS CONFIRMATION';
  $('test-clear-detail').classList.toggle('hidden',!clearAttempt);
  if (clearAttempt) setText('test-clear-detail',clearAttempt.message);
}
function apiContext() { return JSON.stringify([status?.mode,status?.api_address]); }
function currentCommand(attempt = activeAttempt) { return tags.find(tag => tag.tag_name === attempt?.test.command_tag); }
function freshPoll() { return Boolean(poll && status?.supplier_api_connected && status.data_fresh && poll.timestamp === status.supplier_timestamp); }
function canRun(test) {
  const tag = tags.find(item => item.tag_name === test?.command_tag);
  if (!tag || selectedTimeout() === null || clearing || !canStartFeedbackTest(test) || !modeEnabled() || !freshPoll() || status.plc_mode !== 'REMOTE' || poll[tag.tag_name] !== 0) return false;
  try { validate(tag,String(test.command_value)); return true; } catch { return false; }
}
function runUnavailableReason(test) {
  if (canRun(test)) return '';
  if (!test) return 'Select a test pair.';
  const tag = tags.find(item => item.tag_name === test.command_tag);
  if (!tag) return 'Command is missing from the current catalog. Refresh the catalog before testing.';
  if (selectedTimeout() === null) return 'Enter a whole-number wait limit from 1 to 300 seconds.';
  if (!modeEnabled()) return 'Enable write test mode to run this test.';
  if (!freshPoll()) return 'Wait for fresh, matching API data before testing.';
  if (status.plc_mode !== 'REMOTE') return 'PLC Remote/API mode is required to run this test.';
  if (clearing) return 'A Send 0 request is in progress. Wait for its receipt.';
  if (poll[tag.tag_name] === 1) return 'Command is already 1. Review Command bits and send 0 when the confirmed procedure requires it.';
  if (poll[tag.tag_name] !== 0) return 'Command readback must be a verified 0 before this test can start.';
  try { validate(tag,String(test.command_value)); } catch (error) { return `Command cannot be sent: ${error.message}. Refresh its catalog details.`; }
  return 'An active write or pending command blocks this actuator, address or feedback signal. Review its test run and Command bits.';
}
function clearRule() {
  const {operation,result} = activeAttempt ?? {}, tag = currentCommand();
  return Boolean(tag && operation && apiContext() === operation.context && tag.device_address === operation.address &&
    (!result?.command_address || result.command_address === operation.address) &&
    (operation.end_mode === 'manual0' || (operation.end_mode === 'hold' && !/door/i.test(tag.tag_name))));
}
function observeHold() { for (const attempt of attempts) observeAttemptHold(attempt); }
function observeAttemptHold(attempt) {
  const {operation,result,running} = attempt;
  if (operation?.end_mode !== 'hold') return;
  if (apiContext() !== operation.context || currentCommand(attempt)?.device_address !== operation.address || result?.command_address && result.command_address !== operation.address) {
    operation.holdState = 'INTERRUPTED'; return;
  }
  const record = operation.record;
  if (record?.zeroSeenAt) { operation.holdState = 'RELEASED TO 0'; return; }
  if (record?.zeroRequestedAt) { operation.holdState = 'CLEAR REQUESTED'; return; }
  if (running) return;
  if (record?.holdOneAt) { operation.holdState = 'KEPT AT 1'; operation.heldAt = new Date(record.holdOneAt).toISOString(); return; }
  const receipt = result?.write_response;
  operation.holdState = receipt?.written === true && result?.command_address && Number.isFinite(Date.parse(receipt.console_accepted_at)) && Number.isFinite(Date.parse(receipt.console_command_baseline_utc)) ? 'WAITING' : 'UNVERIFIABLE';
}

function canClearTarget(target) {
  const name = typeof target === 'string' ? target : target?.tag_name;
  const tag = tags.find(item => item.tag_name === name && item.read_write === 'W' && item.data_type === 'Bool');
  if (!tag || clearing || !canStartFeedbackClear(target) || !modeEnabled() || !freshPoll() || status.plc_mode !== 'REMOTE' ||
      !status.mode || !status.api_address || !Number.isFinite(Date.parse(status.supplier_timestamp_utc)) || ![0,1].includes(poll[name])) return false;
  try { validate(tag,'0'); return true; } catch { return false; }
}
function canClear() {
  const record = activeAttempt?.operation?.record;
  return Boolean(record?.oneRequestedAt && !record.oneRejectedAt && !record.zeroSeenAt && clearRule() && canClearTarget(record));
}

function observeClear() {
  const attempt = clearAttempt;
  if (!attempt?.acceptedAt || attempt.state !== 'API ACCEPTED 0 — WAITING FOR READBACK') return;
  if (attempt.record?.zeroRequestedAt !== attempt.zeroRequestedAt) {
    attempt.state = 'CLEAR MONITORING INTERRUPTED'; attempt.message = 'A newer Send 0 request replaced this request. Check the latest command record.'; return;
  }
  if (apiContext() !== attempt.context || tags.find(tag => tag.tag_name === attempt.tag_name)?.device_address !== attempt.address) {
    attempt.state = 'CLEAR MONITORING INTERRUPTED'; attempt.message = 'The API or command address changed. Check the equipment and command state before another write.'; return;
  }
  const stamp = Date.parse(status?.supplier_timestamp_utc);
  if (attempt.record?.zeroSeenAt && freshPoll() && status.plc_mode === 'REMOTE' && poll[attempt.tag_name] === 0 &&
      stamp > Date.parse(attempt.browserBaselineUtc) && stamp > Date.parse(attempt.commandBaselineUtc) && stamp > Date.parse(attempt.acceptedAt)) {
    attempt.state = 'VERIFIED 0'; attempt.verifiedAt = status.supplier_timestamp_utc;
    const test = attempts.find(test => test.operation?.record === attempt.record);
    if (test?.operation.end_mode === 'hold') test.operation.holdState = 'RELEASED TO 0';
    attempt.message = `The API accepted ${attempt.tag_name}=0. A fresh later readback confirmed 0 at ${attempt.verifiedAt}. This checks the command bit. It does not confirm a physical position.`;
  }
}
function sendZero(target) {
  if (!canClearTarget(target)) return;
  const name = typeof target === 'string' ? target : target.tag_name;
  const tag = tags.find(item => item.tag_name === name), address = tag.device_address, context = apiContext(), intent = commandIntent(name);
  const plan = intent?.endMode === 'hold' ? 'Hold 1' : intent?.endMode === 'manual0' ? 'Manual 0' : intent?.held ? 'Keep at 1 (legacy record)' : 'Unclassified / no recorded plan';
  confirmWrite('Confirm manual Send 0', [['Signal',name],['PLC address',address],['Current value',poll[name]],['New value',0],
    ['Recorded plan',plan],['Record source',intent?.source ?? 'No browser record — untracked readback'],
    ['Clear meaning','This writes 0 to the command bit. It does not guarantee that equipment stops.'],
    ['Required physical check',/door/i.test(name) ? 'Confirm physical movement has finished before sending 0.' : 'Confirm the observed action and that it is appropriate to clear this request.'],
    ['Operation',`Clear this same command ${name}. The console does not reset or retry automatically.`],['No opposite door command','This write only clears the selected command.']], async () => {
    if (!canClearTarget(target) || tags.find(item => item.tag_name === name)?.device_address !== address || apiContext() !== context) {
      clearAttempt = {tag_name:name,address,context,state:'CLEAR BLOCKED BEFORE DISPATCH',message:'The command or connection changed during confirmation. Check the current state before another write.'}; renderInventory(); renderClear(); return;
    }
    clearing = true;
    clearAttempt = {tag_name:name,address,context,browserBaselineUtc:status.supplier_timestamp_utc,state:'SENDING 0',
      message:`Sending ${name}=0. Waiting for the API receipt.`};
    let observation, sharedRecord, clearResponse = null, clearFailure = null;
    updateVerifier();
    try {
      sharedRecord = beginFeedbackClear(target);
      clearAttempt.record = sharedRecord; clearAttempt.zeroRequestedAt = sharedRecord?.zeroRequestedAt;
      if (!sharedRecord) { const blocked = new Error('The shared command state is busy or changed. The console did not dispatch the clear.'); blocked.writeDispatched = false; throw blocked; }
      observation = beginWriteObservation([{tag_name:name,value:0}]);
      observation.source = typeof target === 'string' ? 'Shared command bar manual Send 0' : 'Feedback tests manual Send 0'; observation.command_browser_baseline_utc = clearAttempt.browserBaselineUtc;
      const response = await post('/api/write',{tag_name:name,value:0}); clearResponse = response;
      finishWriteObservation(observation,response);
      if (response.written !== true) {
        clearAttempt.state = 'CLEAR OUTCOME UNKNOWN'; clearAttempt.message = 'The API did not confirm written=true. Check the equipment and command state before another write.';
      } else {
        const receiptAddress = response.console_command_address ?? response.device_address;
        if (receiptAddress != null && receiptAddress !== address) {
          clearAttempt.state = 'CLEAR OUTCOME UNKNOWN'; clearAttempt.message = 'The receipt has a different command address. Check the equipment and command state before another write.';
        } else {
          clearAttempt.acceptedAt = response.console_accepted_at; clearAttempt.commandBaselineUtc = response.console_command_baseline_utc;
          clearAttempt.state = receiptAddress === address && Number.isFinite(Date.parse(clearAttempt.acceptedAt)) && Number.isFinite(Date.parse(clearAttempt.commandBaselineUtc)) ? 'API ACCEPTED 0 — WAITING FOR READBACK' : 'API ACCEPTED 0 — READBACK UNVERIFIABLE';
          clearAttempt.message = `The API accepted ${name}=0. ${clearAttempt.state.endsWith('UNVERIFIABLE') ? 'The receipt lacks its address or final timestamp. Restart the backend. Check the equipment before another write.' : 'Wait for a fresh later readback of 0.'}`;
        }
      }
    } catch (failure) {
      clearFailure = failure;
      if (observation) finishWriteObservation(observation,null,failure);
      clearAttempt.state = failure.writeDispatched === false ? 'CLEAR BLOCKED BEFORE DISPATCH' : 'CLEAR OUTCOME UNKNOWN';
      clearAttempt.message = `${failure.message}. Review the equipment and command state before another write.`;
    } finally { if (sharedRecord) finishFeedbackClear(sharedRecord,clearResponse,clearFailure); clearing = false; updateVerifier(); }
  });
}

function runTest(test) {
  if (!canRun(test)) return;
  selectedTestId = test.id;
  const tag = tags.find(item => item.tag_name === test.command_tag), address = tag.device_address, context = apiContext(), timeoutMs = selectedTimeout();
  let holdChoice = null;
  confirmWrite(`Confirm ${test.requires_confirmation ? 'mapping under test' : 'feedback test'}`, [['Command',`${test.command_tag}=${test.command_value}`],['PLC address',address],
    ['Expected feedback',`${test.feedback_tag}=${test.expected_feedback}`],['Wait limit',`${timeoutMs / 1000} seconds`],['Mapping',test.requires_confirmation ? 'Under test: the console records matches as OBSERVED, not PASS. The reviewed docs do not specify this mapping behavior.' : 'Local test pair; pair behavior is not specified in the reviewed docs.'],
    ['After 1',/door/i.test(test.command_tag) ? 'Send 0 after physical movement finishes. Confirm any unverified reset rule.' : 'Choose Hold 1 or Manual 0. This records your test plan.'],
    ['Operation','The console sends one command write. It does not send automatic 0, pulses, or retries. Confirm the area and command are ready.']], async () => {
    if (!canRun(test) || selectedTimeout() !== timeoutMs || tags.find(item => item.tag_name === test.command_tag)?.device_address !== address || apiContext() !== context) {
      const error = new Error('The command, wait limit or connection changed during confirmation; no test was dispatched.'); error.writeDispatched = false;
      activeAttempt = {id:crypto.randomUUID(),test,operation:null,result:null,error,running:false,startedAt:Date.now(),finishedAt:Date.now()}; attempts.push(activeAttempt); updateVerifier(); return;
    }
    const endMode = holdChoice?.checked ? 'hold' : 'manual0';
    const record = beginFeedbackTest(test,endMode,timeoutMs);
    if (!record) return;
    const operation = {end_mode:endMode,mapping_under_test:Boolean(test.requires_confirmation),timeout_ms:timeoutMs,address,context,holdState:'WAITING',record};
    const attempt = {id:crypto.randomUUID(),test,operation,result:null,error:null,running:true,startedAt:record.oneRequestedAt ?? Date.now(),finishedAt:null};
    attempts.push(attempt); activeAttempt = attempt; updateVerifier();
    const panel = $('test-result'); panel.focus({preventScroll:true}); panel.scrollIntoView({block:'start'});
    try {
      attempt.result = await request('/api/test/run',{method:'POST',body:JSON.stringify({id:test.id,end_mode:endMode,
        ...(timeoutMs !== test.timeout_ms ? {timeout_ms:timeoutMs} : {}),...(test.requires_confirmation ? {mapping_under_test:true} : {})}),
        signal:AbortSignal.timeout(timeoutMs + 30000)});
    }
    catch (failure) { attempt.error = failure; }
    finally { attempt.running = false; attempt.finishedAt = Date.now(); finishFeedbackTest(record,attempt.result,attempt.error); updateVerifier(); }
  });
  const details = node('details'), summary = node('summary','','Rule source');
  details.append(summary,node('p','',commandGuidance(tag).evidence)); $('confirm-body').append(details);
  if (!/door/i.test(test.command_tag)) {
    const defaultMode = commandGuidance(tag).hint === 'hold' ? 'hold' : 'manual0';
    const mode = node('div','command-mode'), label = node('span','command-mode-label','After 1:'), choices = node('div','command-mode-options');
    mode.id = 'test-end-mode'; label.id = 'test-end-mode-label'; mode.setAttribute('role','group'); mode.setAttribute('aria-labelledby',label.id);
    for (const [value,text] of [['hold','Hold 1'],['manual0','Manual 0']]) {
      const choice = node('label'), input = node('input'); input.type = 'radio'; input.name = 'test-end-mode'; input.value = value; input.id = `test-mode-${value === 'hold' ? 'hold' : 'manual'}`; input.checked = value === defaultMode;
      if (value === 'hold') holdChoice = input;
      choice.append(input,node('span','',text));
      if (value === 'hold' && defaultMode === 'hold') {
        const hint = node('small','command-mode-badge','Hint'); hint.dataset.modeHint = 'hold'; hint.id = 'test-mode-hold-hint';
        hint.title = 'Inferred from the reviewed manual. Hold behavior is not specified there.'; input.setAttribute('aria-describedby',hint.id); choice.append(hint);
      }
      choices.append(choice);
    }
    mode.append(label,choices); $('confirm-body').prepend(mode);
  }
}
