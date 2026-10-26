// Signal judgments are explicit decisions, independent of the newest write attempt.
const cache = new Map(), serverDecisions = new Map();
const contextKey = status => status?.mode && status?.api_address ? `${status.mode}:${status.api_address}` : null;
const decisionKey = status => `plc-signal-results:v1:${contextKey(status)}`;
const importedKey = status => `plc-imported-human-results:v1:${contextKey(status)}`;
export const signature = tag => tag ? [tag.tag_name,tag.device_address,tag.data_type,tag.read_write,tag.multiplier] : null;
const matches = (identity, tag) => JSON.stringify(identity) === JSON.stringify(signature(tag));
function read(key, strict = false) {
  try {
    const raw = localStorage.getItem(key) ?? '[]';
    if (cache.get(key)?.raw !== raw) {
      const rows = JSON.parse(raw);
      if (!Array.isArray(rows)) throw new Error('Saved results are not a list.');
      cache.set(key,{raw,rows});
    }
    return cache.get(key).rows;
  } catch (error) { if (strict) throw error; return cache.get(key)?.rows ?? []; }
}
function timestamp(value) {
  const ms = typeof value === 'number' ? value : typeof value === 'string' && value.trim() ? Date.parse(value) : NaN;
  return Number.isFinite(ms) && ms > 0 ? new Date(ms).toISOString() : null;
}
function legacyDecision(record) {
  const value = record.issueAt || record.operatorResult === 'fail' ? 'fail' :
    record.operatorResult === 'unchecked' ? 'unchecked' : timestamp(record.operatorCompletedAt) ? 'pass' : null;
  if (!value) return null;
  const at = timestamp(record.operatorResultAt) ?? timestamp(record.issueAt) ?? timestamp(record.operatorCompletedAt) ??
    timestamp(record.startedAt) ?? timestamp(record.requested_at);
  return at ? {value,at,record} : null;
}
export function manualDecisions(status) {
  return contextKey(status) ? read(decisionKey(status)).filter(row => row && typeof row === 'object') : [];
}
const offsetTimestamp = value => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) && Boolean(timestamp(value));
function validServerDecision(row) {
  return Boolean(row && row.kind === 'human' && Array.isArray(row.identity) && row.identity.length === 5 &&
    row.identity.slice(0,3).every(value => typeof value === 'string' && value) && row.identity[3] === 'W' && Number.isFinite(row.identity[4]) &&
    ['pass','fail','unchecked'].includes(row.value) && (!Object.hasOwn(row,'api_backfill_allowed') || typeof row.api_backfill_allowed === 'boolean') &&
    offsetTimestamp(row.at) && (row.observed_at == null || offsetTimestamp(row.observed_at)) && typeof row.source === 'string' && row.source && row.write_sent === false);
}
export function importedHumanDecisions(status) {
  const context = contextKey(status);
  if (!context) return [];
  if (!serverDecisions.has(context)) serverDecisions.set(context,read(importedKey(status)).filter(validServerDecision));
  return serverDecisions.get(context);
}
export function setServerHumanDecisions(data, status) {
  const context = contextKey(status);
  if (!context || contextKey(data?.context) !== context || data?.operator_results_error || !Array.isArray(data?.operator_results) ||
      !data.operator_results.every(validServerDecision)) return false;
  serverDecisions.set(context,data.operator_results);
  try { localStorage.setItem(importedKey(status),JSON.stringify(data.operator_results)); } catch { /* The server retains the source decisions. */ }
  return true;
}
export function savedManualApiDecision(tag, status) {
  return tag ? manualDecisions(status).findLast(row => row.kind === 'api' && matches(row.identity,tag) &&
    ['auto','checked','failed','unchecked'].includes(row.value) && timestamp(row.at)) ?? null : null;
}
export function savedHumanDecision(tag, status, test = null) {
  const context = contextKey(status);
  if (!tag || tag.read_write !== 'W' || !context) return null;
  const decisions = [...importedHumanDecisions(status),...manualDecisions(status)].filter(row => row.kind === 'human' && matches(row.identity,tag) &&
    ['pass','fail','unchecked'].includes(row.value) && timestamp(row.at));
  const scope = `plc-command-checklist:v1:${context}`;
  for (const record of read(scope)) {
    if (!record || record.tag_name !== tag.tag_name || record.address !== tag.device_address || record.zeroOnlyCleanup ||
        record.identity && !matches(record.identity,tag) || !record.identity && (tag.data_type !== 'Bool' || tag.multiplier !== 1) || record.feedbackScope && record.feedbackScope !== scope ||
        test && record.feedbackTestId && record.feedbackTestId !== test.id) continue;
    const decision = legacyDecision(record); if (decision) decisions.push(decision);
  }
  for (const record of read(`plc-value-feedback:v1:${context}`)) {
    // Old Value records have no captured metadata; keep them in history without assigning current signal identity.
    if (!record || !Array.isArray(record.writes) || !record.writes.some(write => write?.tag_name === tag.tag_name) ||
        !Array.isArray(record.identities) || !record.identities.some(identity => matches(identity,tag))) continue;
    const decision = legacyDecision(record); if (decision) decisions.push(decision);
  }
  return decisions.reduce((latest, row) => !latest || Date.parse(row.at) >= Date.parse(latest.at) ? row : latest,null);
}
export function saveManualDecision(tag, status, kind, value) {
  if (!tag || tag.read_write !== 'W' || !contextKey(status) ||
      !(kind === 'human' ? ['pass','fail','unchecked'] : kind === 'api' ? ['auto','checked','failed','unchecked'] : []).includes(value))
    throw new Error('Select a writable signal and a valid result.');
  const key = decisionKey(status), rows = read(key,true);
  const previous = kind === 'human' ? savedHumanDecision(tag,status) : savedManualApiDecision(tag,status);
  const decision = {id:crypto.randomUUID(),identity:signature(tag),kind,value,at:new Date().toISOString(),
    previous_value:previous?.value ?? null,previous_at:previous?.at ?? null,source:'Operator',write_sent:false};
  localStorage.setItem(key,JSON.stringify([...rows,decision]));
  return decision;
}
