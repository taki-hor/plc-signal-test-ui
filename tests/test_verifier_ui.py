"""Feedback test UI checks use the loopback fake API, never the supplier API."""
import json
import time
from datetime import datetime, timedelta

import pytest

from test_frontend_safety import ROOT, browser, harness, pytestmark


def intercept_test(browser, result=None, http_status=200, hold=False):
    _, _, _, js, _ = browser
    response = result or {'result':'PASS','test_name':'Tank01 Door Open','command':'Tank01_DoorOpenRemote=1',
                          'expected_feedback':'Tank01_DoorOpened=1','actual_feedback':1,'elapsed_ms':5828,'http_status':200}
    tags={tag['tag_name']:tag for tag in json.loads((ROOT/'config/mock-tags.json').read_text())['tags']}
    commands={case['id']:{'tag_name':case['command_tag'],'address':tags[case['command_tag']]['device_address']}
              for case in json.loads((ROOT/'config/test-cases.json').read_text())['tests']}
    js("window.originalTestFetch=window.fetch;window.testRequests=[];window.releaseTest=null;window.testReply="+json.dumps(response)+";window.mockTestCommands="+json.dumps(commands)+";window.testHttpStatus="+str(http_status)+";window.testHold="+json.dumps(hold)+";"+"""
      window.fetch=async function(url,options){
        if(url!=='/api/test/run')return window.originalTestFetch(url,options);
        const body=JSON.parse(options.body);window.testRequests.push(body);
        const command=window.mockTestCommands[body.id];
        const snapshot=await(await window.originalTestFetch('/api/status')).json();
        const payload={mapping_under_test:body.mapping_under_test===true,end_mode:body.end_mode??'manual0',command_address:command.address,...window.testReply};
        if(!Object.hasOwn(payload,'write_response')&&['PASS','OBSERVED','TIMEOUT'].includes(payload.result))payload.write_response={written:true,tag_name:command.tag_name,value:1,console_accepted_at:new Date().toISOString(),console_command_baseline_utc:snapshot.supplier_timestamp_utc};
        const reply=()=>new Response(JSON.stringify(payload),{status:window.testHttpStatus,headers:{'Content-Type':'application/json'}});
        return window.testHold?new Promise(resolve=>{window.releaseTest=()=>resolve(reply())}):reply();
      }
    """)


