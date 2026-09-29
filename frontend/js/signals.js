import {$, node, groupFor, fillGroups, valueText} from './dom.js';
let tags = [], poll = null, health = null;
export function setSignalData(nextTags, nextPoll) {
  if (nextTags) { tags = nextTags; fillGroups($('signal-group'), tags); fillGroups($('browser-group'), tags); initTanks(); }
  if (nextPoll) poll = nextPoll;
  renderSignals(); renderTanks(); renderAlarms(); renderBrowser();
}
function searchMatch(tag, query) { return [tag.tag_name, tag.description, tag.device_address].some(v => v.toLowerCase().includes(query)); }
function signalStatus(tag) { return !poll || poll[tag.tag_name] == null || !health?.supplier_api_connected || !health?.data_fresh ? 'FAILED' : 'OK'; }
export function setSignalHealth(nextStatus) { health = nextStatus; renderSignals(); renderTanks(); renderAlarms(); renderBrowser(); }
function renderSignals() {
  const query = $('signal-search').value.trim().toLowerCase(), filter = $('signal-filter').value, group = $('signal-group').value;
  const matched = tags.filter(t => searchMatch(t, query) && (filter === 'all' || t.read_write === filter || t.data_type === filter) && (group === 'all' || groupFor(t) === group));
  $('signal-total').textContent = `${matched.length} / ${tags.length} signals`;
  const list = $('signal-list'); list.replaceChildren(); list.className = matched.length ? 'signal-list' : 'signal-list empty';
  if (!matched.length) { list.textContent = 'No matching signals.'; return; }
  for (const tag of matched.slice(0, 120)) {
    const card = node('div', `signal-card ${signalStatus(tag) === 'FAILED' ? 'failed' : ''}`);
    const info = node('div'); info.append(node('strong', '', tag.tag_name), node('small', '', tag.description));
    const val = node('div', 'value', valueText(poll?.[tag.tag_name]));
    card.append(info, val); list.append(card);
  }
  if (matched.length > 120) list.append(node('div', 'empty', `Showing first 120; narrow the search to inspect remaining ${matched.length - 120}.`));
}
function initTanks() {
  const tanks = [...new Set(tags.map(groupFor).filter(g => g.startsWith('Tank')))].sort();
  const select = $('tank-select'), current = select.value;
  select.replaceChildren(...tanks.map(t => { const opt = node('option', '', t.replace('Tank', 'Tank ')); opt.value = t; return opt; }));
  if (tanks.includes(current)) select.value = current;
}
function tankCategory(tag) {
  const suffix = tag.tag_name.replace(/^Tank\d{2}(?:[A-Z])?_/, '');
  if (suffix.startsWith('Door')) return 'Door';
  if (suffix.startsWith('Temp')) return 'Temperature';
  if (suffix.startsWith('Time')) return 'Timer';
  if (suffix.includes('Basket')) return 'Basket';
  if (suffix.startsWith('Filter')) return 'Filter';
  if (suffix.startsWith('Heater')) return 'Heater';
  if (suffix.startsWith('US')) return 'Ultrasonic';
  if (suffix.startsWith('WaterFlow')) return 'Water flow';
  if (suffix.startsWith('FillWater')) return 'Fill water';
  return 'Other';
}
function renderTanks() {
  const group = $('tank-select').value, container = $('tank-grid'); container.replaceChildren();
  if (!group) { container.textContent = 'No tank tags in catalog.'; return; }
  const grouped = new Map();
  for (const tag of tags.filter(t => groupFor(t) === group)) {
    const category = tankCategory(tag);
    if (!grouped.has(category)) grouped.set(category, []);
    grouped.get(category).push(tag);
  }
  const order = ['Door','Temperature','Timer','Basket','Filter','Heater','Ultrasonic','Water flow','Fill water','Other'];
  for (const category of order) {
    const items = grouped.get(category);
    if (!items) continue;
    const card = node('div', 'tank-category'); card.append(node('h3','',category));
    for (const tag of items) {
      const row = node('div','tank-row');
      const suffix = tag.tag_name.replace(/^Tank\d{2}(?:[A-Z])?_/, '');
      const label = node('span','',suffix); label.title = tag.description;
      row.append(label,node('strong','',valueText(poll?.[tag.tag_name])));
      card.append(row);
    }
    container.append(card);
  }
}
function renderAlarms() {
  const alarms = tags.filter(t => /^Alarm\d+$/i.test(t.tag_name));
  $('alarm-count').textContent = `${alarms.length} alarm tags`;
  const list = $('alarm-list'); list.replaceChildren();
  for (const tag of alarms) {
    const value = poll?.[tag.tag_name];
    const item = node('div', 'alarm-item'), label = node('div');
    label.append(node('strong', '', tag.tag_name), node('small', '', tag.description));
    item.append(label, node('span', '', valueText(value))); list.append(item);
  }
}
function renderBrowser() {
  const query = $('browser-search').value.trim().toLowerCase(), type = $('browser-type').value, rw = $('browser-rw').value, group = $('browser-group').value, sort = $('browser-sort').value;
  const matched = tags.filter(t => searchMatch(t, query) && (type === 'all' || t.data_type === type) && (rw === 'all' || t.read_write === rw) && (group === 'all' || groupFor(t) === group)).sort((a,b) => String(a[sort]).localeCompare(String(b[sort])));
  const body = $('tag-table'); body.replaceChildren();
  for (const tag of matched) {
    const tr = node('tr');
    const cells = [tag.tag_name, tag.description, tag.device_address, tag.data_type, tag.read_write, tag.multiplier, tag.low_limit ?? '—', tag.high_limit ?? '—', valueText(poll?.[tag.tag_name]), signalStatus(tag)];
    cells.forEach((value, index) => { const td = node('td', [2,5,6,7].includes(index) ? 'advanced-col' : index === 1 ? 'description' : '', value); if (index === 0) td.title = tag.tag_name; if (index === 1) td.title = tag.description; tr.append(td); });
    const action = node('td');
    if (tag.read_write === 'W') { const button = node('button', 'button small secondary', 'Select'); button.type = 'button'; button.addEventListener('click', () => { $('write-tag').value = tag.tag_name; $('write-tag').dispatchEvent(new Event('change')); $('write').scrollIntoView(); }); action.append(button); }
    tr.append(action); body.append(tr);
  }
  $('browser-count').textContent = `Showing ${matched.length} of ${tags.length} tags`;
}
export function initSignalEvents() {
  for (const id of ['signal-search','signal-filter','signal-group']) $(id).addEventListener('input', renderSignals);
  $('tank-select').addEventListener('change', renderTanks);
  for (const id of ['browser-search','browser-type','browser-rw','browser-group','browser-sort']) $(id).addEventListener('input', renderBrowser);
  $('advanced-toggle').addEventListener('change', event => document.body.classList.toggle('advanced', event.target.checked));
}
