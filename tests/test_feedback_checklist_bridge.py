"""Feedback/checklist state integration uses only the existing loopback fake API."""
import json
import time
from datetime import datetime, timezone

import pytest

from server.config import ROOT
from test_frontend_safety import browser, harness, pytestmark, choose_command

KEY = 'plc-command-checklist:v1:MOCK:BROWSER TEST'
TAGS = json.loads((ROOT/'config/mock-tags.json').read_text())['tags']
CASES = json.loads((ROOT/'config/test-cases.json').read_text())['tests']
FILTER = next(c for c in CASES if c['id']=='tank01-filterremote')
HEATER = next(c for c in CASES if c['id']=='tank01-heaterremote')


def bridge(browser):
    _, _, _, js, wait_for = browser
    js("window.bridge=null;const script=document.createElement('script');script.type='module';script.textContent=\"import * as bridge from '/js/command-checklist.js';window.bridge=bridge;\";document.body.appendChild(script)")
    wait_for('return window.bridge!==null')
    return js, wait_for


def stored(js):
    return js('return JSON.parse(localStorage.getItem('+json.dumps(KEY)+')||"[]")')


def receipt(browser, case=FILTER, result='OBSERVED'):
    state=browser[0]
    tag=next(t for t in TAGS if t['tag_name']==case['command_tag'])
    return {'result':result,'mapping_under_test':case['requires_confirmation'],'command_address':tag['device_address'],
            'elapsed_ms':123,'write_response':{'written':True,'console_command_address':tag['device_address'],'console_accepted_at':datetime.now(timezone.utc).isoformat(),
            'console_command_baseline_utc':state['last_poll']}}


def begin(browser, case=FILTER, mode='manual0'):
    js,_=bridge(browser)
    js('window.feedbackRecord=window.bridge.beginFeedbackTest('+json.dumps(case)+','+json.dumps(mode)+')')
    assert js('return Boolean(window.feedbackRecord)')


def test_bridge_preserves_other_tag_notes_and_pending_manual_zero_across_reload(browser):
    state, wd, prefix, js, wait_for=browser
    choose_command(browser,'MainInlet')
    js("document.getElementById('bool-notes').value='Another command draft';document.getElementById('bool-notes').dispatchEvent(new Event('input'))")
    begin(browser)
    js("window.bridge.finishFeedbackTest(null,null);window.bridge.finishFeedbackClear(null,null)")
    assert not js('return Boolean(window.bridge.beginFeedbackClear(window.feedbackRecord))')
    state['values'][FILTER['command_tag']]=1
    js('window.bridge.finishFeedbackTest(window.feedbackRecord,'+json.dumps(receipt(browser))+')')
    wait_for("return !document.getElementById('bool-pending').classList.contains('hidden')")
    assert js("return document.getElementById('bool-notes').value")=='Another command draft'
    assert stored(js)[-1]['feedbackState']=='OBSERVED'
    assert stored(js)[-1]['note']=='' and not stored(js)[-1].get('feedback_elapsed_ms')
    assert not js('return window.bridge.canStartFeedbackTest('+json.dumps(HEATER)+')')
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'")
    choose_command(browser,FILTER['command_tag'])
    wait_for("return document.getElementById('bool-completion').textContent==='OBSERVED'")
    assert js("return !document.getElementById('bool-pending').classList.contains('hidden')")
    assert not state['writes']


def test_multiple_feedback_attempts_retain_a_prior_verified_hold_without_extra_writes(browser):
    state, _, _, js, wait_for=browser
    begin(browser,mode='hold')
    state['values'][FILTER['command_tag']]=1
    js('window.bridge.finishFeedbackTest(window.feedbackRecord,'+json.dumps(receipt(browser))+')')
    wait_for("return Boolean(JSON.parse(localStorage.getItem("+json.dumps(KEY)+"))[0].holdOneAt)")
    assert js('return window.bridge.canStartFeedbackTest('+json.dumps(HEATER)+')')
    js('window.feedbackRecord=window.bridge.beginFeedbackTest('+json.dumps(HEATER)+',"manual0")')
    state['values'][HEATER['command_tag']]=1
    js('window.bridge.finishFeedbackTest(window.feedbackRecord,'+json.dumps(receipt(browser,HEATER))+')')
    records=stored(js)
    assert len(records)==2 and records[0]['holdOneAt'] and records[1]['endMode']=='manual0'
    assert all(r['feedbackState']=='OBSERVED' for r in records)
    assert not state['writes']


