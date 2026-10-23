import {$, node, groupFor, fillGroups, valueText, metadataNumber} from './dom.js';
import {prepareWrite} from './controls.js';
let tags = [], poll = null, health = null, selectedTank = null;
export function setSignalData(nextTags, nextPoll) {
  if (nextTags) {
    tags = nextTags; fillGroups($('signal-group'), tags); fillGroups($('browser-group'), tags); initTanks();
    const writable = tags.filter(t => t.read_write === 'W');
    $('nav-signals-badge').textContent = tags.length;
    $('nav-alarms-badge').textContent = tags.filter(t => /^Alarm\d+$/i.test(t.tag_name)).length;
    $('ov-read-count').textContent = `${tags.length - writable.length} read-only tags`;
    $('ov-write-count').textContent = `${writable.length} writable · ${writable.filter(t => t.data_type === 'Bool').length} Bool`;
  }
  if (nextPoll) poll = nextPoll;
  renderSignals(); renderTanks(); renderAlarms(); renderBrowser();
}
function searchMatch(tag, query) { return [tag.tag_name, tag.description, tag.device_address].some(v => v.toLowerCase().includes(query)); }
function readState(tag) {
  if (!poll || poll[tag.tag_name] == null) return 'NO DATA';
  if (!health?.supplier_api_connected) return 'DISCONNECTED · last value';
  return health.data_fresh ? '' : 'STALE';
}
function signalStatus(tag) { return readState(tag) ? 'FAILED' : 'OK'; }
export function setSignalHealth(nextStatus) { health = nextStatus; renderSignals(); renderTanks(); renderAlarms(); renderBrowser(); }
function renderSignals() {
  const query = $('signal-search').value.trim().toLowerCase(), filter = $('signal-filter').value, group = $('signal-group').value;
  const matched = tags.filter(t => searchMatch(t, query) && (filter === 'all' || t.read_write === filter || t.data_type === filter) && (group === 'all' || groupFor(t) === group));
  $('signal-total').textContent = `${matched.length} / ${tags.length} signals`;
  const list = $('signal-list'); list.replaceChildren(); list.className = matched.length ? 'signal-list signal-groups' : 'signal-list empty';
  if (!matched.length) { list.textContent = 'No matching signals.'; return; }
  const groups = new Map();
  for (const tag of matched) {
    const key = groupFor(tag);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(tag);
  }
  for (const key of [...groups.keys()].sort()) {
    const section = node('section', 'signal-group'), heading = node('div', 'signal-group-header'), grid = node('div', 'signal-group-grid');
    section.dataset.signalGroup = key;
    const title = node('h2', '', key === 'Alarm' ? 'Alarms' : key); title.id = `signal-group-${key}`;
    section.setAttribute('aria-labelledby', title.id);
    heading.append(title, node('span', 'signal-group-count', `${groups.get(key).length} signals`));
    for (const tag of groups.get(key)) {
      const state = readState(tag), card = node('div', `signal-card ${state ? 'failed' : ''}`); card.dataset.signalTag = tag.tag_name;
      const info = node('div'); info.append(node('strong', '', tag.tag_name), node('small', '', tag.description));
      if (state) info.append(node('span', 'read-state', state));
      const val = node('div', 'value', valueText(poll?.[tag.tag_name]));
      card.append(info, val); grid.append(card);
    }
    section.append(heading, grid); list.append(section);
  }
}
function initTanks() {
  const tanks = [...new Set(tags.map(groupFor).filter(g => g.startsWith('Tank')))].sort();
  if (!tanks.includes(selectedTank)) selectedTank = tanks[0] ?? null;
  $('tank-select').replaceChildren(...tanks.map(tank => {
    const button = node('button', 'tank-tab', tank.replace('Tank', 'Tank ')); button.type = 'button';
    button.id = `tank-tab-${tank}`; button.dataset.tank = tank; button.setAttribute('role', 'tab'); button.setAttribute('aria-controls', 'tank-grid');
    button.setAttribute('aria-selected', String(tank === selectedTank)); button.tabIndex = tank === selectedTank ? 0 : -1;
    return button;
  }));
  if (selectedTank) $('tank-grid').setAttribute('aria-labelledby', `tank-tab-${selectedTank}`);
  else $('tank-grid').removeAttribute('aria-labelledby');
}
function selectTank(tank) {
  const tabs = [...$('tank-select').querySelectorAll('[data-tank]')], selected = tabs.find(button => button.dataset.tank === tank);
  if (!selected) return;
  selectedTank = tank;
  for (const button of tabs) { button.setAttribute('aria-selected', String(button === selected)); button.tabIndex = button === selected ? 0 : -1; }
  $('tank-grid').setAttribute('aria-labelledby', selected.id); renderTanks();
  selected.focus(); selected.scrollIntoView({block:'nearest', inline:'nearest'});
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
  const group = selectedTank, container = $('tank-grid'); container.replaceChildren();
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
      const state = readState(tag), row = node('div', `tank-row ${state ? 'failed' : ''}`); row.dataset.signalTag = tag.tag_name;
      const suffix = tag.tag_name.replace(/^Tank\d{2}([A-Z])?_/, (_, letter) => letter ? `${letter}_` : '');
      const label = node('div', 'tank-label');
      label.append(node('span', 'tank-name', suffix), node('span', 'read-permission', tag.read_write === 'R' ? 'R · read-only' : 'W · readback'), node('small', 'tank-description', tag.description));
      if (state) label.append(node('span', 'read-state', state));
      row.append(label,node('strong','value',valueText(poll?.[tag.tag_name])));
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
    const state = readState(tag), item = node('div', `alarm-item ${state ? 'failed' : ''}`), label = node('div'); item.dataset.signalTag = tag.tag_name;
    label.append(node('strong', '', tag.tag_name), node('small', '', tag.description));
    if (state) label.append(node('span', 'read-state', state));
    item.append(label, node('span', 'value', valueText(value))); list.append(item);
  }
}
function renderBrowser() {
  const query = $('browser-search').value.trim().toLowerCase(), type = $('browser-type').value, rw = $('browser-rw').value, group = $('browser-group').value, sort = $('browser-sort').value;
  const matched = tags.filter(t => searchMatch(t, query) && (type === 'all' || t.data_type === type) && (rw === 'all' || t.read_write === rw) && (group === 'all' || groupFor(t) === group)).sort((a,b) => String(a[sort]).localeCompare(String(b[sort])));
  const body = $('tag-table'); body.replaceChildren();
  for (const tag of matched) {
    const tr = node('tr');
    const cells = [tag.tag_name, tag.description, tag.device_address, tag.data_type, tag.read_write, metadataNumber(tag.multiplier), metadataNumber(tag.low_limit), metadataNumber(tag.high_limit), valueText(poll?.[tag.tag_name]), signalStatus(tag)];
    cells.forEach((value, index) => { const td = node('td', [2,5,6,7].includes(index) ? 'advanced-col' : index === 1 ? 'description' : '', value); if (index === 0) td.title = tag.tag_name; if (index === 1) td.title = tag.description; tr.append(td); });
    const action = node('td');
    if (tag.read_write === 'W') { const button = node('button', 'button small secondary', 'Select'); button.type = 'button'; button.addEventListener('click', () => prepareWrite(tag.tag_name)); action.append(button); }
    tr.append(action); body.append(tr);
  }
  $('browser-count').textContent = `Showing ${matched.length} of ${tags.length} tags`;
}
export function initSignalEvents() {
  for (const id of ['signal-search','signal-filter','signal-group']) $(id).addEventListener('input', renderSignals);
  $('tank-select').addEventListener('click', event => {
    const button = event.target.closest('[data-tank]'); if (button) selectTank(button.dataset.tank);
  });
  $('tank-select').addEventListener('keydown', event => {
    const tabs = [...$('tank-select').querySelectorAll('[data-tank]')], index = tabs.indexOf(event.target);
    if (index < 0 || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length-1 : (index+(event.key === 'ArrowRight' ? 1 : -1)+tabs.length)%tabs.length;
    selectTank(tabs[next].dataset.tank);
  });
  for (const id of ['browser-search','browser-type','browser-rw','browser-group','browser-sort']) $(id).addEventListener('input', renderBrowser);
  $('advanced-toggle').addEventListener('change', event => document.body.classList.toggle('advanced', event.target.checked));
}
