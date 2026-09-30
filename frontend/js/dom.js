export const $ = id => document.getElementById(id);
export function node(tag, className = '', content = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = content == null ? '—' : String(content);
  return element;
}
export function setText(id, value) { $(id).textContent = value == null || value === '' ? '—' : String(value); }
export function formatTime(value) { if (!value) return '—'; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString(); }
export function valueText(value) { return value == null ? 'NO DATA' : String(value); }
export function metadataNumber(value, empty = '—') { return value == null ? empty : Number.isInteger(value) ? value.toFixed(1) : String(value); }
export function groupFor(tag) { const match = tag.tag_name.match(/^Tank(\d{2})(?:[A-Z])?_/); return match ? `Tank${match[1]}` : tag.tag_name.startsWith('Alarm') ? 'Alarm' : 'System'; }
export function fillGroups(select, tags) {
  const current = select.value;
  select.replaceChildren(node('option', '', 'All groups'));
  select.firstChild.value = 'all';
  for (const group of [...new Set(tags.map(groupFor))].sort()) { const opt = node('option', '', group); opt.value = group; select.append(opt); }
  select.value = [...select.options].some(o => o.value === current) ? current : 'all';
}
export function showError(target, error) { target.textContent = error.message || String(error); target.classList.remove('hidden'); }
