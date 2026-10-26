"""Saved judgments survive unjudged attempts; these tests use only the fake API."""
import json
import time

import pytest

from test_frontend_safety import browser,harness,pytestmark,choose_command,manual_write
from test_feedback_card_results import saved_record,TAG,KEY


def load(browser,records):
    _,wd,prefix,js,wait_for=browser
    js('localStorage.setItem('+json.dumps(KEY)+','+json.dumps(json.dumps(records))+')')
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&Boolean(document.querySelector('[data-command-tag="+TAG+"]'))")


@pytest.mark.parametrize('result',['pass','fail'])
def test_new_attempt_preserves_saved_signal_judgment_without_copying_it(browser,result):
    state,wd,prefix,js,wait_for=browser
    previous=saved_record(result,finishedAt=int(time.time()*1000)-1000)
    load(browser,[previous]);choose_command(browser,TAG)
    row="document.querySelector('[data-command-tag="+TAG+"]')"
    assert js('return '+row+'.dataset.operatorResult')==result
    assert not js("return document.getElementById('bool-new').disabled")
    js("document.getElementById('bool-new').click()")
    assert js('return '+row+'.dataset.operatorResult')==result
    records=js('return JSON.parse(localStorage.getItem('+json.dumps(KEY)+'))')
    assert len(records)==2 and records[0]==previous
    assert not records[-1].get('operatorResult') and not records[-1].get('operatorCompletedAt')
    assert js("return document.querySelector('[data-test-id=tank01-door-open]').dataset.operatorResult")==result
    wd(prefix+'/refresh',{})
    wait_for('return '+row+'?.dataset.operatorResult==='+json.dumps(result))
    assert not state['writes']


def module(browser):
    js,wait_for=browser[3:5]
    js("window.savedResultsModule=null;import('./js/saved-results.js').then(module=>window.savedResultsModule=module)")
    wait_for('return Boolean(window.savedResultsModule)')
    js("window.resultContext={mode:'MOCK',api_address:'BROWSER TEST'};window.resultTag={tag_name:'Tank01_DoorOpenRemote',device_address:'M300',data_type:'Bool',read_write:'W',multiplier:1}")


def test_explicit_manual_reset_survives_polling_and_context_changes_without_altering_history(browser):
    state,wd,prefix,js,wait_for=browser
    previous=saved_record('pass');load(browser,[previous]);module(browser)
    js("window.savedResultsModule.saveManualDecision(window.resultTag,window.resultContext,'human','unchecked');window.dispatchEvent(new Event('signal-results-changed'))")
    assert js("return window.savedResultsModule.savedHumanDecision(window.resultTag,window.resultContext).value")=='unchecked'
    assert js('return JSON.parse(localStorage.getItem('+json.dumps(KEY)+'))')==[previous]
    assert js("return window.savedResultsModule.savedHumanDecision({...window.resultTag,device_address:'M999'},window.resultContext)") is None
    assert js("return window.savedResultsModule.savedHumanDecision(window.resultTag,{...window.resultContext,mode:'REAL'})") is None
    assert js("return window.savedResultsModule.savedHumanDecision(window.resultTag,{...window.resultContext,api_address:'OTHER'})") is None
    wd(prefix+'/refresh',{})
    wait_for("return document.querySelector('[data-command-tag=Tank01_DoorOpenRemote]')?.dataset.operatorResult==='unchecked'")
    module(browser)
    decisions=js('return window.savedResultsModule.manualDecisions(window.resultContext)')
    assert len(decisions)==1 and decisions[0]['previous_value']=='pass' and decisions[0]['write_sent'] is False
    assert not state['writes']


def test_api_manual_judgments_append_audit_and_auto_releases_override_without_writes(browser):
    state,_,_,js,_=browser;module(browser)
    js("for(const value of ['checked','failed','unchecked','auto'])window.savedResultsModule.saveManualDecision(window.resultTag,window.resultContext,'api',value)")
    records=js('return window.savedResultsModule.manualDecisions(window.resultContext)')
    assert [row['value'] for row in records]==['checked','failed','unchecked','auto']
    assert [row['previous_value'] for row in records]==[None,'checked','failed','unchecked']
    assert all(row['write_sent'] is False for row in records)
    assert js('return window.savedResultsModule.savedManualApiDecision(window.resultTag,window.resultContext).value')=='auto'
    assert not state['writes']


