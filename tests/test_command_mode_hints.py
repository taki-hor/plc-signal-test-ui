"""Manual hints are guidance only; these checks use the loopback fake API."""
import json

import pytest

from server.config import ROOT
from test_frontend_safety import browser, harness, pytestmark, choose_command
from test_verifier_ui import intercept_test

TAGS=json.loads((ROOT/'config/mock-tags.json').read_text())['tags']


def test_manual_hold_hints_are_limited_and_never_claim_unconfirmed_rules_are_verified(browser):
    state, _, _, js, wait_for=browser
    commands=[tag for tag in TAGS if tag['read_write']=='W' and tag['data_type']=='Bool']
    template=next(tag for tag in commands if tag['tag_name']=='MainInlet')
    probes=commands+[{**template,'tag_name':'Unknown_FillWaterOn'},{**template,'tag_name':'Tank17_FilterRemote'}]
    js("window.hintRules=null;import('/js/command-guidance.js').then(({commandGuidance})=>window.hintRules="+json.dumps(probes)+".map(tag=>({name:tag.tag_name,...commandGuidance(tag)})))")
    wait_for('return window.hintRules!==null')
    rules=js('return window.hintRules')
    hinted=[rule for rule in rules if rule.get('hint')=='hold']
    assert len(hinted)==47 and all(rule['kind']=='hold' and not rule.get('confirmed') for rule in hinted)
    assert {rule['name'] for rule in rules if rule.get('confirmed')} == {'Tank01_DoorOpenRemote','Tank01_DoorCloseRemote'}
    assert all(not rule.get('hint') for rule in rules if rule['name'].endswith(('Auto','RemoteStart')))
    assert all(not rule.get('hint') and not rule.get('confirmed') for rule in rules[-2:])
    assert not state['writes']


def test_hint_markers_preserve_manual_page_choice_and_select_feedback_manual_suggestion(browser):
    state, _, _, js, wait_for=browser
    choose_command(browser,'Tank01_FilterRemote')
    assert js("return !document.getElementById('bool-hold-hint').classList.contains('hidden')&&document.getElementById('bool-hold-hint').textContent==='Hint'")
    assert js("return document.getElementById('bool-mode-manual').checked")
    js("document.getElementById('bool-mode-hold').click()")
    initial=js("return document.getElementById('poll-time').textContent")
    wait_for("return document.getElementById('poll-time').textContent!=="+json.dumps(initial))
    assert js("return document.getElementById('bool-mode-hold').checked")
    js("document.getElementById('bool-mode-manual').click();document.getElementById('refresh-btn').click()")
    initial=js("return document.getElementById('poll-time').textContent")
    wait_for("return document.getElementById('poll-time').textContent!=="+json.dumps(initial))
    assert js("return document.getElementById('bool-mode-manual').checked")
    for name in ['Tank02_AirAgitationAuto','Tank01_RemoteStart']:
        choose_command(browser,name)
        assert js("return document.getElementById('bool-hold-hint').classList.contains('hidden')&&document.getElementById('bool-mode-manual').checked")
    choose_command(browser,'Tank01_DoorOpenRemote')
    assert js("return !document.getElementById('bool-manual-confirmed').classList.contains('hidden')&&document.getElementById('bool-manual-confirmed').textContent==='Confirmed'")
    choose_command(browser,'Tank03_DoorOpenRemote')
    assert js("return document.getElementById('bool-manual-confirmed').classList.contains('hidden')")
    intercept_test(browser)
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')")
    js("document.querySelector('[data-test-id=tank01-filterremote] button[data-run-test]').click()")
    assert js("return document.getElementById('confirm-body').querySelector('[data-mode-hint=hold]').textContent") == 'Hint'
    assert js("return document.getElementById('test-mode-hold').checked")
    js("document.getElementById('test-mode-manual').click()")
    assert js("return document.getElementById('test-mode-manual').checked")
    js("document.getElementById('confirm-dialog').close('cancel')")
    assert js('return window.testRequests') == []
    assert js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST')||'[]').length") == 0
    assert not state['writes']


