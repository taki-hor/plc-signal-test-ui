import {formatTime, node} from './dom.js';
import {signature, savedHumanDecision, savedManualApiDecision, saveManualDecision} from './saved-results.js';
let records = new Map(), scope = null, contextValid = true;
const key = status => JSON.stringify([status?.mode,status?.api_address]);
const labels = {checked:'API pass',failed:'API fail',unchecked:'Unchecked'};
export function setApiChecks(data, status, tags = []) {
  const nextScope=key(status), mismatch=Boolean(data?.context && key(data.context)!==nextScope);
  if (scope!==nextScope || mismatch) records=new Map();
  scope=nextScope; contextValid=!mismatch;
  const error = data?.error || (mismatch ? 'API target changed. Waiting for matching check results.' : null);
  const note = document.getElementById('api-check-error');
  if (note) { note.textContent = error ? error+' Saved judgments are retained.' : ''; note.classList.toggle('hidden',!error); }
  // A failed refresh cannot erase the last matching result.
  if (!error && Array.isArray(data?.records)) records=new Map(data.records.map(record=>[record.tag_name,record]));
  renderApiSummary(status,tags);
}
export function renderApiSummary(status,tags) {
  const count=document.getElementById('api-check-summary');
  if (!count) return;
  const values=tags.filter(tag=>tag.read_write==='W').map(tag=>apiCheckFor(tag,status));
  const text=`API results: ${values.filter(r=>r.api_status==='checked').length} pass · ${values.filter(r=>r.api_status==='failed').length} fail · ${values.filter(r=>r.api_status==='unchecked').length} unchecked. Human results remain separate.`;
  if (count.textContent!==text) count.textContent=text;
}
export function apiCheckFor(tag, status) {
  const remote=scope===key(status) && tag ? records.get(tag.tag_name) : null;
  const mismatch=Boolean(remote && JSON.stringify(remote.identity)!==JSON.stringify(signature(tag)));
  let result=remote && !mismatch && Object.hasOwn(labels,remote.api_status) ? remote :
    {api_status:'unchecked',detail:mismatch ? 'Metadata changed; previous API evidence no longer applies.' : 'No verified API cycle is recorded for this signal.'};
  const human=tag && savedHumanDecision(tag,status), decision=tag && savedManualApiDecision(tag,status);
  if (human?.value==='pass' && !mismatch && remote?.identity_valid!==false && contextValid && result.api_status!=='checked' &&
      !(result.api_status==='failed' && Date.parse(result.checked_at ?? result.started_at)>=Date.parse(human.at))) {
    result={api_status:'checked',checked_at:human.at,source:'human',detail:'Human-confirmed test. This status was backfilled from your saved Pass; it is not a new automated API cycle.'};
  }
  if (decision && decision.value!=='auto') {
    const automatic=remote && !mismatch ? ` Latest automated result: ${labels[remote.api_status] ?? 'Unchecked'}. ${remote.detail ?? ''}` : '';
    result={api_status:decision.value,checked_at:decision.at,source:'manual',detail:'API status set manually. No PLC command was sent.'+automatic};
  }
  return result;
}
export function apiFilterMatches(tag, filter, humanResult, status) {
  const result=apiCheckFor(tag,status).api_status;
  return filter==='all' || (filter==='needs-human' ? result==='checked' && humanResult!=='pass' : result===filter);
}
export function renderApiBadge(element, tag, status) {
  const result=apiCheckFor(tag,status), label=labels[result.api_status];
  if (element.textContent!==label) element.textContent=label;
  element.classList.add('api-check-badge'); element.dataset.apiState=result.api_status;
  const text=[result.detail,result.checked_at ? 'Recorded '+formatTime(result.checked_at) : ''].filter(Boolean).join(' · ');
  element.title=text;
  const detail=document.getElementById(element.getAttribute('aria-describedby'));
  if (detail && detail.textContent!==text) detail.textContent=text;
}
export function renderSavedResults(element,tag,status) {
  if (!element) return;
  if (!element.firstElementChild) {
    for (const [kind,label,options] of [['api','API result',[['auto','Use API evidence'],['checked','API pass'],['failed','API fail'],['unchecked','Unchecked']]],['human','Human result',[['unchecked','Not checked'],['pass','Pass'],['fail','Fail']]]]) {
      const field=node('label','',label), choice=node('select'); choice.dataset.resultKind=kind;
      choice.id=element.id+'-'+kind; field.htmlFor=choice.id;
      for (const [value,text] of options) { const option=node('option','',text); option.value=value; choice.append(option); }
      field.append(choice); element.append(field);
    }
    const hint=node('small','muted','Saved signal result. New attempts keep it. Changes send no PLC command.');
    const error=node('small','inline-alert hidden'); error.setAttribute('role','alert'); error.dataset.resultError='';
    element.append(hint,error);
  }
  for (const choice of element.querySelectorAll('select')) {
    const kind=choice.dataset.resultKind, decision=kind==='api' ? savedManualApiDecision(tag,status) : savedHumanDecision(tag,status);
    const value=decision?.value ?? (kind==='api' ? 'auto' : 'unchecked');
    if (document.activeElement!==choice) choice.value=value;
    choice.disabled=!tag || !status?.mode || !status?.api_address;
    choice.onchange=()=>{
      const error=element.querySelector('[data-result-error]');
      try { saveManualDecision(tag,status,kind,choice.value); error.classList.add('hidden'); window.dispatchEvent(new Event('signal-results-changed')); }
      catch { choice.value=value; error.textContent='Result could not be saved. Your previous result is retained.'; error.classList.remove('hidden'); }
    };
  }
}
