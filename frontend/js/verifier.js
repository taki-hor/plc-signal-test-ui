import {$, node, valueText, setText} from './dom.js';
import {post, modeEnabled} from './api.js';
import {confirmWrite, validate} from './controls.js';
import {beginWriteObservation, finishWriteObservation} from './write-feedback.js';
import {commandGuidance} from './command-guidance.js';
import {canStartFeedbackTest, beginFeedbackTest, finishFeedbackTest, beginFeedbackClear, finishFeedbackClear, pendingCommandNames, canStartFeedbackClear} from './command-checklist.js';
let cases = [], tags = [], status = null, poll = null, running = false, clearing = false, activeTest = null, result = null, error = null, clearAttempt = null, operation = null;
const inventoryRows = new Map();
export function updateVerifier(nextCases, nextStatus, nextPoll, nextTags) {
  if (nextTags) tags = nextTags;
  if (nextCases) { cases = nextCases; renderCases(); }
  if (nextStatus) status = nextStatus;
  if (nextPoll) poll = nextPoll;
  for (const button of $('test-list').querySelectorAll('button')) button.disabled = !canRun(cases.find(test => test.id === button.closest('[data-test-id]').dataset.testId));
  observeHold(); observeClear(); renderInventory(); renderResult(); renderClear();
}
function renderInventory() {
  const boolTags = tags.filter(tag => tag.read_write === 'W' && tag.data_type === 'Bool');
  const ones = boolTags.filter(tag => poll?.[tag.tag_name] === 1).map(tag => tag.tag_name), pending = pendingCommandNames();
  const names = [...new Set([...ones,...pending])].filter(name => boolTags.some(tag => tag.tag_name === name));
  $('test-active-commands').classList.toggle('hidden',!names.length && !clearAttempt);
  const label = `${freshPoll() ? 'Commands currently 1' : 'Last command readbacks 1 — stale/unverified'}: ${ones.join(', ') || 'none'}${pending.length ? `. Pending manual clear: ${pending.join(', ')}` : ''}`;
  if ($('test-active-command-list').textContent !== label) $('test-active-command-list').textContent = label;
  for (const [name,row] of inventoryRows) if (!names.includes(name)) { row.element.remove(); inventoryRows.delete(name); }
  for (const name of names) {
    let row = inventoryRows.get(name);
    if (!row) {
      const element = node('div','test-command-row'), title = node('code','test-command-name',name), value = node('span','test-status'), button = node('button','button small secondary','Send 0…');
      element.dataset.clearTag = name; button.dataset.clearCommand = name; button.type = 'button'; button.setAttribute('aria-label',`Send 0 to ${name}`); button.onclick = () => sendZero(name);
      element.append(title,value,button); $('test-active-command-rows').append(element);
      row = {element,value,button}; inventoryRows.set(name,row);
    }
    const label = poll?.[name] === 1 ? (freshPoll() ? 'Bits at 1' : 'STALE · 1') : 'Pending 0';
    if (row.value.textContent !== label) row.value.textContent = label;
    row.button.disabled = !canClearTarget(name);
  }
}

