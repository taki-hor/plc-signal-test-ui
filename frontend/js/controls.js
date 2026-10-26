import {apiFilterMatches, renderApiBadge, renderSavedResults} from './api-checks.js';
import {go} from './router.js';
import {$, node, valueText, metadataNumber} from './dom.js';
import {post, enableMode, disableMode, modeEnabled} from './api.js';
import {beginWriteObservation, finishWriteObservation, writeHumanResult} from './write-feedback.js';
let tags = [], poll = null, status = null, valueIdentity = null;
function canWrite() { return modeEnabled() && status?.supplier_api_connected && status?.data_fresh && status?.plc_mode === 'REMOTE'; }
export function writeIdentity(tag, context) {
  return tag && context?.api_address && context?.mode ?
    JSON.stringify([context.api_address,context.mode,tag.tag_name,tag.device_address,tag.data_type,tag.read_write,tag.multiplier]) : null;
}
export function updateControls(nextTags, nextPoll, nextStatus) {
  if (nextTags) {
    tags = nextTags;
    const writable = tags.filter(t => t.read_write === 'W').sort((a,b) => a.tag_name.localeCompare(b.tag_name));
    const select = $('write-tag'), prior = select.value;
    select.replaceChildren();
    for (const [label,items] of [['Numeric setpoints',writable.filter(t => t.data_type !== 'Bool')],['Bool commands',writable.filter(t => t.data_type === 'Bool')]]) {
      if (!items.length) continue;
      const group = node('optgroup'); group.label = label;
      group.append(...items.map(t => { const option = node('option', '', `${t.tag_name} — ${t.description}`); option.value = t.tag_name; return option; }));
      select.append(group);
    }
    if (writable.some(t => t.tag_name === prior)) select.value = prior;
  }
  if (nextPoll) poll = nextPoll;
  if (nextStatus) status = nextStatus;
  $('write-submit').disabled = !canWrite() || !selected();
  $('batch-submit').disabled = !canWrite();
  renderSelected();
}
function selected() { return tags.find(t => t.tag_name === $('write-tag').value); }
function renderValueControl(tag, defaultInvalid = false) {
  const bool = tag?.data_type === 'Bool', input = $('write-value');
  input.classList.toggle('hidden',bool); $('write-bool-control').classList.toggle('hidden',!bool);
  if (bool) $('write-value-label').removeAttribute('for'); else $('write-value-label').htmlFor = 'write-value';
  if (bool && defaultInvalid && (input.value.trim() === '' || ![0,1].includes(Number(input.value)))) input.value = '0';
  const value = input.value.trim() === '' ? null : Number(input.value);
  $('write-bool-zero').checked = bool && value === 0; $('write-bool-one').checked = bool && value === 1;
}
function renderSelected() {
  for (const option of $('write-tag').options) { const tag=tags.find(t=>t.tag_name===option.value); option.hidden=!apiFilterMatches(tag,$('write-api-filter').value,writeHumanResult(tag?.tag_name,status),status); }
  const tag = selected(), identity = tag ? JSON.stringify([tag.tag_name,tag.device_address,tag.data_type]) : null;
  $('write-submit').disabled=!canWrite() || !tag;
  renderValueControl(tag,identity !== valueIdentity); valueIdentity = identity;
  renderApiBadge($('write-api-state'),tag,status); renderSavedResults($('write-saved-results'),tag,status);
  $('write-api-filter-note').textContent=tag && !apiFilterMatches(tag,$('write-api-filter').value,writeHumanResult(tag.tag_name,status),status) ? 'Selected signal is outside this filter.' : '';
  const detail = $('write-detail'); detail.replaceChildren();
  if (!tag) { detail.textContent = 'No writable signals in catalog.'; return; }
  const grid = node('div', 'detail-grid');
  const allowed = tag.data_type === 'Bool' ? '0 or 1' : tag.low_limit == null && tag.high_limit == null ? 'Not published' : `${metadataNumber(tag.low_limit, 'not published')} to ${metadataNumber(tag.high_limit, 'not published')}`;
  const fields = [['Description', tag.description], ['Tag', tag.tag_name], ['PLC address', tag.device_address], ['Type', tag.data_type], ['Current', valueText(poll?.[tag.tag_name])], ['Multiplier', metadataNumber(tag.multiplier)], ['API limits', allowed]];
  fields.forEach(([name,value]) => grid.append(node('span', '', name), node('strong', '', value)));
  detail.append(grid);
  $('write-limits').textContent = `API limits: ${allowed} · ${tag.data_type} · engineering units`;
  $('write-value').placeholder = tag.data_type === 'Bool' ? '0 or 1' : 'Enter engineering value';
}
export function validate(tag, raw) {
  if (!tag || tag.read_write !== 'W') throw new Error('Writable tag required');
  if (raw.trim() === '') throw new Error('Enter a value');
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error('Enter a finite number');
  if (tag.data_type === 'Bool' && value !== 0 && value !== 1) throw new Error('Bool accepts 0 or 1');
  if (tag.low_limit != null && value < tag.low_limit) throw new Error(`Below low limit ${tag.low_limit}`);
  if (tag.high_limit != null && value > tag.high_limit) throw new Error(`Above high limit ${tag.high_limit}`);
  return value;
}
export function prepareWrite(tagName, value) {
  const tag = tags.find(item => item.tag_name === tagName);
  if (!tag || tag.read_write !== 'W') return false;
  if (value !== undefined) {
    try { validate(tag, String(value)); } catch { return false; }
    $('write-value').value = String(value);
  }
  $('write-api-filter').value='all';
  $('write-tag').value = tag.tag_name;
  $('write-tag').dispatchEvent(new Event('change'));
  go('write');
  return true;
}
export function confirmWrite(title, fields, action) {
  const dialog = $('confirm-dialog'); dialog.returnValue = ''; $('confirm-title').textContent = title;
  const body = $('confirm-body'); body.replaceChildren();
  const grid = node('div', 'detail-grid'); fields.forEach(([label,value]) => grid.append(node('span', '', label), node('strong', '', value)));
  body.append(grid);
  dialog.onclose = async () => { if (dialog.returnValue === 'confirm') await action(); };
  dialog.showModal();
}
export function initControls(onChange) {
  $('write-tag').addEventListener('change', renderSelected);
  $('write-value').addEventListener('input', () => renderValueControl(selected()));
  for (const id of ['write-bool-zero','write-bool-one']) $(id).addEventListener('change', () => {
    if (selected()?.data_type !== 'Bool' || !$(id).checked) return;
    $('write-value').value = $(id).value; renderValueControl(selected());
  });
  $('write-api-filter').addEventListener('input',()=>{
    const items=tags.filter(t=>t.read_write==='W' && apiFilterMatches(t,$('write-api-filter').value,writeHumanResult(t.tag_name,status),status));
    if (!items.some(t=>t.tag_name===$('write-tag').value)) $('write-tag').value=items[0]?.tag_name ?? '';
    $('write-submit').disabled=!canWrite() || !selected(); $('write-tag').dispatchEvent(new Event('change'));
  });
  $('mode-btn').addEventListener('click', async () => {
    $('mode-btn').disabled = true;
    try {
      if (modeEnabled()) { const disabling = disableMode(); onChange(); await disabling; }
      else {
        if (!window.confirm('Enable WRITE TEST MODE for 30 minutes? Commands may actuate equipment.')) return;
        await enableMode();
      }
      $('mode-error').textContent = ''; $('mode-error').classList.add('hidden');
    } catch (error) {
      $('mode-error').textContent = `Write mode request failed: ${error.message}`;
      $('mode-error').classList.remove('hidden');
    }
    finally { $('mode-btn').disabled = false; onChange(); }
  });
  $('write-submit').addEventListener('click', () => {
    if (!canWrite()) { onChange(); return; }
    const tag = selected();
    try {
      renderValueControl(tag);
      const value = validate(tag, $('write-value').value);
      const reviewed = writeIdentity(tag,status);
      confirmWrite('Confirm PLC write', [['Signal',tag.tag_name],['Address',tag.device_address],['Current value',valueText(poll?.[tag.tag_name])],['New value',value]], async () => {
        const current = selected();
        if (!reviewed || writeIdentity(current,status) !== reviewed) {
          $('write-result').textContent = 'Write blocked: signal, permissions or API context changed. Review the command again.'; onChange(); return;
        }
        if (!canWrite()) { $('write-result').textContent = 'Write blocked: fresh Remote data and write test mode are required.'; onChange(); return; }
        const observation = beginWriteObservation([{tag_name:tag.tag_name,value}]);
        try { const response = await post('/api/write', {tag_name: tag.tag_name, value}); finishWriteObservation(observation,response); $('write-result').textContent = response.written === true ? `WRITE ACCEPTED · ${response.tag_name} = ${response.value}. Watch the read signals and feedback below.` : `WRITE FAILED · Supplier did not confirm written=true for ${tag.tag_name}.`; onChange(); }
        catch (error) { finishWriteObservation(observation,null,error); $('write-result').textContent = `WRITE FAILED · ${error.message}${error.detail ? ` (${error.detail})` : ''}`; }
      });
    } catch (error) { $('write-result').textContent = error.message; }
  });
  $('batch-submit').addEventListener('click', () => {
    if (!canWrite()) { onChange(); return; }
    try {
      const writes = JSON.parse($('batch-json').value);
      if (!Array.isArray(writes) || writes.length < 1 || writes.length > 100) throw new Error('Batch requires 1 to 100 items');
      const names = new Set();
      const validated = writes.map(item => {
        const tag = tags.find(t => t.tag_name === item.tag_name);
        if (names.has(item.tag_name)) throw new Error(`Duplicate tag ${item.tag_name}`);
        names.add(item.tag_name);
        return {tag_name: item.tag_name, value: validate(tag, String(item.value))};
      });
      const reviewed = validated.map(item => writeIdentity(tags.find(tag => tag.tag_name === item.tag_name),status));
      confirmWrite('Confirm batch PLC write', [['Item count',validated.length],['Signals',validated.map(w => `${w.tag_name}=${w.value}`).join(', ')],['Confirmation','CONFIRM BATCH WRITE']], async () => {
        if (validated.some((item,index) => !reviewed[index] || writeIdentity(tags.find(tag => tag.tag_name === item.tag_name),status) !== reviewed[index])) {
          $('batch-result').textContent = 'Batch blocked: signal, permissions or API context changed. Review the commands again.'; onChange(); return;
        }
        if (!canWrite()) { $('batch-result').textContent = 'Batch blocked: fresh Remote data and write test mode are required.'; onChange(); return; }
        const observation = beginWriteObservation(validated);
        try { const response = await post('/api/write/batch', {writes:validated, confirmation:'CONFIRM BATCH WRITE'}); finishWriteObservation(observation,response); $('batch-result').textContent = response.console_batch_accepted === true ? `BATCH ACCEPTED · ${validated.length} items. Watch the read signals and feedback above.` : 'BATCH OUTCOME REQUIRES REVIEW · Supplier did not confirm every item as written.'; onChange(); }
        catch (error) { finishWriteObservation(observation,null,error); $('batch-result').textContent = `BATCH FAILED · ${error.message}`; }
      });
    } catch (error) { $('batch-result').textContent = error.message; }
  });
}
