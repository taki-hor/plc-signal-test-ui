"""Candidate mapping checks use intercepted runs and the isolated loopback API."""
import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from test_frontend_safety import browser, harness, pytestmark
from test_verifier_ui import intercept_test, start_test

CASE = 'tank01-filterremote'
COMMAND = 'Tank01_FilterRemote'
FEEDBACK = 'Tank01_FilterStatus'


def candidate_reply(browser,mode='manual0',missing_receipt=False,baseline=None):
    state = browser[0]
    response = {'result':'OBSERVED','test_name':'Tank 01 FilterRemote','command':COMMAND+'=1',
                'expected_feedback':FEEDBACK+'=1','actual_feedback':1,'elapsed_ms':1260,'http_status':200,
                'mapping_under_test':True,'end_mode':mode,'command_address':'M320',
                'write_response':{'written':True,'tag_name':COMMAND,'value':1,'console_command_address':'M320'}}
    if not missing_receipt:
        response['write_response'].update(console_accepted_at=datetime.now(timezone.utc).isoformat(),
                                          console_command_baseline_utc=baseline or state['last_poll'])
    intercept_test(browser,response)
    return response


def open_candidate(browser):
    _, _, _, js, wait_for = browser
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')")
    js("document.querySelector('[data-test-id="+CASE+"] button[data-run-test]').click()")
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    assert js('return window.testRequests') == []


def test_candidates_are_available_as_mappings_under_test_not_configured_passes(browser):
    state, _, _, js, wait_for = browser
    candidate_reply(browser)
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return document.querySelectorAll('[data-test-id] button[data-needs-confirmation=true]').length===36")
    assert js("return [...document.querySelectorAll('[data-test-id] button[data-needs-confirmation=true]')].every(button=>!button.disabled)")
    assert js("return [...document.querySelectorAll('[data-test-id] button[data-needs-confirmation=true]')].every(button=>{const badge=button.closest('[data-test-id]').querySelector('.test-status');return badge.dataset.state==='MAPPING UNDER TEST'&&badge.textContent.toUpperCase().includes('MAPPING UNDER TEST')})")
    assert not state['writes'] and js('return window.testRequests') == []


@pytest.mark.parametrize('mode',['manual0','hold'])
def test_candidate_opt_in_and_end_mode_are_sent_only_after_single_confirmation(browser,mode):
    state, _, _, js, wait_for = browser
    candidate_reply(browser,mode)
    open_candidate(browser)
    assert 'mapping' in js("return document.getElementById('confirm-body').textContent").lower()
    assert 'under test' in js("return document.getElementById('confirm-body').textContent").lower()
    assert js("return document.getElementById('test-mode-hold').checked")
    js("document.getElementById('test-mode-hold').click()" if mode=='hold' else "document.getElementById('test-mode-manual').click()")
    assert not state['writes'] and js('return window.testRequests') == []
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('OBSERVED')")
    assert js('return window.testRequests') == [{'id':CASE,'mapping_under_test':True,'end_mode':mode}]
    assert js("return document.querySelector('[data-test-id="+CASE+"] .test-status').dataset.state") == 'MAPPING UNDER TEST'
    assert js("return document.getElementById('test-result-state').dataset.state") == 'OBSERVED'
    assert '1260 ms' in js("return document.getElementById('test-backend-result').textContent")
    assert not state['writes']


@pytest.mark.parametrize('mode',['manual0','hold'])
def test_cancelled_candidate_confirmation_never_runs_or_writes(browser,mode):
    state, _, _, js, wait_for = browser
    candidate_reply(browser,mode)
    start_test(browser,CASE,mode=mode,accept=False)
    time.sleep(.2)
    assert js('return window.testRequests') == []
    assert not state['writes']
    assert js("return document.getElementById('test-result-state').textContent") == 'No run selected. Review the pair, then run a test when ready.'


