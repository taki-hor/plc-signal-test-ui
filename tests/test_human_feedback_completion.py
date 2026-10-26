"""Human checks and feedback wait limits use only the loopback fake API."""
import json

import pytest

from test_frontend_safety import browser, harness, pytestmark, choose_command
from test_verifier_ui import intercept_test, start_test

KEY = 'plc-command-checklist:v1:MOCK:BROWSER TEST'


def set_wait(browser, value):
    browser[3]("const input=document.getElementById('test-timeout');input.value="+json.dumps(str(value))+";input.dispatchEvent(new Event('input'))")


def records(browser):
    return browser[3]('return JSON.parse(localStorage.getItem('+json.dumps(KEY)+')||"[]")')


@pytest.mark.parametrize('case_id,command,api_result',[
    ('tank01-door-open','Tank01_DoorOpenRemote','PASS'),
    ('tank01-filterremote','Tank01_FilterRemote','OBSERVED'),
    ('tank01-heaterremote','Tank01_HeaterRemote','TIMEOUT'),
])
def test_feedback_results_need_a_human_mark_without_changing_api_evidence_or_pending_clear(browser,case_id,command,api_result):
    state, _, _, js, wait_for=browser
    intercept_test(browser,{'result':api_result,'actual_feedback':0 if api_result=='TIMEOUT' else 1,'elapsed_ms':1234,'http_status':200})
    start_test(browser,case_id)
    wait_for("return document.getElementById('test-result-state').dataset.state==="+json.dumps(api_result))
    assert js("return document.getElementById('test-operator-state').textContent")=='AWAITING YOUR CHECK'
    assert not records(browser)[-1].get('operatorCompletedAt')
    assert js("return document.getElementById('bool-progress').textContent.startsWith('0 / 102')")
    before=js("return document.getElementById('test-backend-result').textContent")
    requests=js('return window.testRequests')
    state['mode']=False
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    assert not js("return document.getElementById('test-operator-result').disabled")
    js("const choice=document.getElementById('test-operator-result');choice.value='pass';choice.dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('test-operator-state').textContent")=='PASS — YOUR CHECK'
    assert records(browser)[-1]['operatorCompletedAt']
    js("const choice=document.getElementById('test-operator-result');choice.value='fail';choice.dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('test-operator-state').textContent")=='FAIL — YOUR CHECK'
    assert records(browser)[-1]['issueAt'] and not records(browser)[-1].get('operatorCompletedAt')
    js("const choice=document.getElementById('test-operator-result');choice.value='unchecked';choice.dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('test-operator-state').textContent")=='AWAITING YOUR CHECK'
    assert not records(browser)[-1].get('issueAt')
    js("const choice=document.getElementById('test-operator-result');choice.value='pass';choice.dispatchEvent(new Event('change'))")
    assert records(browser)[-1]['operatorCompletedAt']
    assert js("return document.getElementById('test-backend-result').textContent")==before
    assert any(event.get('backend_result')==api_result for event in records(browser)[-1]['events'])
    assert not records(browser)[-1].get('zeroRequestedAt')
    assert js("return !document.getElementById('bool-pending').classList.contains('hidden')")
    choose_command(browser,command)
    assert js("return document.getElementById('bool-operator-state').textContent")=='PASS — YOUR CHECK'
    js("document.getElementById('bool-mark-incomplete').click()")
    assert js("return document.getElementById('test-operator-state').textContent")=='AWAITING YOUR CHECK'
    assert not records(browser)[-1].get('operatorCompletedAt')
    assert js("return document.getElementById('test-backend-result').textContent")==before
    assert js('return window.testRequests')==requests
    assert not state['writes']


@pytest.mark.parametrize('seconds',[1,75,300])
def test_feedback_wait_limit_is_confirmed_captured_and_extends_only_this_request(browser,seconds):
    state, _, _, js, wait_for=browser
    intercept_test(browser,{'result':'TIMEOUT','actual_feedback':0,'elapsed_ms':1234,'http_status':200})
    js("window.abortLimits=[];window.originalAbortTimeout=AbortSignal.timeout;AbortSignal.timeout=function(ms){window.abortLimits.push(ms);return window.originalAbortTimeout.call(AbortSignal,ms)}")
    set_wait(browser,seconds)
    js("document.querySelector('[data-nav=verify]').click();document.querySelector('[data-test-id=tank01-door-open] button[data-run-test]').click()")
    assert str(seconds)+' seconds' in js("return document.getElementById('confirm-body').textContent")
    assert js('return window.testRequests')==[]
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-result-state').dataset.state==='TIMEOUT'")
    assert js('return window.testRequests')==[{'id':'tank01-door-open','end_mode':'manual0','timeout_ms':seconds*1000}]
    assert seconds*1000+30000 in js('return window.abortLimits')
    assert records(browser)[-1]['timeout_ms']==seconds*1000
    assert any(event.get('timeout_ms')==seconds*1000 for event in records(browser)[-1]['events'])
    set_wait(browser,15)
    assert js("return document.getElementById('test-active-timeout').textContent")==str(seconds)+' seconds'
    assert js("return [...document.querySelectorAll('[data-wait-limit]')].every(cell=>cell.textContent==='15 s')")
    js("window.savedCases=null;fetch('/api/test/cases').then(r=>r.json()).then(data=>window.savedCases=data.tests)")
    wait_for('return window.savedCases!==null')
    assert js('return window.savedCases.every(test=>test.timeout_ms===15000)')
    assert not state['writes']


@pytest.mark.parametrize('value',['',0,-1,301,1.5])
def test_invalid_feedback_wait_limit_disables_runs_without_dispatch(browser,value):
    state, _, _, js, _=browser
    intercept_test(browser)
    set_wait(browser,value)
    assert js("return document.getElementById('test-timeout').getAttribute('aria-invalid')")=='true'
    assert js("return [...document.querySelectorAll('[data-test-id] button[data-run-test]')].every(button=>button.disabled)")
    js("document.querySelector('[data-test-id=tank01-door-open] button[data-run-test]').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert js('return window.testRequests')==[]
    assert not state['writes']


def test_changing_wait_limit_during_confirmation_blocks_dispatch(browser):
    state, _, _, js, wait_for=browser
    intercept_test(browser)
    assert js("return document.getElementById('test-timeout').value")=='15'
    js("document.querySelector('[data-nav=verify]').click();document.querySelector('[data-test-id=tank01-door-open] button[data-run-test]').click()")
    set_wait(browser,60)
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-result-state').dataset.state==='BLOCKED'")
    assert js('return window.testRequests')==[]
    assert not records(browser)
    assert not state['writes']


def test_editing_next_wait_limit_does_not_change_active_test_or_allow_early_human_completion(browser):
    state, _, _, js, wait_for=browser
    intercept_test(browser,hold=True)
    set_wait(browser,75)
    start_test(browser)
    wait_for("return typeof window.releaseTest==='function'")
    assert js("return document.getElementById('test-operator-result').disabled")
    set_wait(browser,15)
    assert js("return document.getElementById('test-active-timeout').textContent")=='75 seconds'
    assert records(browser)[-1]['timeout_ms']==75000
    js('window.releaseTest()')
    wait_for("return document.getElementById('test-result-state').dataset.state==='PASS'")
    assert js("return document.getElementById('test-operator-state').textContent")=='AWAITING YOUR CHECK'
    assert js("return document.getElementById('test-timeout').value")=='15'
    assert js("return document.getElementById('test-active-timeout').textContent")=='75 seconds'
    assert not records(browser)[-1].get('operatorCompletedAt')
    assert not state['writes']
