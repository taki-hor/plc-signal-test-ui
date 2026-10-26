"""Separate API/human labels and filters use only the isolated fake API."""
import json
import time

import pytest

from server.config import ROOT
from test_frontend_safety import browser,harness,pytestmark

TAGS={tag['tag_name']:tag for tag in json.loads((ROOT/'config/mock-tags.json').read_text())['tags']}


def record(name,state):
    tag=TAGS[name]
    return {'tag_name':name,'api_status':state,'identity':[name,tag['device_address'],tag['data_type'],tag['read_write'],tag['multiplier']],
            'checked_at':'2026-10-26T03:00:00+00:00','basis':'Command and related status','detail':'Verified first-pass evidence'}


def seed(browser):
    state,_,_,js,wait_for=browser
    state['api_checks']=[record('Tank01_FilterRemote','checked'),record('Tank01_USRemote','checked'),record('Tank07_CoolerAuto','checked'),record('Tank03_FilterRemote','failed')]
    state['api_check_error']=None;state['api_check_context']={'mode':'MOCK','api_address':'BROWSER TEST'}
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .api-check-badge').dataset.apiState==='checked'")


def choose_filter(browser,element,value):
    browser[3]('const e=document.getElementById('+json.dumps(element)+');e.value='+json.dumps(value)+";e.dispatchEvent(new Event('input'));e.dispatchEvent(new Event('change'))")


def visible_manual(js):
    return js("return [...document.querySelectorAll('[data-command-tag]:not(.hidden)')].map(e=>e.dataset.commandTag)")


def test_api_labels_and_filters_are_shared_but_never_set_a_human_pass(browser):
    state,_,_,js,wait_for=browser;seed(browser)
    js("location.hash='#/commands'")
    choose_filter(browser,'bool-api-filter','checked')
    assert set(visible_manual(js))=={'Tank01_FilterRemote','Tank01_USRemote','Tank07_CoolerAuto'}
    choose_filter(browser,'bool-api-filter','failed')
    assert visible_manual(js)==['Tank03_FilterRemote']
    choose_filter(browser,'bool-api-filter','unchecked')
    assert 'Tank01_HeaterRemote' in visible_manual(js) and 'Tank01_FilterRemote' not in visible_manual(js)
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .manual-result-badge').textContent")=='Not checked'
    js("location.hash='#/verify'");choose_filter(browser,'test-api-filter','checked')
    assert set(js("return [...document.querySelectorAll('[data-test-id]:not(.hidden)')].map(e=>e.dataset.testId)"))=={'tank01-filterremote','tank01-usremote'}
    choose_filter(browser,'test-api-filter','failed')
    assert js("return [...document.querySelectorAll('[data-test-id]:not(.hidden)')].map(e=>e.dataset.testId)")==['tank03-filterremote']
    assert js("return document.querySelector('[data-test-id=tank01-filterremote] [data-card-result]').dataset.cardResult")=='unchecked'
    assert not state['writes']


def test_needs_human_filter_preserves_existing_physical_marks(browser):
    state,wd,prefix,js,wait_for=browser;seed(browser)
    now=int(time.time()*1000)
    saved=[{'id':'physical-check','tag_name':'Tank01_FilterRemote','address':'M320','startedAt':now,'events':[],
            'operatorResult':'pass','operatorCompletedAt':now,'operatorResultAt':now}]
    js("localStorage.setItem('plc-command-checklist:v1:MOCK:BROWSER TEST',"+json.dumps(json.dumps(saved))+")")
    wd(prefix+'/refresh',{})
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .manual-result-badge')?.textContent==='✓ Pass'")
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .api-check-badge').dataset.apiState==='checked'")
    choose_filter(browser,'bool-api-filter','needs-human')
    assert set(visible_manual(js))=={'Tank01_USRemote','Tank07_CoolerAuto'}
    choose_filter(browser,'test-api-filter','needs-human')
    assert js("return [...document.querySelectorAll('[data-test-id]:not(.hidden)')].map(e=>e.dataset.testId)")==['tank01-usremote']
    assert js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST'))[0].operatorResult")=='pass'
    assert not state['writes']


