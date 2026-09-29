import {$, node, valueText} from './dom.js';
import {post, enableMode, disableMode, modeEnabled} from './api.js';
let tags = [], poll = null, status = null;
export function updateControls(nextTags, nextPoll, nextStatus) {
  if (nextTags) {
    tags = nextTags;
    const writable = tags.filter(t => t.read_write === 'W').sort((a,b) => a.tag_name.localeCompare(b.tag_name));
    const select = $('write-tag'), prior = select.value;
    select.replaceChildren(...writable.map(t => { const option = node('option', '', `${t.tag_name} — ${t.description}`); option.value = t.tag_name; return option; }));
    if (writable.some(t => t.tag_name === prior)) select.value = prior;
  }
  if (nextPoll) poll = nextPoll;
  if (nextStatus) status = nextStatus;
  const canWrite = modeEnabled() && status?.data_fresh && status?.plc_mode === 'REMOTE';
  $('write-submit').disabled = !canWrite;
  $('batch-submit').disabled = !canWrite;
  renderSelected();
}
function selected() { return tags.find(t => t.tag_name === $('write-tag').value); }
function renderSelected() {
  const tag = selected(), detail = $('write-detail'); detail.replaceChildren();
  if (!tag) { detail.textContent = 'No writable signals in catalog.'; return; }
  const grid = node('div', 'detail-grid');
  const fields = [['Description', tag.description], ['Tag', tag.tag_name], ['PLC address', tag.device_address], ['Type', tag.data_type], ['Current', valueText(poll?.[tag.tag_name])], ['Multiplier', tag.multiplier], ['Allowed', `${tag.low_limit ?? 'unbounded'} to ${tag.high_limit ?? 'unbounded'}`]];
  fields.forEach(([name,value]) => grid.append(node('span', '', name), node('strong', '', value)));
  detail.append(grid);
  $('write-limits').textContent = `Allowed: ${tag.data_type === 'Bool' ? '0 or 1' : `${tag.low_limit ?? 'unbounded'} to ${tag.high_limit ?? 'unbounded'}`} · ${tag.data_type} · engineering units`;
  $('write-value').placeholder = tag.data_type === 'Bool' ? '0 or 1' : 'Enter engineering value';
}
function validate(tag, raw) {
  if (!tag || tag.read_write !== 'W') throw new Error('Writable tag required');
  if (raw.trim() === '') throw new Error('Enter a value');
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error('Enter a finite number');
  if (tag.data_type === 'Bool' && value !== 0 && value !== 1) throw new Error('Bool accepts 0 or 1');
  if (tag.low_limit != null && value < tag.low_limit) throw new Error(`Below low limit ${tag.low_limit}`);
  if (tag.high_limit != null && value > tag.high_limit) throw new Error(`Above high limit ${tag.high_limit}`);
  return value;
}
function confirmWrite(title, fields, action) {
  const dialog = $('confirm-dialog'); $('confirm-title').textContent = title;
  const body = $('confirm-body'); body.replaceChildren();
  const grid = node('div', 'detail-grid'); fields.forEach(([label,value]) => grid.append(node('span', '', label), node('strong', '', value)));
  body.append(grid);
  dialog.onclose = async () => { if (dialog.returnValue === 'confirm') await action(); };
  dialog.showModal();
}
export function initControls(onChange) {
  $('write-tag').addEventListener('change', renderSelected);
  $('mode-btn').addEventListener('click', async () => {
    try {
      if (modeEnabled()) await disableMode();
      else if (window.confirm('Enable WRITE TEST MODE for 30 minutes? Commands may actuate equipment.')) await enableMode();
      onChange();
    } catch (error) { $('write-result').textContent = error.message; }
  });
  $('write-submit').addEventListener('click', () => {
    const tag = selected();
    try {
      const value = validate(tag, $('write-value').value);
      confirmWrite('Confirm PLC write', [['Signal',tag.tag_name],['Address',tag.device_address],['Current value',valueText(poll?.[tag.tag_name])],['New value',value]], async () => {
        try { const response = await post('/api/write', {tag_name: tag.tag_name, value}); $('write-result').textContent = response.written === true ? `WRITE ACCEPTED · ${response.tag_name} = ${response.value}. Check physical feedback separately.` : `WRITE FAILED · Supplier did not confirm written=true for ${tag.tag_name}.`;  onChange(); }
        catch (error) { $('write-result').textContent = `WRITE FAILED · ${error.message}${error.detail ? ` (${error.detail})` : ''}`; }
      });
    } catch (error) { $('write-result').textContent = error.message; }
  });
  $('batch-submit').addEventListener('click', () => {
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
      confirmWrite('Confirm batch PLC write', [['Item count',validated.length],['Signals',validated.map(w => `${w.tag_name}=${w.value}`).join(', ')],['Confirmation','CONFIRM BATCH WRITE']], async () => {
        try { await post('/api/write/batch', {writes:validated, confirmation:'CONFIRM BATCH WRITE'}); $('batch-result').textContent = `BATCH ACCEPTED · ${validated.length} items. Verify physical feedback separately.`; onChange(); }
        catch (error) { $('batch-result').textContent = `BATCH FAILED · ${error.message}`; }
      });
    } catch (error) { $('batch-result').textContent = error.message; }
  });
}