@pytest.mark.parametrize('legacy_receipt',[False,True])
def test_candidate_manual_zero_uses_same_page_same_tag_and_one_confirmation(browser,legacy_receipt):
    state, _, _, js, wait_for = browser
    candidate_reply(browser)
    start_test(browser,CASE,mode='manual0')
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('OBSERVED')")
    state['values'].update({COMMAND:1,FEEDBACK:1})
    wait_for("return !document.getElementById('test-send-zero').disabled")
    before = js("return document.getElementById('test-backend-result').textContent")
    if legacy_receipt:
        js("window.legacyClearFetch=window.fetch;window.fetch=async function(url,options){const response=await window.legacyClearFetch(url,options);if(url!=='/api/write')return response;const data=await response.json();delete data.console_command_address;data.device_address='M320';return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
    js("document.getElementById('test-send-zero').click()")
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    assert COMMAND in js("return document.getElementById('confirm-body').textContent")
    assert not state['writes']
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes'] == [{'tag_name':COMMAND,'value':0}]
    assert js('return window.testRequests') == [{'id':CASE,'mapping_under_test':True,'end_mode':'manual0'}]
    assert js('return location.hash') == '#/verify'
    assert js("return document.getElementById('test-backend-result').textContent") == before
    assert js("return document.getElementById('test-result-state').dataset.state") == 'OBSERVED'


@pytest.mark.parametrize('guard',['readonly','stale'])
def test_candidate_run_rechecks_guards_when_confirmation_is_accepted(browser,guard):
    state, _, _, js, wait_for = browser
    candidate_reply(browser)
    open_candidate(browser)
    if guard=='readonly':
        state['mode'] = False
        wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    else:
        state['fault'] = 'signals_503'
        wait_for("return document.getElementById('api-state').textContent==='DISCONNECTED'")
    js("document.getElementById('confirm-yes').click()")
    time.sleep(.2)
    assert js('return window.testRequests') == []
    assert not state['writes']


@pytest.mark.parametrize('backend_result',['OBSERVED','TIMEOUT'])
def test_candidate_hold_needs_accepted_receipt_and_later_fresh_one_without_extra_write(browser,backend_result):
    state, _, _, js, wait_for = browser
    state['freeze_stamp'] = state['last_poll']
    response = candidate_reply(browser,'hold')
    response['result'] = backend_result
    js('window.testReply='+json.dumps(response))
    start_test(browser,CASE,mode='hold')
    wait_for("return document.getElementById('test-result-state').dataset.state==="+json.dumps(backend_result))
    state['values'].update({COMMAND:1,FEEDBACK:1 if backend_result=='OBSERVED' else 0})
    wait_for("return document.getElementById('test-command-readback').textContent==='1'")
    assert js("return document.getElementById('test-hold-state').dataset.state") == 'WAITING'
    state['freeze_stamp'] = None
    wait_for("return document.getElementById('test-hold-state').dataset.state==='KEPT AT 1'")
    assert js("return document.getElementById('test-result-state').dataset.state") == backend_result
    assert js('return window.testRequests') == [{'id':CASE,'mapping_under_test':True,'end_mode':'hold'}]
    assert not state['writes']


@pytest.mark.parametrize('missing_receipt',[False,True])
def test_candidate_hold_rejects_cached_final_baseline_or_missing_receipt(browser,missing_receipt):
    state, _, _, js, wait_for = browser
    final_baseline = (datetime.now(timezone.utc)+timedelta(seconds=2)).isoformat()
    state['freeze_stamp'] = final_baseline
    candidate_reply(browser,'hold',missing_receipt=missing_receipt,baseline=final_baseline)
    start_test(browser,CASE,mode='hold')
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    state['values'].update({COMMAND:1,FEEDBACK:1})
    wait_for("return document.getElementById('test-command-readback').textContent==='1'")
    assert js("return document.getElementById('test-hold-state').dataset.state") == ('UNVERIFIABLE' if missing_receipt else 'WAITING')
    state['freeze_stamp'] = (datetime.fromisoformat(final_baseline)+timedelta(milliseconds=1)).isoformat()
    if missing_receipt:
        time.sleep(.4)
        assert js("return document.getElementById('test-hold-state').dataset.state") == 'UNVERIFIABLE'
    else:
        wait_for("return document.getElementById('test-hold-state').dataset.state==='KEPT AT 1'")
    assert not state['writes']


@pytest.mark.parametrize('guard',['readonly','stale'])
def test_candidate_hold_qualification_waits_for_write_mode_and_live_connection(browser,guard):
    state, wd, prefix, js, wait_for = browser
    state['freeze_stamp'] = state['last_poll']
    candidate_reply(browser,'hold')
    start_test(browser,CASE,mode='hold')
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    if guard=='readonly':
        state['mode'] = False
        wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    else:
        state['fault'] = 'signals_503'
        wait_for("return document.getElementById('api-state').textContent==='DISCONNECTED'")
    state['values'].update({COMMAND:1,FEEDBACK:1})
    state['freeze_stamp'] = None
    time.sleep(.3)
    assert js("return document.getElementById('test-hold-state').dataset.state") != 'KEPT AT 1'
    if guard=='readonly':
        js("document.getElementById('mode-btn').click()")
        wd(prefix+'/alert/accept',{})
    else:
        state['fault'] = None
    wait_for("return document.getElementById('test-hold-state').dataset.state==='KEPT AT 1'")
    assert js('return window.testRequests') == [{'id':CASE,'mapping_under_test':True,'end_mode':'hold'}]
    assert not state['writes']


def test_observed_result_and_raw_one_do_not_replace_a_confirmed_write_receipt(browser):
    state, _, _, js, wait_for = browser
    response = candidate_reply(browser,'hold')
    response['write_response']['written'] = False
    js('window.testReply='+json.dumps(response))
    start_test(browser,CASE,mode='hold')
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    state['values'].update({COMMAND:1,FEEDBACK:1})
    wait_for("return document.getElementById('test-command-readback').textContent==='1'")
    assert js("return document.getElementById('test-hold-state').dataset.state") == 'UNVERIFIABLE'
    assert not state['writes']


def test_previous_held_command_remains_visible_after_another_test_and_reload(browser):
    state, wd, prefix, js, wait_for = browser
    candidate_reply(browser,'hold')
    start_test(browser,CASE,mode='hold')
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    state['values'].update({COMMAND:1,FEEDBACK:1})
    wait_for("return document.getElementById('test-hold-state').dataset.state==='KEPT AT 1'")
    wait_for("return document.getElementById('test-active-command-list').textContent.includes('Tank01_FilterRemote')")
    next_reply={'result':'PASS','test_name':'Tank 01 Door Open','command':'Tank01_DoorOpenRemote=1',
                'expected_feedback':'Tank01_DoorOpened=1','actual_feedback':1,'elapsed_ms':2300,'http_status':200}
    js('window.testReply='+json.dumps(next_reply))
    start_test(browser,'tank01-door-open')
    wait_for("return document.getElementById('test-result-state').dataset.state==='PASS'")
    assert js("return document.getElementById('test-active-command-list').textContent.includes('Tank01_FilterRemote')")
    assert js("return document.getElementById('test-active-commands').getClientRects().length>0")
    assert js('return window.testRequests') == [{'id':CASE,'mapping_under_test':True,'end_mode':'hold'},
                                               {'id':'tank01-door-open','end_mode':'manual0'}]
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('test-active-command-list').textContent.includes('Tank01_FilterRemote')")
    assert js("return document.getElementById('test-active-commands').getClientRects().length>0")
    assert js("return document.getElementById('write-banner-title').textContent") == 'READ-ONLY MODE'
    assert not state['writes']


@pytest.mark.parametrize('clear_outcome',['blocked','unknown'])
def test_pending_hold_cannot_be_promoted_after_manual_zero_attempt(browser,clear_outcome):
    state, _, _, js, wait_for = browser
    state['freeze_stamp'] = state['last_poll']
    candidate_reply(browser,'hold')
    start_test(browser,CASE,mode='hold')
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    state['values'].update({COMMAND:1,FEEDBACK:1})
    wait_for("return !document.getElementById('test-send-zero').disabled")
    state['clear_hold'] = True
    state['clear_outcome'] = clear_outcome
    js("window.candidateZeroFetch=window.fetch;window.candidateZeroPosts=[];window.fetch=(url,options)=>{if(url==='/api/write')window.candidateZeroPosts.push(JSON.parse(options.body));return window.candidateZeroFetch(url,options)};document.getElementById('test-send-zero').click();document.getElementById('confirm-yes').click()")
    assert state['clear_entered'].wait(2)
    state['freeze_stamp'] = None
    time.sleep(.4)
    assert js("return document.getElementById('test-hold-state').dataset.state") != 'KEPT AT 1'
    state['clear_release'].set()
    expected='CLEAR BLOCKED BEFORE DISPATCH' if clear_outcome=='blocked' else 'CLEAR OUTCOME UNKNOWN'
    wait_for("return document.getElementById('test-clear-state').textContent==="+json.dumps(expected))
    time.sleep(.3)
    assert js("return document.getElementById('test-hold-state').dataset.state") != 'KEPT AT 1'
    assert js('return window.candidateZeroPosts') == [{'tag_name':COMMAND,'value':0}]
    assert not state['writes']


def test_pending_candidate_can_explicitly_clear_fresh_current_zero_once_on_same_page(browser):
    state, _, _, js, wait_for = browser
    candidate_reply(browser)
    start_test(browser,CASE,mode='manual0')
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    state['values'].update({COMMAND:1,FEEDBACK:1})
    wait_for("return document.getElementById('test-command-readback').textContent==='1'")
    state['values'][COMMAND] = 0
    wait_for("return document.getElementById('test-command-readback').textContent==='0'")
    wait_for("return !document.getElementById('test-send-zero').disabled")
    assert not state['writes']
    js("document.getElementById('test-send-zero').click()")
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    assert 'Current value0' in js("return document.getElementById('confirm-body').textContent")
    assert COMMAND in js("return document.getElementById('confirm-body').textContent")
    assert not state['writes']
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes'] == [{'tag_name':COMMAND,'value':0}]
    assert js('return location.hash') == '#/verify'
    assert js('return window.testRequests') == [{'id':CASE,'mapping_under_test':True,'end_mode':'manual0'}]
    assert js("return document.getElementById('test-result-state').dataset.state") == 'OBSERVED'


def test_reload_shows_pending_manual_clear_even_when_current_command_is_zero(browser):
    state, wd, prefix, js, wait_for = browser
    candidate_reply(browser)
    start_test(browser,CASE,mode='manual0')
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    state['values'].update({COMMAND:1,FEEDBACK:1})
    wait_for("return document.getElementById('test-command-readback').textContent==='1'")
    state['values'][COMMAND] = 0
    wait_for("return document.getElementById('test-command-readback').textContent==='0'")
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'")
    wait_for("return document.getElementById('test-active-command-list').textContent.includes('Pending manual clear:')")
    assert COMMAND in js("return document.getElementById('test-active-command-list').textContent")
    assert js("return document.getElementById('test-active-commands').getClientRects().length>0")
    assert js("return document.getElementById('write-banner-title').textContent") == 'READ-ONLY MODE'
    candidate_reply(browser)
    js("document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for("return document.getElementById('write-banner-title').textContent==='WRITE TEST MODE ENABLED'")
    assert js("return document.querySelector('[data-test-id=tank01-filterremote] button[data-run-test]').disabled&&!document.querySelector('[data-test-id=tank01-door-open] button[data-run-test]').disabled")
    js("document.querySelector('[data-test-id=tank01-filterremote] button[data-run-test]').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert js('return window.testRequests') == []
    assert js("return performance.getEntriesByType('resource').filter(entry=>['/api/write','/api/test/run'].includes(new URL(entry.name).pathname)).length") == 0
    assert not state['writes']



def test_acted_candidate_with_unconfirmed_ack_remains_pending_and_can_be_cleared(browser):
    state, _, _, js, wait_for=browser
    reply=candidate_reply(browser)
    reply.update(result='COMMUNICATION ERROR',write_dispatched=True,write_response=None,error='Supplier returned a non-object acknowledgement')
    js('window.testReply='+json.dumps(reply))
    start_test(browser,CASE)
    wait_for("return document.getElementById('test-result-state').dataset.state==='COMMUNICATION ERROR'")
    state['values'][COMMAND]=1
    wait_for("return document.getElementById('test-command-readback').textContent==='1'")
    record=js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST')).at(-1)")
    assert not record.get('oneRejectedAt') and not record.get('holdOneAt')
    assert record['feedbackState']=='OUTCOME UNKNOWN'
    assert js("return document.getElementById('test-active-command-list').textContent.includes('Pending manual clear: Tank01_FilterRemote')")
    assert js("return document.querySelector('[data-test-id=tank01-filterremote] button[data-run-test]').disabled&&!document.querySelector('[data-test-id=tank01-door-open] button[data-run-test]').disabled")
    assert not js("return document.getElementById('test-send-zero').disabled")
    assert not state['writes']


@pytest.mark.parametrize('address_evidence',['wrong_trusted','wrong_legacy','missing'])
def test_wrong_or_missing_clear_address_never_verifies_zero_or_drops_pending_record(browser,address_evidence):
    state, _, _, js, wait_for=browser
    candidate_reply(browser)
    start_test(browser,CASE)
    wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
    state['values'][COMMAND]=1
    wait_for("return !document.getElementById('test-send-zero').disabled")
    change={
        'wrong_trusted':"data.console_command_address='M999';data.device_address='M320';",
        'wrong_legacy':"delete data.console_command_address;data.device_address='M999';",
        'missing':"delete data.console_command_address;delete data.device_address;",
    }[address_evidence]
    js("window.clearIdentityFetch=window.fetch;window.fetch=async function(url,options){const response=await window.clearIdentityFetch(url,options);if(url!=='/api/write')return response;const data=await response.json();"+change+"return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('test-send-zero').click();document.getElementById('confirm-yes').click()")
    expected='API ACCEPTED 0 — READBACK UNVERIFIABLE' if address_evidence=='missing' else 'CLEAR OUTCOME UNKNOWN'
    wait_for("return document.getElementById('test-clear-state').textContent==="+json.dumps(expected))
    wait_for("return document.getElementById('test-command-readback').textContent==='0'")
    time.sleep(.4)
    assert js("return document.getElementById('test-clear-state').textContent") == expected
    record=js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST')).at(-1)")
    assert record['zeroRequestedAt'] and not record.get('zeroSeenAt')
    assert js("return document.getElementById('test-active-command-list').textContent.includes('Pending manual clear: Tank01_FilterRemote')")
    assert js("return document.querySelector('[data-test-id=tank01-filterremote] button[data-run-test]').disabled&&!document.querySelector('[data-test-id=tank01-door-open] button[data-run-test]').disabled")
    assert state['writes'] == [{'tag_name':COMMAND,'value':0}]