def test_value_selector_filters_without_losing_access_or_sending_commands(browser):
    state,_,_,js,wait_for=browser;seed(browser)
    js("location.hash='#/write'");choose_filter(browser,'write-api-filter','failed')
    assert js("return [...document.getElementById('write-tag').options].filter(e=>!e.hidden).map(e=>e.value)")==['Tank03_FilterRemote']
    assert js("return document.getElementById('write-api-state').textContent")=='API fail'
    choose_filter(browser,'write-api-filter','checked')
    assert set(js("return [...document.getElementById('write-tag').options].filter(e=>!e.hidden).map(e=>e.value)"))=={'Tank01_FilterRemote','Tank01_USRemote','Tank07_CoolerAuto'}
    choose_filter(browser,'write-api-filter','all')
    assert js("return [...document.getElementById('write-tag').options].filter(e=>!e.hidden).length")==141
    assert not state['writes']


def test_changed_context_or_metadata_cannot_inherit_an_api_check(browser):
    state,_,_,js,wait_for=browser;seed(browser)
    state['api_checks'][0]['identity'][1]='M999'
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .api-check-badge').dataset.apiState==='unchecked'")
    state['api_check_context']={'mode':'REAL','api_address':'OTHER API'}
    wait_for("return document.querySelector('[data-command-tag=Tank01_USRemote] .api-check-badge').dataset.apiState==='unchecked'")
    assert not js("return document.getElementById('api-check-error').classList.contains('hidden')")
    assert not state['writes']


def test_api_pass_label_and_transient_refresh_error_preserve_saved_results(browser):
    state,_,_,js,wait_for=browser;seed(browser)
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .api-check-badge').textContent")=='API pass'
    state['api_check_error']='Temporary result-store connection failure'
    wait_for("return !document.getElementById('api-check-error').classList.contains('hidden')")
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .api-check-badge').dataset.apiState")=='checked'
    assert not state['writes']


def test_human_pass_backfills_api_pass_but_newer_failure_stays_visible(browser):
    state,_,_,js,wait_for=browser;seed(browser)
    tag=TAGS['Tank01_HeaterRemote']
    identity=[tag['tag_name'],tag['device_address'],tag['data_type'],tag['read_write'],tag['multiplier']]
    decisions=[{'identity':identity,'kind':'human','value':'pass','at':'2026-10-25T01:00:00Z'}]
    js("localStorage.setItem('plc-signal-results:v1:MOCK:BROWSER TEST',"+json.dumps(json.dumps(decisions))+");window.dispatchEvent(new Event('signal-results-changed'))")
    wait_for("return document.querySelector('[data-command-tag=Tank01_HeaterRemote] .api-check-badge').textContent==='API pass'")
    assert 'Human-confirmed' in js("return document.querySelector('[data-command-tag=Tank01_HeaterRemote] .api-check-badge').title")
    state['api_checks'].append(record('Tank01_HeaterRemote','failed'))
    wait_for("return document.querySelector('[data-command-tag=Tank01_HeaterRemote] .api-check-badge').textContent==='API fail'")
    assert js("return document.querySelector('[data-command-tag=Tank01_HeaterRemote]').dataset.operatorResult")=='pass'
    assert not state['writes']


def test_manual_result_controls_work_without_a_write_and_keep_an_audit(browser):
    state,wd,prefix,js,wait_for=browser;seed(browser)
    js("location.hash='#/commands';document.querySelector('[data-command-tag=Tank01_HeaterRemote]').click()")
    choose_filter(browser,'bool-saved-results-human','pass')
    assert js("return document.querySelector('[data-command-tag=Tank01_HeaterRemote]').dataset.operatorResult")=='pass'
    choose_filter(browser,'bool-saved-results-api','failed')
    assert js("return document.getElementById('bool-api-state').textContent")=='API fail'
    choose_filter(browser,'bool-saved-results-api','unchecked')
    assert js("return document.getElementById('bool-api-state').textContent")=='Unchecked'
    saved=js("return JSON.parse(localStorage.getItem('plc-signal-results:v1:MOCK:BROWSER TEST'))")
    assert [row['value'] for row in saved]==['pass','failed','unchecked']
    assert all(row['write_sent'] is False for row in saved)
    wd(prefix+'/refresh',{})
    wait_for("return document.querySelector('[data-command-tag=Tank01_HeaterRemote]')?.dataset.operatorResult==='pass'")
    assert js("return document.querySelector('[data-command-tag=Tank01_HeaterRemote] .api-check-badge').textContent")=='Unchecked'
    assert not state['writes']


