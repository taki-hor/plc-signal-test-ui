"""End-mode choices use the loopback fake API; no supplier writes are possible."""
import json
import time
from datetime import datetime, timedelta

import pytest

from test_frontend_safety import browser, harness, pytestmark, choose_command, checklist_write

KEY = 'plc-command-checklist:v1:MOCK:BROWSER TEST'
FILTER = 'Tank01_FilterRemote'
RECORD = "JSON.parse(localStorage.getItem(" + json.dumps(KEY) + ")||'[]').findLast(r=>r.tag_name===" + json.dumps(FILTER) + ")"


def choose_hold(browser):
    _, _, _, js, _ = browser
    assert not js("return document.getElementById('bool-mode-hold').disabled")
    js("document.getElementById('bool-mode-hold').click()")
    assert js("return document.getElementById('bool-mode-hold').checked")


def last_record(browser):
    return browser[3]('return ' + RECORD)


def start_frozen_hold(browser):
    state, _, _, _, _ = browser
    choose_command(browser,FILTER)
    choose_hold(browser)
    state['freeze_stamp'] = state['last_poll']
    checklist_write(browser,1)


def test_default_manual_zero_does_not_automatically_keep_or_clear(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser,FILTER)
    assert js("return document.getElementById('bool-mode-manual').checked")
    assert js("return document.getElementById('bool-one').textContent") == 'Send 1…'
    checklist_write(browser,1)
    wait_for("return document.getElementById('bool-value').textContent==='1'")
    time.sleep(.3)
    record = last_record(browser)
    assert record['endMode'] == 'manual0' and not record.get('holdOneAt')
    assert js("return document.getElementById('bool-mode-manual').disabled&&document.getElementById('bool-mode-hold').disabled")
    choose_command(browser,'Tank01_DoorOpenRemote')
    assert js("return document.getElementById('bool-one').disabled")
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


def test_hold_choice_is_confirmed_once_then_kept_without_another_write(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser,FILTER)
    choose_hold(browser)
    assert js("return document.getElementById('bool-one').textContent") == 'Set & hold 1…'
    js("document.getElementById('bool-one').click()")
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    assert 'After 1Hold at 1' in js("return document.getElementById('confirm-body').textContent")
    js("document.getElementById('confirm-dialog').close('cancel')")
    time.sleep(.1)
    assert not state['writes'] and last_record(browser) is None
    checklist_write(browser,1)
    wait_for("return document.getElementById('bool-result').textContent==='KEPT AT 1'")
    record = last_record(browser)
    assert record['endMode'] == 'hold' and record['endModeConfirmedAt'] and record['holdOneAt']
    assert not record.get('zeroAcceptedAt') and not record.get('zeroSeenAt')
    held_event = next(event for event in record['events'] if event.get('automatic_local_record'))
    assert held_event['write_sent'] is False and held_event['end_mode'] == 'hold'
    assert js("return !document.getElementById('bool-held').classList.contains('hidden')")
    choose_command(browser,'Tank01_DoorOpenRemote')
    assert not js("return document.getElementById('bool-one').disabled")
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


def test_hold_mode_is_locked_after_send_and_completes_while_another_tag_is_selected(browser):
    state, _, _, js, wait_for = browser
    start_frozen_hold(browser)
    assert js("return document.getElementById('bool-mode-manual').disabled")
    js("document.getElementById('bool-mode-manual').click()")
    assert js("return document.getElementById('bool-mode-hold').checked")
    assert last_record(browser)['endMode'] == 'hold'
    choose_command(browser,'Tank01_FillWaterOn')
    assert js("return document.getElementById('bool-mode-manual').checked")
    state['freeze_stamp'] = None
    wait_for('return Boolean((' + RECORD + ')?.holdOneAt)')
    assert not js("return document.getElementById('bool-one').disabled")
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