def test_blocked_test_releases_busy_but_unknown_write_stays_pending(browser):
    state, _, _, js, _=browser
    begin(browser)
    js("window.bridge.finishFeedbackTest(window.feedbackRecord,{result:'BLOCKED',write_dispatched:false,error:'Initial feedback already set'})")
    assert stored(js)[-1]['oneRejectedAt']
    assert js('return window.bridge.canStartFeedbackTest('+json.dumps(FILTER)+')')
    js('window.feedbackRecord=window.bridge.beginFeedbackTest('+json.dumps(FILTER)+',"hold")')
    js("window.bridge.finishFeedbackTest(window.feedbackRecord,null,{message:'Request outcome lost',status:502})")
    record=stored(js)[-1]
    assert record['feedbackState']=='OUTCOME UNKNOWN' and not record.get('oneAcceptedAt') and not record.get('holdOneAt')
    assert not js('return window.bridge.canStartFeedbackTest('+json.dumps(HEATER)+')')
    assert js('return Boolean(window.bridge.beginFeedbackClear(window.feedbackRecord))')
    js("window.bridge.finishFeedbackClear(window.feedbackRecord,null,{message:'Clear blocked',writeDispatched:false})")
    assert not state['writes']


@pytest.mark.parametrize('blocked',[False,True])
def test_clear_intent_moves_a_held_record_back_to_pending_until_verified(browser,blocked):
    state, _, _, js, wait_for=browser
    begin(browser,mode='hold')
    state['values'][FILTER['command_tag']]=1
    js('window.bridge.finishFeedbackTest(window.feedbackRecord,'+json.dumps(receipt(browser))+')')
    wait_for("return Boolean(JSON.parse(localStorage.getItem("+json.dumps(KEY)+"))[0].holdOneAt)")
    assert js('return Boolean(window.bridge.beginFeedbackClear(window.feedbackRecord))')
    js('window.bridge.finishFeedbackClear(window.feedbackRecord,null,'+json.dumps({'message':'Clear failure',**({'writeDispatched':False} if blocked else {})})+')')
    wait_for("return !document.getElementById('bool-pending').classList.contains('hidden')")
    assert js("return document.getElementById('bool-held').classList.contains('hidden')")
    assert not js('return window.bridge.canStartFeedbackTest('+json.dumps(HEATER)+')')
    assert stored(js)[-1]['zeroRequestedAt'] and not stored(js)[-1].get('zeroSeenAt')
    assert not state['writes']


def test_accepted_clear_cannot_verify_zero_under_a_different_catalog_address(browser):
    state, _, _, js, wait_for=browser
    begin(browser)
    state['values'][FILTER['command_tag']]=1
    js('window.bridge.finishFeedbackTest(window.feedbackRecord,'+json.dumps(receipt(browser))+')')
    assert js('return Boolean(window.bridge.beginFeedbackClear(window.feedbackRecord))')
    clear={'written':True,'console_command_address':'M320','console_accepted_at':datetime.now(timezone.utc).isoformat(),'console_command_baseline_utc':state['last_poll']}
    js('window.bridge.finishFeedbackClear(window.feedbackRecord,'+json.dumps(clear)+')')
    changed=[{**t,'device_address':'M999'} if t['tag_name']==FILTER['command_tag'] else t for t in TAGS]
    js('window.bridge.updateChecklist('+json.dumps(changed)+',null,null)')
    state['values'][FILTER['command_tag']]=0
    time.sleep(.7)
    assert stored(js)[-1]['zeroAcceptedAt'] and not stored(js)[-1].get('zeroSeenAt')
    assert not state['writes']


@pytest.mark.parametrize('reply,error',[
    ({'result':'BLOCKED','write_dispatched':True,'error':'Post-dispatch failure'},None),
    ({'result':'BLOCKED','error':'Old backend supplied no dispatch evidence'},None),
    (None,{'message':'Unclassified HTTP rejection','status':400}),
    (None,{'message':'Unclassified HTTP rejection','status':403}),
])
def test_unproven_blocked_outcome_remains_pending_even_when_command_is_one(browser,reply,error):
    state, _, _, js, wait_for=browser
    begin(browser,mode='hold')
    state['values'][FILTER['command_tag']]=1
    js('window.bridge.finishFeedbackTest(window.feedbackRecord,'+json.dumps(reply)+','+json.dumps(error)+')')
    record=stored(js)[-1]
    assert record['oneRequestedAt'] and not record.get('oneRejectedAt')
    assert record['feedbackState']=='OUTCOME UNKNOWN' and not record.get('holdOneAt')
    assert not js('return window.bridge.canStartFeedbackTest('+json.dumps(HEATER)+')')
    assert js('return Boolean(window.bridge.beginFeedbackClear(window.feedbackRecord))')
    js("window.bridge.finishFeedbackClear(window.feedbackRecord,null,{message:'No clear sent',writeDispatched:false})")
    assert not state['writes']