function renderCases() {
  const list = $('test-list'); list.replaceChildren();
  for (const test of cases) {
    const card = node('div', 'test-card'), row = node('div','row'); card.dataset.testId = test.id;
    const badge = node('span','test-status',test.requires_confirmation ? 'MAPPING UNDER TEST' : 'CONFIGURED'); badge.dataset.state = badge.textContent;
    row.append(node('h3','',test.name),badge);
    const values = node('dl','test-case-values');
    for (const [label,value] of [['Command',`${test.command_tag} = ${test.command_value}`],['Expected feedback',`${test.feedback_tag} = ${test.expected_feedback}`],['Wait limit',`${(test.timeout_ms/1000).toFixed(1)} s`]]) {
      const pair = node('div'); pair.append(node('dt','',label),node('dd','',value)); values.append(pair);
    }
    const button = node('button','button small primary','Run test'); button.type = 'button'; button.dataset.needsConfirmation = String(Boolean(test.requires_confirmation));
    button.addEventListener('click', () => runTest(test)); card.append(row,values);
    if (test.requires_confirmation) {
      const reason = node('p','test-case-note','Mapping under test. A match gives OBSERVED, not PASS. The supplier must confirm the mapping and reset rule.');
      reason.id = `test-rule-${test.id}`; button.setAttribute('aria-describedby',reason.id);
      const details = node('details','test-technical'); details.append(node('summary','','Mapping limits'),reason); card.append(details);
    }
    card.append(button); list.append(card);
  }
}
function renderResult() {
  if (!activeTest) return;
  const state = $('test-result-state'), phase = running ? 'RUNNING' : error ? (error.writeDispatched === false ? 'BLOCKED' : 'COMMUNICATION ERROR') : result.result;
  const label = `${phase} · ${activeTest.name}`;
  if (state.textContent !== label) state.textContent = label;
  state.dataset.state = phase;
  $('test-result-detail').classList.remove('hidden');
  const fresh = Boolean(poll && status?.supplier_api_connected && status.data_fresh && poll.timestamp === status.supplier_timestamp);
  setText('test-active-command',`${activeTest.command_tag} = ${activeTest.command_value}`);
  setText('test-command-readback',valueText(poll?.[activeTest.command_tag]));
  setText('test-expected-feedback',`${activeTest.feedback_tag} = ${activeTest.expected_feedback}`);
  setText('test-live-feedback',`${activeTest.feedback_tag} = ${valueText(poll?.[activeTest.feedback_tag])}`);
  setText('test-live-health',fresh ? 'LIVE · FRESH' : 'STALE / NO DATA');
  $('test-live-health').dataset.state = fresh ? 'CONFIGURED' : 'NEEDS CONFIRMATION';
  setText('test-live-source',`Supplier timestamp: ${poll?.timestamp ?? 'NO DATA'}`);
  $('test-backend-result').classList.toggle('hidden',!result);
  if (result) setText('test-backend-result',`Backend result: ${result.result} · Actual feedback: ${valueText(result.actual_feedback)} · Elapsed: ${result.elapsed_ms} ms`);
  setText('test-result-technical',`HTTP: ${result?.http_status ?? '—'}${result?.error ? ` · ${result.error}` : ''}${error ? ` · ${error.message}` : ''}`);
  $('test-result-error').classList.toggle('hidden',!error && !result?.error);
  setText('test-result-error',error?.message ?? result?.error ?? '');
  const confirmedReset = commandGuidance(currentCommand()).confirmed === true;
  setText('test-operation-mode',`After 1: ${operation?.end_mode === 'hold' ? 'Hold 1' : 'Manual 0'}${operation?.mapping_under_test ? ' · mapping under test; operator choice' : ''}`);
  setText('test-reset-rule',confirmedReset ? `Hold ${activeTest.command_tag}=1 during movement. After physical movement finishes, send 0.` : operation?.mapping_under_test ? 'You choose Hold 1 or Manual 0. The hold/reset procedure is unconfirmed. Value 0 does not guarantee that equipment stops.' : 'This command’s hold/reset procedure is unconfirmed. Manual 0 is your explicitly chosen test plan. Observe physical completion before you clear this command.');
  setText('test-rule-evidence',confirmedReset ? 'The operator confirmed this rule for Tank 01 at M300/M301. The manual does not specify it. The console does not send automatic 0.' : 'The supplier did not confirm this hold/reset rule. The selected mode is your test choice. Clearing the request does not guarantee that equipment stops. The console does not send automatic 0.');
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
function currentCommand() { return tags.find(tag => tag.tag_name === activeTest?.command_tag); }
function freshPoll() { return Boolean(poll && status?.supplier_api_connected && status.data_fresh && poll.timestamp === status.supplier_timestamp); }
function canRun(test) {
  const tag = tags.find(item => item.tag_name === test?.command_tag);
  if (!tag || running || clearing || !canStartFeedbackTest(test) || !modeEnabled() || !freshPoll() || status.plc_mode !== 'REMOTE' || poll[tag.tag_name] !== 0) return false;
  try { validate(tag,String(test.command_value)); return true; } catch { return false; }
}
function clearRule() {
  const tag = currentCommand();
  return Boolean(tag && operation && apiContext() === operation.context && tag.device_address === operation.address &&
    (!result?.command_address || result.command_address === operation.address) &&
    (operation.end_mode === 'manual0' || (operation.end_mode === 'hold' && !/door/i.test(tag.tag_name))));
}
function observeHold() {
  if (operation?.end_mode !== 'hold' || running) return;
  if (apiContext() !== operation.context || currentCommand()?.device_address !== operation.address || result?.command_address && result.command_address !== operation.address) {
    operation.holdState = 'INTERRUPTED'; return;
  }
  const record = operation.record;
  if (record?.zeroSeenAt) { operation.holdState = 'RELEASED TO 0'; return; }
  if (record?.zeroRequestedAt) { operation.holdState = 'CLEAR REQUESTED'; return; }
  if (record?.holdOneAt) { operation.holdState = 'KEPT AT 1'; operation.heldAt = new Date(record.holdOneAt).toISOString(); return; }
  const receipt = result?.write_response;
  operation.holdState = receipt?.written === true && result?.command_address && Number.isFinite(Date.parse(receipt.console_accepted_at)) && Number.isFinite(Date.parse(receipt.console_command_baseline_utc)) ? 'WAITING' : 'UNVERIFIABLE';
}

function canClearTarget(target) {
  const name = typeof target === 'string' ? target : target?.tag_name;
  const tag = tags.find(item => item.tag_name === name && item.read_write === 'W' && item.data_type === 'Bool');
  if (!tag || running || clearing || !canStartFeedbackClear(target) || !modeEnabled() || !freshPoll() || status.plc_mode !== 'REMOTE' ||
      !status.mode || !status.api_address || !Number.isFinite(Date.parse(status.supplier_timestamp_utc)) || ![0,1].includes(poll[name])) return false;
  try { validate(tag,'0'); return true; } catch { return false; }
}
function canClear() {
  const record = operation?.record;
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
    if (operation?.record === attempt.record && operation.end_mode === 'hold') operation.holdState = 'RELEASED TO 0';
    attempt.message = `The API accepted ${attempt.tag_name}=0. A fresh later readback confirmed 0 at ${attempt.verifiedAt}. This checks the command bit. It does not confirm a physical position.`;
  }
}
function sendZero(target) {
  if (!canClearTarget(target)) return;
  const name = typeof target === 'string' ? target : target.tag_name;
  const tag = tags.find(item => item.tag_name === name), address = tag.device_address, context = apiContext();
  confirmWrite('Confirm manual Send 0', [['Signal',name],['PLC address',address],['Current value',poll[name]],['New value',0],
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
      observation.source = 'Feedback tests manual Send 0'; observation.command_browser_baseline_utc = clearAttempt.browserBaselineUtc;
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
  const tag = tags.find(item => item.tag_name === test.command_tag), address = tag.device_address, context = apiContext();
  let holdChoice = null;
  confirmWrite(`Confirm ${test.requires_confirmation ? 'mapping under test' : 'feedback test'}`, [['Command',`${test.command_tag}=${test.command_value}`],['PLC address',address],
    ['Expected feedback',`${test.feedback_tag}=${test.expected_feedback}`],['Mapping',test.requires_confirmation ? 'Under test: the console records matches as OBSERVED, not PASS. The supplier must confirm the mapping.' : 'Configured feedback test'],
    ['After 1',/door/i.test(test.command_tag) ? 'Send 0 after physical movement finishes. Confirm any unverified reset rule.' : 'Choose Hold 1 or Manual 0. This records your test plan.'],
    ['Operation','The console sends one command write. It does not send automatic 0, pulses, or retries. Confirm the area and command are ready.']], async () => {
    if (!canRun(test) || tags.find(item => item.tag_name === test.command_tag)?.device_address !== address || apiContext() !== context) {
      activeTest = test; result = null; operation = null; clearAttempt = null; error = new Error('The command or connection changed during confirmation; no test was dispatched.'); error.writeDispatched = false; renderResult(); return;
    }
    const endMode = holdChoice?.checked ? 'hold' : 'manual0';
    const record = beginFeedbackTest(test,endMode);
    if (!record) return;
    operation = {end_mode:endMode,mapping_under_test:Boolean(test.requires_confirmation),address,context,holdState:'WAITING',record};
    activeTest = test; result = null; error = null; clearAttempt = null; running = true; updateVerifier();
    const panel = $('test-result'); panel.focus({preventScroll:true}); panel.scrollIntoView({block:'start'});
    try { result = await post('/api/test/run',{id:test.id,end_mode:endMode,...(test.requires_confirmation ? {mapping_under_test:true} : {})}); }
    catch (failure) { error = failure; }
    finally { finishFeedbackTest(record,result,error); running = false; updateVerifier(); }
  });
  const details = node('details'), summary = node('summary','','Rule source');
  details.append(summary,node('p','',commandGuidance(tag).evidence)); $('confirm-body').append(details);
  if (!/door/i.test(test.command_tag)) {
    const mode = node('div','command-mode'), label = node('span','command-mode-label','After 1:'), choices = node('div','command-mode-options');
    mode.id = 'test-end-mode'; label.id = 'test-end-mode-label'; mode.setAttribute('role','group'); mode.setAttribute('aria-labelledby',label.id);
    for (const [value,text] of [['hold','Hold 1'],['manual0','Manual 0']]) {
      const choice = node('label'), input = node('input'); input.type = 'radio'; input.name = 'test-end-mode'; input.value = value; input.id = `test-mode-${value === 'hold' ? 'hold' : 'manual'}`; input.checked = value === 'manual0';
      if (value === 'hold') holdChoice = input;
      choice.append(input,node('span','',text));
      if (value === 'hold' && commandGuidance(tag).hint === 'hold') {
        const hint = node('small','command-mode-badge','Hint'); hint.dataset.modeHint = 'hold'; hint.id = 'test-mode-hold-hint';
        hint.title = 'Inferred from the manual. Supplier confirmation is required.'; input.setAttribute('aria-describedby',hint.id); choice.append(hint);
      }
      choices.append(choice);
    }
    mode.append(label,choices); $('confirm-body').prepend(mode);
  }
}