def start_test(browser, case_id='tank01-door-open', accept=True, mode='manual0'):
    _, _, _, js, wait_for = browser
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')")
    js("document.querySelector('[data-test-id="+case_id+"] button').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    if mode=='hold': js("document.getElementById('test-mode-hold').click()")
    if accept: js("document.getElementById('confirm-yes').click()")
    else: js("document.getElementById('confirm-dialog').close('cancel')")


@pytest.mark.parametrize('action,elapsed',[('open',5828),('close',7918)])
def test_completed_result_is_above_cases_visible_and_focused(browser,action,elapsed):
    state, wd, prefix, js, wait_for = browser
    wd(prefix+'/window/rect',{'width':1440,'height':1000})
    response={'result':'PASS','test_name':'Tank01 Door '+action.title(),'command':'Tank01_Door'+action.title()+'Remote=1',
              'expected_feedback':'Tank01_Door'+('Opened' if action=='open' else 'Closed')+'=1',
              'actual_feedback':1,'elapsed_ms':elapsed,'http_status':200}
    intercept_test(browser,response)
    start_test(browser,'tank01-door-'+action)
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('PASS')")
    assert js("return document.querySelectorAll('#test-list .test-card').length") == 50
    assert js("return Boolean(document.getElementById('test-result').compareDocumentPosition(document.getElementById('test-list')) & Node.DOCUMENT_POSITION_FOLLOWING)")
    assert js("const r=document.getElementById('test-result').getBoundingClientRect();return r.top>=0&&r.top<innerHeight&&r.bottom>0")
    assert js("return document.activeElement.id") == 'test-result'
    assert str(elapsed)+' ms' in js("return document.querySelector('.test-backend-result').textContent")
    assert js('return window.testRequests') == [{'id':'tank01-door-'+action,'end_mode':'manual0'}]
    assert not state['writes']


def test_live_feedback_and_freshness_update_while_waiting_without_awarding_pass(browser):
    state, _, _, js, wait_for = browser
    intercept_test(browser,hold=True)
    start_test(browser)
    wait_for("return typeof window.releaseTest==='function'")
    wait_for("return document.getElementById('test-live-feedback').textContent==='Tank01_DoorOpened = 0'")
    assert 'RUNNING' in js("return document.getElementById('test-result-state').textContent")
    initial_source=js("return document.getElementById('test-live-source').textContent")
    js("window.phaseMutations=0;new MutationObserver(m=>window.phaseMutations+=m.length).observe(document.getElementById('test-result-state'),{childList:true,subtree:true,characterData:true});document.querySelector('#test-result .test-technical').open=true")
    state['values'].update(Tank01_DoorOpenRemote=1,Tank01_DoorOpened=1)
    wait_for("return document.getElementById('test-live-feedback').textContent==='Tank01_DoorOpened = 1'")
    assert js("return document.getElementById('test-result-state').textContent.startsWith('RUNNING')")
    assert js("return document.getElementById('test-backend-result').classList.contains('hidden')")
    assert js("return document.getElementById('test-live-source').textContent") != initial_source
    assert js("return document.getElementById('test-live-health').textContent") == 'LIVE · FRESH'
    assert js('return window.phaseMutations') == 0
    assert js("return document.querySelector('#test-result .test-technical').open")
    state['fault']='signals_503'
    wait_for("return document.getElementById('test-live-health').textContent==='STALE / NO DATA'")
    state['fault']=None
    wait_for("return document.getElementById('test-live-health').textContent==='LIVE · FRESH'")
    js('window.releaseTest()')
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('PASS')")
    assert js('return window.testRequests') == [{'id':'tank01-door-open','end_mode':'manual0'}]
    assert not state['writes']


def test_completion_does_not_navigate_or_move_focus_from_another_page(browser):
    state, _, _, js, wait_for = browser
    intercept_test(browser,hold=True)
    start_test(browser)
    wait_for("return typeof window.releaseTest==='function'")
    js("document.querySelector('[data-nav=signals]').click()")
    wait_for("return document.querySelector('[data-nav=signals]').getAttribute('aria-current')==='page'")
    js("document.getElementById('signal-search').focus();window.releaseTest()")
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('PASS')")
    assert js('return location.hash') == '#/signals'
    assert js('return document.activeElement.id') == 'signal-search'
    assert js("return document.getElementById('verify').classList.contains('hidden')")
    assert js('return window.testRequests') == [{'id':'tank01-door-open','end_mode':'manual0'}]
    assert not state['writes']


@pytest.mark.parametrize('kind',['blocked','communication'])
def test_blocked_and_communication_outcomes_are_visible_without_extra_commands(browser,kind):
    state, _, _, js, wait_for = browser
    if kind=='blocked':
        intercept_test(browser,{'result':'BLOCKED','test_name':'Tank01 Door Open','command':'Tank01_DoorOpenRemote=1',
                               'expected_feedback':'Tank01_DoorOpened=1','actual_feedback':0,'elapsed_ms':12,
                               'http_status':None,'error':'Feedback already has expected value','write_dispatched':False})
    else:
        intercept_test(browser,{'error':'Injected supplier communication failure'},http_status=503)
    start_test(browser)
    expected='BLOCKED' if kind=='blocked' else 'COMMUNICATION ERROR'
    wait_for("return document.getElementById('test-result-state').textContent.startsWith("+json.dumps(expected)+")")
    assert ('Feedback already has expected value' if kind=='blocked' else 'Injected supplier communication failure') in js("return document.getElementById('test-result').textContent")
    assert js('return window.testRequests') == [{'id':'tank01-door-open','end_mode':'manual0'}]
    assert not state['writes']


def test_cancelled_confirmation_does_not_start_a_test(browser):
    state, _, _, js, wait_for = browser
    intercept_test(browser)
    start_test(browser,accept=False)
    time.sleep(.3)
    assert js('return window.testRequests') == []
    assert js("return document.getElementById('test-result-state').textContent") == 'Choose a configured test below. Its progress and result appear here.'
    assert not state['writes']


@pytest.mark.parametrize('action',['open','close'])
def test_tank01_manual_zero_clears_same_tag_after_one_confirmation_on_feedback_page(browser,action):
    state, _, _, js, wait_for = browser
    tag=ready_to_clear(browser,action)
    before=js("return document.getElementById('test-backend-result').textContent")
    assert tag in js("return document.getElementById('test-reset-rule').textContent")
    js("document.getElementById('test-send-zero').click()")
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    confirmation=js("return document.getElementById('confirm-body').textContent")
    assert tag in confirmation and 'Confirm physical movement has finished' in confirmation
    assert 'No opposite door command' in confirmation
    assert not state['writes']
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert js('return location.hash') == '#/verify'
    assert js("return document.getElementById('test-backend-result').textContent") == before
    assert state['writes'] == [{'tag_name':tag,'value':0}]
    assert js('return window.testRequests') == [{'id':'tank01-door-'+action,'end_mode':'manual0'}]
    audit=js("return JSON.parse(localStorage.getItem('plc-value-feedback:v1:MOCK:BROWSER TEST'))[0]")
    assert audit['writes']==[{'tag_name':tag,'value':0}]
    assert audit['source']=='Feedback tests manual Send 0' and audit['accepted_at']


def test_other_tanks_do_not_inherit_tank01_reset_guidance(browser):
    state, _, _, js, wait_for = browser
    intercept_test(browser)
    start_test(browser,'tank03-door-open')
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('PASS')")
    assert 'hold/reset procedure is unconfirmed' in js("return document.getElementById('test-reset-rule').textContent")
    assert 'your explicitly chosen test plan' in js("return document.getElementById('test-reset-rule').textContent")
    assert not js("return document.getElementById('test-send-zero').classList.contains('hidden')")
    assert not state['writes']


def test_prepare_write_is_form_only_and_rejects_invalid_targets(browser):
    state, _, _, js, wait_for = browser
    js("document.getElementById('mode-btn').click()")
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    # Import in the page realm so Firefox shares the application's module state.
    script = "import {prepareWrite} from '/js/controls.js';const before=[document.getElementById('write-tag').value,document.getElementById('write-value').value];const rejected=[prepareWrite('Tank01_DoorOpened',0),prepareWrite('Tank01_DoorOpenRemote',2),prepareWrite('MissingTag',0)];const unchanged=JSON.stringify(before)===JSON.stringify([document.getElementById('write-tag').value,document.getElementById('write-value').value]);const prepared=prepareWrite('Tank01_DoorOpenRemote',0);window.prefillChecks={rejected,unchanged,prepared};"
    js("window.prefillChecks=null;const script=document.createElement('script');script.type='module';script.textContent="+json.dumps(script)+";document.body.appendChild(script)")
    wait_for('return window.prefillChecks!==null')
    assert js('return window.prefillChecks') == {'rejected':[False,False,False],'unchanged':True,'prepared':True}
    assert js('return location.hash') == '#/write'
    assert js("return document.getElementById('write-value').value") == '0'
    assert js("return document.getElementById('write-banner-title').textContent") == 'READ-ONLY MODE'
    assert not js("return document.getElementById('confirm-dialog').open")
    assert not state['writes']


def test_candidate_non_door_cases_explain_their_under_test_status_before_confirmation(browser):
    state, _, _, js, wait_for = browser
    intercept_test(browser)
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return document.querySelectorAll('#test-list button[data-needs-confirmation=true]').length===36")
    assert js("return [...document.querySelectorAll('#test-list button[data-needs-confirmation=true]')].every(button=>!button.disabled&&document.getElementById(button.getAttribute('aria-describedby')).textContent.includes('Mapping under test'))")
    js("document.querySelector('#test-list button[data-needs-confirmation=true]').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    js("document.getElementById('confirm-dialog').close('cancel')")
    assert js('return window.testRequests') == []
    assert not state['writes']


@pytest.mark.parametrize('action',['open','close'])
@pytest.mark.parametrize('catalog_change',['address','missing'])
def test_tank01_reset_confirmation_requires_current_catalog_identity(browser,action,catalog_change):
    state, _, _, js, wait_for = browser
    tag='Tank01_Door'+action.title()+'Remote'
    intercept_test(browser)
    start_test(browser,'tank01-door-'+action)
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('PASS')")
    assert not js("return document.getElementById('test-send-zero').classList.contains('hidden')")
    # Change the actual catalogue response, then use the application's normal reload path.
    change=("data.tags=data.tags.map(t=>t.tag_name==="+json.dumps(tag)+"?{...t,device_address:'M999'}:t);" if catalog_change=='address'
            else "data.tags=data.tags.filter(t=>t.tag_name!=="+json.dumps(tag)+");")
    js("window.catalogFetch=window.fetch;window.catalogChanged=false;window.fetch=async function(url,options){const response=await window.catalogFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();"+change+"window.catalogChanged=true;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
    wait_for('return window.catalogChanged')
    wait_for("return document.getElementById('test-send-zero').classList.contains('hidden')")
    assert 'hold/reset procedure is unconfirmed' in js("return document.getElementById('test-reset-rule').textContent")
    assert js("return document.getElementById('test-result-state').textContent.startsWith('PASS')")
    assert js("return location.hash") == '#/verify'
    assert js('return window.testRequests') == [{'id':'tank01-door-'+action,'end_mode':'manual0'}]
    assert not state['writes']


def ready_to_clear(browser,action='open'):
    state, _, _, js, wait_for=browser
    tag='Tank01_Door'+action.title()+'Remote'
    intercept_test(browser)
    start_test(browser,'tank01-door-'+action)
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('PASS')")
    state['values'][tag]=1
    wait_for("return document.getElementById('test-command-readback').textContent==='1'&&!document.getElementById('test-send-zero').disabled")
    return tag


def test_manual_zero_cancel_sends_nothing_and_preserves_pass(browser):
    state, _, _, js, wait_for=browser
    ready_to_clear(browser)
    before=js("return document.getElementById('test-backend-result').textContent")
    js("document.getElementById('test-send-zero').click();document.getElementById('confirm-dialog').close('cancel')")
    time.sleep(.3)
    assert not state['writes']
    assert js("return document.getElementById('test-backend-result').textContent") == before
    assert js("return document.getElementById('test-clear-state').classList.contains('hidden')")


@pytest.mark.parametrize('guard',['mode_off','stale','local','mismatched_poll','api_context','address'])
def test_manual_zero_rechecks_guards_and_captured_identity_at_confirmation(browser,guard):
    state, _, _, js, wait_for=browser
    ready_to_clear(browser)
    js("document.getElementById('test-send-zero').click()")
    if guard=='mode_off':
        state['mode']=False
        wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    elif guard=='stale':
        state['fault']='signals_503'
        wait_for("return document.getElementById('test-live-health').textContent==='STALE / NO DATA'")
    elif guard=='address':
        js("window.driftFetch=window.fetch;window.fetch=async function(url,options){const response=await window.driftFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();data.tags=data.tags.map(tag=>tag.tag_name==='Tank01_DoorOpenRemote'?{...tag,device_address:'M999'}:tag);return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
        wait_for("return document.getElementById('test-send-zero').classList.contains('hidden')")
    else:
        field,value={'local':('plc_mode','LOCAL'),'mismatched_poll':('supplier_timestamp','different snapshot'),'api_context':('api_address','OTHER TEST API')}[guard]
        js("window.driftFetch=window.fetch;window.driftSeen=false;window.fetch=async function(url,options){const response=await window.driftFetch(url,options);if(url!=='/api/status')return response;const data=await response.json();data["+json.dumps(field)+"]="+json.dumps(value)+";window.driftSeen=true;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
        wait_for('return window.driftSeen')
        wait_for("return document.getElementById('api-address').textContent==='OTHER TEST API'" if guard=='api_context' else "return document.getElementById('test-send-zero').disabled")
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='CLEAR BLOCKED BEFORE DISPATCH'")
    assert not state['writes']
    assert js('return window.testRequests') == [{'id':'tank01-door-open','end_mode':'manual0'}]
    assert js("return document.getElementById('test-result-state').textContent.startsWith('PASS')")


@pytest.mark.parametrize('missing_baseline',[False,True])
def test_manual_zero_requires_newer_supplier_readback_than_final_baseline(browser,missing_baseline):
    state, _, _, js, wait_for=browser
    ready_to_clear(browser)
    state['validation_advance']=True;state['omit_baseline']=missing_baseline
    js("document.getElementById('test-send-zero').click();document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent.startsWith('API ACCEPTED 0')")
    stamp=state['freeze_stamp']
    wait_for("return document.getElementById('test-command-readback').textContent==='0'")
    time.sleep(.4)
    assert js("return document.getElementById('test-clear-state').textContent") != 'VERIFIED 0'
    state['freeze_stamp']=(datetime.fromisoformat(stamp)+timedelta(milliseconds=1)).isoformat()
    if missing_baseline:
        time.sleep(.4)
        assert js("return document.getElementById('test-clear-state').textContent") == 'API ACCEPTED 0 — READBACK UNVERIFIABLE'
    else:
        wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes']==[{'tag_name':'Tank01_DoorOpenRemote','value':0}]


@pytest.mark.parametrize('fault,expected',[('before_dispatch','CLEAR BLOCKED BEFORE DISPATCH'),('unknown','CLEAR OUTCOME UNKNOWN')])
def test_manual_zero_write_failure_is_separate_from_backend_pass_without_retry(browser,fault,expected):
    state, _, _, js, wait_for=browser
    ready_to_clear(browser)
    before=js("return document.getElementById('test-backend-result').textContent")
    state['write_fault']=fault
    js("document.getElementById('test-send-zero').click();document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==="+json.dumps(expected))
    time.sleep(.4)
    assert js("return document.getElementById('test-backend-result').textContent") == before
    assert 'Review the equipment and command state' in js("return document.getElementById('test-clear-detail').textContent")
    assert not state['writes']


def test_manual_zero_inflight_blocks_double_send_and_other_feedback_tests(browser):
    state, _, _, js, wait_for=browser
    ready_to_clear(browser)
    state['clear_hold']=True
    js("document.getElementById('test-send-zero').click();document.getElementById('confirm-yes').click()")
    assert state['clear_entered'].wait(2)
    wait_for("return document.getElementById('test-clear-state').textContent==='SENDING 0'")
    assert js("return document.getElementById('test-send-zero').disabled&&[...document.querySelectorAll('#test-list button')].every(button=>button.disabled)")
    js("document.getElementById('test-send-zero').click();document.querySelector('[data-test-id=tank01-door-close] button').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert js('return window.testRequests') == [{'id':'tank01-door-open','end_mode':'manual0'}]
    state['clear_release'].set()
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes']==[{'tag_name':'Tank01_DoorOpenRemote','value':0}]


def test_manual_zero_is_unavailable_when_api_context_changed_before_opening_confirmation(browser):
    state, _, _, js, wait_for=browser
    ready_to_clear(browser)
    js("window.contextFetch=window.fetch;window.fetch=async function(url,options){const response=await window.contextFetch(url,options);if(url!=='/api/status')return response;const data=await response.json();data.api_address='OTHER TEST API';return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
    wait_for("return document.getElementById('api-address').textContent==='OTHER TEST API'")
    assert js("return document.getElementById('test-send-zero').disabled")
    js("document.getElementById('test-send-zero').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert not state['writes']


def test_accepted_manual_zero_cannot_be_repeated_while_waiting_for_later_zero(browser):
    state, _, _, js, wait_for=browser
    ready_to_clear(browser)
    js("window.delayedClearFetch=window.fetch;window.delayZeroReadback=true;window.fetch=async function(url,options){const response=await window.delayedClearFetch(url,options);if(url!=='/api/signals'||!window.delayZeroReadback)return response;const data=await response.json();data.Tank01_DoorOpenRemote=1;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
    js("document.getElementById('test-send-zero').click();document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='API ACCEPTED 0 — WAITING FOR READBACK'")
    assert js("return document.getElementById('test-send-zero').disabled")
    js("document.getElementById('test-send-zero').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert state['writes']==[{'tag_name':'Tank01_DoorOpenRemote','value':0}]
    js('window.delayZeroReadback=false')
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes']==[{'tag_name':'Tank01_DoorOpenRemote','value':0}]
