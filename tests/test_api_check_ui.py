"""Separate API/human labels and filters use only the isolated fake API."""
import json
import time

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