def test_manual_api_override_displays_newer_automated_failure_and_can_release_override(browser):
    state,_,_,js,wait_for=browser;seed(browser)
    js("location.hash='#/commands';document.querySelector('[data-command-tag=Tank03_FilterRemote]').click()")
    choose_filter(browser,'bool-saved-results-api','checked')
    assert js("return document.getElementById('bool-api-state').textContent")=='API pass'
    assert 'Latest automated result: API fail' in js("return document.getElementById('bool-api-state-detail').textContent")
    choose_filter(browser,'bool-saved-results-api','auto')
    assert js("return document.getElementById('bool-api-state').textContent")=='API fail'
    assert not state['writes']


def test_feedback_identity_change_cannot_backfill_an_old_human_pass(browser):
    state,_,_,js,wait_for=browser;seed(browser)
    tag=TAGS['Tank01_FilterRemote']
    identity=[tag['tag_name'],tag['device_address'],tag['data_type'],tag['read_write'],tag['multiplier']]
    decisions=[{'identity':identity,'kind':'human','value':'pass','at':'2026-10-25T01:00:00Z'}]
    js("localStorage.setItem('plc-signal-results:v1:MOCK:BROWSER TEST',"+json.dumps(json.dumps(decisions))+")")
    state['api_checks'][0].update(api_status='unchecked',identity_valid=False,detail='Feedback metadata changed; previous API check no longer applies.')
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .api-check-badge').dataset.apiState==='unchecked'")
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote]').dataset.operatorResult")=='pass'
    assert not state['writes']


def human_record(name,at='2026-10-25T05:00:00Z',observed_at='2026-10-25T04:00:00Z'):
    tag=TAGS[name]
    return {'kind':'human','identity':[name,tag['device_address'],tag['data_type'],tag['read_write'],tag['multiplier']],
            'value':'pass','at':at,'source':'Operator-confirmed CLI run','evidence_ref':'logs/cli-run/report.json',
            'observed_at':observed_at,'physical_stop_verified':False,'write_sent':False}


def seed_humans(browser,names):
    state,_,_,_,wait_for=browser
    state['operator_results']=[human_record(name) for name in names]
    wait_for("return "+json.dumps(names)+".every(name=>document.querySelector('[data-command-tag=\"'+name+'\"]')?.dataset.operatorResult==='pass')")


def test_explicit_cli_pass_import_updates_33_human_badges_without_actuation_or_stop_claim(browser):
    state,_,_,js,wait_for=browser
    names=[tag['tag_name'] for tag in TAGS.values() if tag['read_write']=='W' and tag['data_type']=='Bool' and 'Door' not in tag['tag_name']][:33]
    assert len(names)==33;seed_humans(browser,names)
    assert js("return [...document.querySelectorAll('[data-command-tag]')].filter(row=>row.dataset.operatorResult==='pass').length")==33
    name=names[0]
    js("document.querySelector('[data-command-tag=\""+name+"\"]').click()")
    assert 'Operator-confirmed CLI run' in js("return document.getElementById('bool-saved-results-human').title")
    assert 'Physical stop not confirmed' in js("return document.getElementById('bool-saved-results-human').title")
    assert 'Physical stop was not confirmed' in js("return document.getElementById('bool-api-state-detail').textContent")
    js("window.serverExport=null;URL.createObjectURL=blob=>{blob.text().then(text=>window.serverExport=text);return 'blob:import-test'};HTMLAnchorElement.prototype.click=function(){};document.getElementById('bool-export-json').click()")
    wait_for('return window.serverExport!==null')
    exported=json.loads(js('return window.serverExport'))
    assert len(exported['imported_human_decisions'])==33
    assert all(row['physical_stop_verified'] is False for row in exported['imported_human_decisions'])
    assert not state['writes']