def test_corrupt_manual_audit_cannot_be_overwritten_by_a_new_choice(browser):
    state,_,_,js,_=browser;module(browser)
    js("localStorage.setItem('plc-signal-results:v1:MOCK:BROWSER TEST','broken');window.manualSaveBlocked=false;try{window.savedResultsModule.saveManualDecision(window.resultTag,window.resultContext,'human','pass')}catch{window.manualSaveBlocked=true}")
    assert js('return window.manualSaveBlocked') is True
    assert js("return localStorage.getItem('plc-signal-results:v1:MOCK:BROWSER TEST')")=='broken'
    assert not state['writes']


def test_value_signal_judgment_survives_pruned_unjudged_history(browser):
    state,wd,prefix,js,wait_for=browser
    manual_write(browser,'Tank01_TempSV',25)
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('READ SNAPSHOT RECORDED')")
    js("const choice=document.getElementById('write-feedback-operator-result');choice.value='pass';choice.dispatchEvent(new Event('change'))")
    module(browser)
    # Read the captured identity rather than assuming the supplier's address/scaling.
    js("const record=JSON.parse(localStorage.getItem('plc-value-feedback:v1:MOCK:BROWSER TEST')).at(-1);const [tag_name,device_address,data_type,read_write,multiplier]=record.identities[0];window.valueTag={tag_name,device_address,data_type,read_write,multiplier};const drafts=Array.from({length:50},(_,index)=>({...record,id:'unjudged-'+index,operatorResult:undefined,operatorResultAt:undefined,operatorCompletedAt:undefined,operatorEvents:undefined}));localStorage.setItem('plc-value-feedback:v1:MOCK:BROWSER TEST',JSON.stringify(drafts))")
    assert js("return window.savedResultsModule.savedHumanDecision(window.valueTag,window.resultContext).value")=='pass'
    assert js("return window.savedResultsModule.savedHumanDecision({...window.valueTag,device_address:'D9999'},window.resultContext)") is None
    assert len(state['writes'])==1