@pytest.mark.parametrize('action',['Open','Close'])
def test_doors_remain_manual_zero_after_completion(browser,action):
    state, _, _, js, wait_for = browser
    tag='Tank01_Door'+action+'Remote'
    choose_command(browser,tag)
    assert js("return document.getElementById('bool-mode-manual').checked&&document.getElementById('bool-mode-hold').disabled")
    js("document.getElementById('bool-mode-hold').click()")
    checklist_write(browser,1)
    state['values']['Tank01_Door'+('Opened' if action=='Open' else 'Closed')] = 1
    wait_for("return document.getElementById('bool-completion').textContent==='CONFIRMED'")
    assert js("return document.getElementById('bool-result').textContent") == 'NEEDS 0'
    assert js("return document.getElementById('bool-held').classList.contains('hidden')")
    assert state['writes'] == [{'tag_name':tag,'value':1}]


@pytest.mark.parametrize('missing_baseline',[False,True])
def test_auto_keep_requires_new_final_backend_readback(browser,missing_baseline):
    state, _, _, js, wait_for = browser
    choose_command(browser,FILTER)
    choose_hold(browser)
    state['validation_advance'] = True
    state['omit_baseline'] = missing_baseline
    checklist_write(browser,1)
    stamp = state['freeze_stamp']
    wait_for("return document.getElementById('poll-time').textContent===new Date("+json.dumps(stamp)+").toLocaleString()")
    time.sleep(.3)
    assert not last_record(browser).get('holdOneAt')
    state['freeze_stamp'] = (datetime.fromisoformat(stamp)+timedelta(milliseconds=1)).isoformat()
    if missing_baseline:
        time.sleep(.5)
        assert not last_record(browser).get('holdOneAt')
        assert 'final pre-write timestamp' in js("return document.getElementById('bool-write-hint').textContent")
    else:
        wait_for('return Boolean(('+RECORD+')?.holdOneAt)')
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


@pytest.mark.parametrize('unavailable',['readonly','disconnected'])
def test_auto_keep_waits_for_write_mode_and_fresh_connection(browser,unavailable):
    state, wd, prefix, js, wait_for = browser
    start_frozen_hold(browser)
    if unavailable=='readonly':
        js("document.getElementById('mode-btn').click()")
        wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    else:
        state['fault'] = 'signals_503'
        wait_for("return document.getElementById('api-state').textContent==='DISCONNECTED'")
    state['freeze_stamp'] = None
    time.sleep(.4)
    assert not last_record(browser).get('holdOneAt')
    if unavailable=='readonly':
        js("document.getElementById('mode-btn').click()")
        wd(prefix+'/alert/accept',{})
    else:
        state['fault'] = None
    wait_for('return Boolean(('+RECORD+')?.holdOneAt)')
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


@pytest.mark.parametrize('fault',['unknown','before_dispatch'])
def test_unknown_or_rejected_one_is_never_promoted_to_held(browser,fault):
    state, _, _, js, wait_for = browser
    choose_command(browser,FILTER)
    choose_hold(browser)
    state['write_fault'] = fault
    js("document.getElementById('bool-one').click();document.getElementById('confirm-yes').click()")
    expected='OUTCOME UNKNOWN' if fault=='unknown' else 'BLOCKED'
    wait_for("return document.getElementById('bool-completion').textContent==="+json.dumps(expected))
    state['values'][FILTER] = 1
    wait_for("return document.getElementById('bool-value').textContent==='1'")
    time.sleep(.3)
    assert not last_record(browser).get('holdOneAt')
    assert js("return document.getElementById('bool-mode-hold').disabled") is (fault=='unknown')
    assert not state['writes']


@pytest.mark.parametrize('outcome',['accepted','blocked','unknown'])
def test_attempted_clear_prevents_automatic_hold_even_if_one_remains(browser,outcome):
    state, _, _, js, wait_for = browser
    start_frozen_hold(browser)
    state['clear_hold'] = True
    state['clear_outcome'] = outcome
    js("document.getElementById('bool-zero').click();document.getElementById('confirm-yes').click()")
    assert state['clear_entered'].wait(2)
    state['freeze_stamp'] = None
    wait_for("return document.getElementById('bool-value').textContent==='1'")
    assert not last_record(browser).get('holdOneAt')
    state['clear_release'].set()
    wait_for('return ('+RECORD+").events.some(e=>/^(API accepted 0|Write 0 blocked|Write 0 outcome)/.test(e.action))")
    time.sleep(.4)
    record = last_record(browser)
    assert record['zeroRequestedAt'] and not record.get('holdOneAt')
    assert [w['value'] for w in state['writes']] == ([1,0] if outcome=='accepted' else [1])