def open_feedback_confirmation(browser,case_id):
    _, _, _, js, wait_for=browser
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')")
    wait_for("return !document.querySelector('[data-test-id="+case_id+"] button[data-run-test]').disabled")
    js("document.querySelector('[data-test-id="+case_id+"] button[data-run-test]').click()")
    assert js("return document.getElementById('confirm-dialog').open")


@pytest.mark.parametrize('case_id',['tank01-filterremote','tank01-heaterremote','tank01-usremote','tank01-fillwateron'])
def test_feedback_initially_selects_qualified_manual_hold_without_running_on_open_or_cancel(browser,case_id):
    state, _, _, js, _=browser
    intercept_test(browser)
    open_feedback_confirmation(browser,case_id)
    assert js("return document.getElementById('test-mode-hold').checked&&!document.getElementById('test-mode-manual').checked")
    evidence=js("return document.getElementById('test-mode-hold-hint').title").lower()
    assert 'inferred' in evidence and 'not specified' in evidence
    assert js("return document.querySelector('[data-test-id="+case_id+"] .test-status').dataset.state")=='MAPPING UNDER TEST'
    assert js('return window.testRequests')==[] and not state['writes']
    js("document.getElementById('confirm-dialog').close('cancel')")
    assert js('return window.testRequests')==[] and not state['writes']
    assert js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST')||'[]').length")==0


@pytest.mark.parametrize('command',['Tank02_AirAgitationAuto','Tank01_RemoteStart','Unknown_FillWaterOn'])
def test_feedback_without_a_manual_clear_suggestion_keeps_manual_zero_default(browser,command):
    state, _, _, js, wait_for=browser
    intercept_test(browser)
    extra={**next(tag for tag in TAGS if tag['tag_name']=='MainInlet'),'tag_name':command,'device_address':'M999'}
    js("window.fallbackModeFetch=window.fetch;window.fetch=async function(url,options){const response=await window.fallbackModeFetch(url,options);if(!['/api/tags','/api/test/cases','/api/signals'].includes(url))return response;const data=await response.json();if(url==='/api/tags'&&!data.tags.some(tag=>tag.tag_name==="+json.dumps(command)+"))data.tags.push("+json.dumps(extra)+");if(url==='/api/test/cases')data.tests=data.tests.map(test=>test.id==='tank01-filterremote'?{...test,command_tag:"+json.dumps(command)+"}:test);if(url==='/api/signals')data["+json.dumps(command)+"]=0;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
    wait_for("return document.querySelector('[data-test-id=tank01-filterremote]').textContent.includes("+json.dumps(command)+")")
    open_feedback_confirmation(browser,'tank01-filterremote')
    assert js("return document.getElementById('test-mode-manual').checked&&!document.getElementById('test-mode-hold').checked")
    assert js("return document.getElementById('test-mode-hold-hint')===null")
    js("document.getElementById('confirm-dialog').close('cancel')")
    assert js('return window.testRequests')==[] and not state['writes']


@pytest.mark.parametrize('case_id',['tank01-door-open','tank03-door-open'])
def test_feedback_doors_have_no_hold_choice(browser,case_id):
    state, _, _, js, _=browser
    intercept_test(browser)
    open_feedback_confirmation(browser,case_id)
    assert js("return document.getElementById('test-mode-hold')===null&&document.getElementById('test-mode-manual')===null")
    assert 'Send 0 after physical movement finishes' in js("return document.getElementById('confirm-body').textContent")
    js("document.getElementById('confirm-dialog').close('cancel')")
    assert js('return window.testRequests')==[] and not state['writes']


def test_feedback_operator_can_override_manual_hold_default_before_single_write_confirmation(browser):
    state, _, _, js, wait_for=browser
    intercept_test(browser,{'result':'OBSERVED','actual_feedback':1,'elapsed_ms':123,'http_status':200})
    open_feedback_confirmation(browser,'tank01-filterremote')
    assert js("return document.getElementById('test-mode-hold').checked")
    js("document.getElementById('test-mode-manual').click()")
    assert js('return window.testRequests')==[] and not state['writes']
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    assert js('return window.testRequests')==[{'id':'tank01-filterremote','end_mode':'manual0','mapping_under_test':True}]
    assert js("return document.querySelector('[data-test-id=tank01-filterremote] .test-status').dataset.state")=='MAPPING UNDER TEST'
    assert not state['writes']