def test_cli_import_local_correction_wins_repeated_polling_and_empty_server_list(browser):
    state,_,_,js,wait_for=browser
    name='Tank01_FilterRemote';seed_humans(browser,[name])
    js("document.querySelector('[data-command-tag=Tank01_FilterRemote]').click()")
    choose_filter(browser,'bool-saved-results-human','unchecked')
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote]').dataset.operatorResult")=='unchecked'
    choose_filter(browser,'bool-saved-results-human','fail')
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote]').dataset.operatorResult")=='fail'
    state['operator_results']=[]
    wait_for("return JSON.parse(localStorage.getItem('plc-imported-human-results:v1:MOCK:BROWSER TEST')??'[null]').length===0")
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote]').dataset.operatorResult")=='fail'
    saved=js("return JSON.parse(localStorage.getItem('plc-signal-results:v1:MOCK:BROWSER TEST'))")
    assert [row['value'] for row in saved]==['unchecked','fail']
    assert not state['writes']


def test_cli_human_error_keeps_imported_result_and_independent_api_results_after_reload(browser):
    state,wd,prefix,js,wait_for=browser;seed(browser)
    seed_humans(browser,['Tank01_FilterRemote'])
    state['operator_results']=[];state['operator_results_error']='Human result store is temporarily unavailable'
    wait_for("return document.getElementById('api-check-error').textContent.includes('Human result store')")
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote]').dataset.operatorResult")=='pass'
    assert js("return document.querySelector('[data-command-tag=Tank03_FilterRemote] .api-check-badge').dataset.apiState")=='failed'
    wd(prefix+'/refresh',{})
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote]')?.dataset.operatorResult==='pass'")
    assert not state['writes']


@pytest.mark.parametrize('identity',['address','mode','api'])
def test_cli_human_import_is_bound_to_metadata_api_and_mode(browser,identity):
    state,_,_,js,wait_for=browser
    seed_humans(browser,['Tank01_FilterRemote'])
    endpoint='/api/tags' if identity=='address' else '/api/status'
    change="data.tags=data.tags.map(tag=>tag.tag_name==='Tank01_FilterRemote'?{...tag,device_address:'M999'}:tag);" if identity=='address' else "data.mode='REAL';" if identity=='mode' else "data.api_address='OTHER API';"
    js("window.importFetch=window.fetch;window.fetch=async(url,options)=>{const response=await window.importFetch(url,options);if(url!=="+json.dumps(endpoint)+")return response;const data=await response.json();"+change+"return new Response(JSON.stringify(data),{headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote]')?.dataset.operatorResult==='unchecked'")
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .api-check-badge').dataset.apiState")=='unchecked'
    assert not state['writes']


def test_cli_observation_time_preserves_a_later_automated_api_failure(browser):
    state,_,_,js,wait_for=browser
    state['operator_results']=[human_record('Tank01_FilterRemote',at='2026-10-26T06:00:00Z',observed_at='2026-10-26T02:00:00Z')]
    failed=record('Tank01_FilterRemote','failed');failed['checked_at']='2026-10-26T03:00:00Z'
    state['api_checks']=[failed]
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote]')?.dataset.operatorResult==='pass'")
    assert js("return document.querySelector('[data-command-tag=Tank01_FilterRemote] .api-check-badge').textContent")=='API fail'
    assert not state['writes']


def test_absent_operator_store_cannot_erase_an_imported_pass_on_reload(browser):
    state,wd,prefix,js,wait_for=browser
    seed_humans(browser,['Tank01_FilterRemote'])
    state['operator_results']=None
    wd(prefix+'/refresh',{})
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote]')?.dataset.operatorResult==='pass'")
    assert len(js("return JSON.parse(localStorage.getItem('plc-imported-human-results:v1:MOCK:BROWSER TEST'))"))==1
    assert not state['writes']