def test_reloading_pending_hold_requires_new_write_mode_without_resending(browser):
    state, wd, prefix, js, wait_for = browser
    start_frozen_hold(browser)
    confirmed_at = last_record(browser)['endModeConfirmedAt']
    url=wd(prefix+'/url')
    wd(prefix+'/url',{'url':url})
    wait_for("return document.querySelectorAll('[data-command-tag]').length===102")
    choose_command(browser,FILTER)
    state['freeze_stamp'] = None
    wait_for("return document.getElementById('bool-value').textContent==='1'")
    assert js("return document.getElementById('write-banner-title').textContent") == 'READ-ONLY MODE'
    assert not last_record(browser).get('holdOneAt')
    assert last_record(browser)['endModeConfirmedAt'] == confirmed_at
    js("document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for('return Boolean(('+RECORD+')?.holdOneAt)')
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


def test_address_change_prevents_pending_hold_from_applying_to_new_endpoint(browser):
    state, _, _, js, wait_for = browser
    start_frozen_hold(browser)
    js("window.catalogModeFetch=window.fetch;window.fetch=async function(url,options){const response=await window.catalogModeFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();data.tags=data.tags.map(t=>t.tag_name==='Tank01_FilterRemote'?{...t,device_address:'M999'}:t);return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
    wait_for("return document.getElementById('bool-address').textContent==='M999'")
    state['freeze_stamp'] = None
    time.sleep(.4)
    assert not last_record(browser).get('holdOneAt')
    assert js("return document.getElementById('bool-mode-manual').checked")
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


def test_new_api_context_does_not_inherit_hold_choice_or_records(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser,FILTER)
    choose_hold(browser)
    checklist_write(browser,1)
    wait_for('return Boolean(('+RECORD+')?.holdOneAt)')
    js("window.scopeModeFetch=window.fetch;window.fetch=async function(url,options){const response=await window.scopeModeFetch(url,options);if(url!=='/api/status')return response;const data=await response.json();data.api_address='BROWSER TEST SECOND API';return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
    wait_for("return document.getElementById('api-address').textContent==='BROWSER TEST SECOND API'")
    assert js("return document.getElementById('bool-held').classList.contains('hidden')")
    assert js("return document.getElementById('bool-mode-manual').checked")
    assert last_record(browser)['holdOneAt']
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


def test_operator_issue_prevents_automatic_hold(browser):
    state, _, _, js, wait_for = browser
    start_frozen_hold(browser)
    js("document.getElementById('bool-issue').click()")
    state['freeze_stamp'] = None
    wait_for("return document.getElementById('bool-value').textContent==='1'")
    time.sleep(.3)
    assert last_record(browser)['issueAt'] and not last_record(browser).get('holdOneAt')
    assert js("return document.getElementById('bool-result').textContent") == 'ISSUE'
    assert state['writes'] == [{'tag_name':FILTER,'value':1}]


def test_legacy_attempt_requires_explicit_keep_instead_of_assumed_mode(browser):
    state, wd, prefix, js, wait_for = browser
    started = int(time.time()*1000)-3000
    baseline = datetime.fromtimestamp((started+500)/1000).astimezone().isoformat()
    accepted = datetime.fromtimestamp((started+1000)/1000).astimezone().isoformat()
    legacy = {'id':'legacy-hold-choice','tag_name':FILTER,'address':'M305','startedAt':started,
              'oneRequestedAt':started,'oneAcceptedAt':started+1000,'oneServerAt':accepted,
              'oneBaselineUtc':baseline,'oneCommandBaselineUtc':baseline,
              'feedbackState':'NO CONFIRMED MAPPING','events':[]}
    # Use the real catalogue address rather than relying on a fixture's suffix mapping.
    choose_command(browser,FILTER)
    legacy['address'] = js("return document.getElementById('bool-address').textContent")
    state['values'][FILTER] = 1
    js('localStorage.setItem('+json.dumps(KEY)+','+json.dumps(json.dumps([legacy]))+')')
    url=wd(prefix+'/url');wd(prefix+'/url',{'url':url})
    wait_for("return document.querySelectorAll('[data-command-tag]').length===102")
    choose_command(browser,FILTER)
    js("document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for("return !document.getElementById('bool-keep').disabled")
    assert not last_record(browser).get('holdOneAt')
    assert js("return !document.getElementById('bool-keep').classList.contains('hidden')")
    js("document.getElementById('bool-keep').click()")
    assert last_record(browser)['holdOneAt']
    assert not state['writes']


@pytest.mark.parametrize('identity',['api','mode','address'])
def test_unsent_hold_draft_resets_when_endpoint_identity_changes(browser,identity):
    state, _, _, js, wait_for = browser
    choose_command(browser,FILTER)
    choose_hold(browser)
    assert last_record(browser) is None
    if identity=='address':
        path='/api/tags'
        change="data.tags=data.tags.map(t=>t.tag_name==='Tank01_FilterRemote'?{...t,device_address:'M999'}:t);"
        updated="return document.getElementById('bool-address').textContent==='M999'"
    else:
        path='/api/status'
        change="data.api_address='UNSENT DRAFT SECOND API';" if identity=='api' else "data.mode='REAL';"
        updated=("return document.getElementById('api-address').textContent==='UNSENT DRAFT SECOND API'" if identity=='api'
                 else "return document.getElementById('mock-badge').classList.contains('hidden')")
    js("window.draftIdentityFetch=window.fetch;window.fetch=async function(url,options){const response=await window.draftIdentityFetch(url,options);if(url!=="+json.dumps(path)+")return response;const data=await response.json();"+change+"return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
    wait_for(updated)
    assert js("return document.getElementById('bool-mode-manual').checked&&!document.getElementById('bool-mode-hold').checked")
    assert js("return document.getElementById('bool-one').textContent") == 'Send 1…'
    assert last_record(browser) is None
    assert not state['writes']


@pytest.mark.parametrize('value',[1,0])
@pytest.mark.parametrize('address_evidence',['wrong_trusted','wrong_legacy','missing','matching_legacy'])
def test_manual_write_requires_matching_receipt_address_before_verifying_readback(browser,value,address_evidence):
    state, _, _, js, wait_for = browser
    choose_command(browser,FILTER)
    if value==0: checklist_write(browser,1)
    else: choose_hold(browser)
    address=js("return document.getElementById('bool-address').textContent")
    change={
        'wrong_trusted':"data.console_command_address='M999';data.device_address="+json.dumps(address)+";",
        'wrong_legacy':"delete data.console_command_address;data.device_address='M999';",
        'missing':"delete data.console_command_address;delete data.device_address;",
        'matching_legacy':"delete data.console_command_address;data.device_address="+json.dumps(address)+";",
    }[address_evidence]
    js("window.receiptAddressFetch=window.fetch;window.fetch=async function(url,options){const response=await window.receiptAddressFetch(url,options);if(url!=='/api/write')return response;const data=await response.json();"+change+"return new Response(JSON.stringify(data),{status:response.status,headers:{'Content-Type':'application/json'}})}")
    if address_evidence=='matching_legacy':
        checklist_write(browser,value)
        if value==1:
            wait_for("return document.getElementById('bool-result').textContent==='KEPT AT 1'")
            assert last_record(browser)['holdOneAt']
        else:
            wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
            assert last_record(browser)['zeroSeenAt']
    else:
        control='bool-one' if value==1 else 'bool-zero'
        js("document.getElementById("+json.dumps(control)+").click();document.getElementById('confirm-yes').click()")
        wait_for("return document.getElementById('bool-log').textContent.includes('Write receipt address does not match')")
        wait_for("return document.getElementById('bool-value').textContent==="+json.dumps(str(value)))
        record=last_record(browser)
        assert not record.get('oneRejectedAt') and not record.get('holdOneAt') and not record.get('zeroSeenAt')
        assert not record.get('oneAcceptedAt' if value==1 else 'zeroAcceptedAt')
        if value==1: assert record['feedbackState']=='OUTCOME UNKNOWN'
        assert js("return !document.getElementById('bool-pending').classList.contains('hidden')")
        choose_command(browser,'Tank01_HeaterRemote')
        assert js("return document.getElementById('bool-one').disabled")
    assert state['writes']==[{'tag_name':FILTER,'value':v} for v in ([1] if value==1 else [1,0])]