@pytest.mark.parametrize('identity',['changed','missing'])
def test_historical_value_mark_cannot_promote_a_different_or_unidentified_signal(browser,identity):
    state,wd,prefix,js,wait_for=browser
    name='Tank01_FilterRemote'
    stamp=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    record={'id':'historical-value-write','requested_at':stamp,'accepted_at':stamp,'writes':[{'tag_name':name,'value':1}],
            'identities':[[name,'M320','Bool','W',1]],'state':'READ SNAPSHOT RECORDED','feedback':[]}
    if identity=='missing':record.pop('identities')
    js("localStorage.setItem('plc-value-feedback:v1:MOCK:BROWSER TEST',"+json.dumps(json.dumps([record]))+")")
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.getElementById('write-tag').options.length>0")
    js("document.querySelector('[data-nav=write]').click();document.getElementById('write-tag').value='Tank01_FilterRemote';document.getElementById('write-tag').dispatchEvent(new Event('change'))")
    if identity=='changed':
        js("window.metadataFetch=window.fetch;window.fetch=async(url,options)=>{const response=await window.metadataFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();data.tags=data.tags.map(tag=>tag.tag_name==='Tank01_FilterRemote'?{...tag,device_address:'M999'}:tag);return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
        wait_for("return document.getElementById('write-detail').textContent.includes('M999')")
    assert not js("return document.getElementById('write-feedback-operator-result').disabled")
    js("const choice=document.getElementById('write-feedback-operator-result');choice.value='pass';choice.dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('write-feedback-operator-state').textContent")=='PASS — YOUR CHECK'
    assert js("return document.querySelector('#write-saved-results [data-result-kind=human]').value")=='unchecked'
    assert js("return document.getElementById('write-api-state').dataset.apiState")=='unchecked'
    assert js("return JSON.parse(localStorage.getItem('plc-value-feedback:v1:MOCK:BROWSER TEST'))[0].operatorResult")=='pass'
    assert js("return JSON.parse(localStorage.getItem('plc-signal-results:v1:MOCK:BROWSER TEST')??'[]').length")==0
    assert not state['writes']


def test_server_human_cache_rejects_contextless_naive_or_automatic_rows_and_keeps_last_import(browser):
    state,_,_,js,_=browser;module(browser)
    entry={'kind':'human','identity':[TAG,'M300','Bool','W',1],'value':'pass','at':'2026-10-25T01:00:00Z',
           'source':'Operator-confirmed CLI run','write_sent':False,'physical_stop_verified':False}
    state['operator_results']=[entry]
    js('window.serverHumanEntry='+json.dumps(entry))
    assert js("return window.savedResultsModule.setServerHumanDecisions({context:window.resultContext,operator_results:[window.serverHumanEntry]},window.resultContext)") is True
    js("window.rejectedImports=[{operator_results:[]},{context:{...window.resultContext,mode:'REAL'},operator_results:[]},{context:window.resultContext,operator_results:[{...window.serverHumanEntry,at:'2026-10-25T01:00:00'}]},{context:window.resultContext,operator_results:[{...window.serverHumanEntry,kind:'api'}]},{context:window.resultContext,operator_results:[],operator_results_error:'Temporary human-store failure'},{context:window.resultContext,error:'Transport unavailable'}]")
    assert js('return window.rejectedImports.every(data=>!window.savedResultsModule.setServerHumanDecisions(data,window.resultContext))') is True
    assert js('return window.savedResultsModule.savedHumanDecision(window.resultTag,window.resultContext).value')=='pass'
    assert js('return window.savedResultsModule.importedHumanDecisions(window.resultContext)[0].physical_stop_verified') is False
    assert js("return window.savedResultsModule.savedHumanDecision(window.resultTag,{...window.resultContext,mode:'REAL'})") is None
    assert not state['writes']


def test_imported_api_pass_preserves_human_fail_automated_evidence_and_newer_local_choices(browser):
    state,wd,prefix,js,wait_for=browser;module(browser)
    name='Tank01_FilterRemote'
    identity=[name,'M320','Bool','W',1]
    human={'kind':'human','identity':identity,'value':'fail','at':'2026-10-25T01:00:00Z',
           'source':'Operator observed no movement','write_sent':False}
    api={**human,'kind':'api','value':'checked','at':'2026-10-25T02:00:00Z','source':'Operator API-only Pass'}
    state['api_checks']=[{'tag_name':name,'api_status':'failed','identity':identity,
                         'checked_at':'2026-10-25T03:00:00Z','basis':'Command and related status','detail':'Mapped feedback timed out'}]
    state['operator_results']=[human,api]
    row="document.querySelector('[data-command-tag="+name+"]')"
    wait_for('return '+row+"?.dataset.operatorResult==='fail' && "+row+".querySelector('.api-check-badge').dataset.apiState==='checked'")
    js("window.resultTag={...window.resultTag,tag_name:'Tank01_FilterRemote',device_address:'M320'};document.querySelector('[data-command-tag=Tank01_FilterRemote]').click()")
    assert js("return document.getElementById('bool-saved-results-human').value")=='fail'
    assert js("return document.getElementById('bool-saved-results-api').value")=='checked'
    assert 'Latest automated result: API fail' in js("return document.getElementById('bool-api-state-detail').textContent")
    assert 'Mapped feedback timed out' in js("return document.getElementById('bool-api-state-detail').textContent")
    assert js('return window.savedResultsModule.importedHumanDecisions(window.resultContext).length')==1
    js("localStorage.setItem('plc-signal-results:v1:MOCK:BROWSER TEST',JSON.stringify([{kind:'api',identity:"+json.dumps(identity)+",value:'failed',at:'2026-10-25T01:30:00Z'}]))")
    assert js('return window.savedResultsModule.savedManualApiDecision(window.resultTag,window.resultContext).value')=='checked'
    js("window.savedResultsModule.saveManualDecision(window.resultTag,window.resultContext,'api','auto');window.dispatchEvent(new Event('signal-results-changed'))")
    assert js("return document.getElementById('bool-api-state').textContent")=='API fail'
    assert js("return document.getElementById('bool-saved-results-human').value")=='fail'
    wd(prefix+'/refresh',{})
    wait_for('return '+row+"?.dataset.operatorResult==='fail' && "+row+".querySelector('.api-check-badge').dataset.apiState==='failed'")
    module(browser)
    js("window.resultTag={...window.resultTag,tag_name:'Tank01_FilterRemote',device_address:'M320'}")
    assert js('return window.savedResultsModule.savedManualApiDecision(window.resultTag,window.resultContext).value')=='auto'
    assert js("return window.savedResultsModule.savedManualApiDecision({...window.resultTag,device_address:'M999'},window.resultContext)") is None
    assert js("return window.savedResultsModule.savedManualApiDecision(window.resultTag,{...window.resultContext,mode:'REAL'})") is None
    for button in ('bool-export-json','write-feedback-export-json'):
        js("window.importedResultExport=null;URL.createObjectURL=blob=>{blob.text().then(text=>window.importedResultExport=text);return 'blob:imported-results'};HTMLAnchorElement.prototype.click=function(){};document.getElementById("+json.dumps(button)+").click()")
        wait_for('return window.importedResultExport!==null')
        exported=json.loads(js('return window.importedResultExport'))
        assert exported['imported_human_decisions']==[human]
        assert exported['imported_api_decisions']==[api]
        assert exported['manual_decisions'][-1]['value']=='auto'
    assert not state['writes']
