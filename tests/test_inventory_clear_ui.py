"""Inventory clear tests send commands only to the isolated loopback fake API."""
import json
import time
from datetime import datetime, timedelta

import pytest

from test_frontend_safety import browser, harness, pytestmark, choose_command, checklist_write
from test_verifier_ui import intercept_test, start_test
from test_candidate_feedback_ui import candidate_reply

KEY='plc-command-checklist:v1:MOCK:BROWSER TEST'
TAG='Tank03_FillWaterOn'


def button(name=TAG):
    return "document.querySelector('[data-clear-command="+name+"]')"


def records(browser):
    return browser[3]('return JSON.parse(localStorage.getItem('+json.dumps(KEY)+')||"[]")')


def show_inventory(browser,name=TAG,value=1):
    state, _, _, js, wait_for=browser
    if value is not None: state['values'][name]=value
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')")
    wait_for('return Boolean('+button(name)+')&&!'+button(name)+'.disabled')


def confirm_row_zero(browser,name=TAG):
    js=browser[3]
    js(button(name)+'.click()')
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    assert name in js("return document.getElementById('confirm-body').textContent")
    js("document.getElementById('confirm-yes').click()")


@pytest.mark.parametrize('name',[TAG,'Tank05_DoorOpenRemote'])
def test_unknown_origin_clear_is_one_explicit_zero_and_preserves_the_existing_draft(browser,name):
    state, _, _, js, wait_for=browser
    intercept_test(browser)
    choose_command(browser,name)
    js("document.getElementById('bool-notes').value='Keep this earlier draft';document.getElementById('bool-notes').dispatchEvent(new Event('input'))")
    draft=records(browser)[-1]
    show_inventory(browser,name)
    before=js("return document.getElementById('test-result-state').textContent")
    js(button(name)+'.click()')
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    js("document.getElementById('confirm-dialog').close('cancel')")
    time.sleep(.1)
    assert not state['writes'] and len(records(browser))==1
    confirm_row_zero(browser,name)
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes']==[{'tag_name':name,'value':0}]
    assert js('return window.testRequests')==[]
    assert js('return location.hash')=='#/verify'
    assert js("return document.getElementById('test-result-state').textContent")==before
    assert js("return document.getElementById('test-last-clear').getClientRects().length>0")
    assert name in js("return document.getElementById('test-clear-target').textContent")
    saved=records(browser)
    assert saved[0]['id']==draft['id'] and saved[0]['note']=='Keep this earlier draft'
    cleanup=saved[-1]
    assert cleanup['source']=='Manual cleanup' and cleanup['zeroOnlyCleanup'] is True and cleanup['note']==''
    assert not cleanup.get('oneRequestedAt') and not cleanup.get('oneAcceptedAt')
    assert cleanup['zeroAcceptedAt'] and cleanup['zeroSeenAt']


def test_clearing_another_inventory_tag_does_not_replace_the_current_pass_or_time(browser):
    state, _, _, js, wait_for=browser
    intercept_test(browser)
    start_test(browser)
    wait_for("return document.getElementById('test-result-state').dataset.state==='PASS'")
    result=js("return document.getElementById('test-backend-result').textContent")
    active=js("return document.getElementById('test-active-command').textContent")
    show_inventory(browser)
    confirm_row_zero(browser)
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert js("return document.getElementById('test-backend-result').textContent")==result
    assert js("return document.getElementById('test-active-command').textContent")==active
    assert js("return document.getElementById('test-result-state').dataset.state")=='PASS'
    assert state['writes']==[{'tag_name':TAG,'value':0}]
    assert js('return window.testRequests')==[{'id':'tank01-door-open','end_mode':'manual0'}]
    saved=records(browser)
    assert saved[0]['tag_name']=='Tank01_DoorOpenRemote' and not saved[0].get('zeroSeenAt')
    assert saved[-1]['tag_name']==TAG and saved[-1]['zeroSeenAt']


@pytest.mark.parametrize('origin',['commands','feedback'])
def test_pending_zero_after_reload_can_be_cleared_from_its_row_without_an_active_test(browser,origin):
    state, wd, prefix, js, wait_for=browser
    name='Tank01_FilterRemote'
    if origin=='commands':
        choose_command(browser,name)
        checklist_write(browser,1)
    else:
        candidate_reply(browser)
        start_test(browser,'tank01-filterremote')
        wait_for("return document.getElementById('test-result-state').dataset.state==='OBSERVED'")
        state['values'][name]=1
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote]').textContent.includes('Value 1')")
    previous=records(browser)[-1]
    state['values'][name]=0
    wait_for("return document.querySelector('[data-command-tag=Tank01_FilterRemote]').textContent.includes('Value 0')")
    before=list(state['writes'])
    show_inventory(browser,name,value=None)
    wd(prefix+'/refresh',{})
    wait_for('return Boolean('+button(name)+')')
    assert js('return '+button(name)+'.disabled')
    assert state['writes']==before
    js("document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for('return !'+button(name)+'.disabled')
    initial=js("return document.getElementById('test-result-state').textContent")
    confirm_row_zero(browser,name)
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes']==before+[{'tag_name':name,'value':0}]
    assert js("return document.getElementById('test-result-state').textContent")==initial
    assert js("return document.getElementById('test-last-clear').getClientRects().length>0")
    assert records(browser)[-1]['id']==previous['id'] and records(browser)[-1]['zeroSeenAt']
    assert js("return performance.getEntriesByType('resource').filter(entry=>new URL(entry.name).pathname==='/api/test/run').length")==0


@pytest.mark.parametrize('guard',['readonly','stale','address','api_context'])
def test_inventory_confirmation_rechecks_guards_and_the_captured_pending_identity(browser,guard):
    state, _, _, js, wait_for=browser
    choose_command(browser,TAG)
    checklist_write(browser,1)
    state['values'][TAG]=0
    show_inventory(browser,value=None)
    wait_for("return document.querySelector('[data-clear-tag="+TAG+"] .test-status').textContent==='Pending 0'")
    before=list(state['writes'])
    js(button()+'.click()')
    assert js("return document.getElementById('confirm-dialog').open")
    if guard=='readonly':
        state['mode']=False
        wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
        assert js('return '+button()+'.disabled')
    elif guard=='stale':
        state['fault']='signals_503'
        wait_for("return document.getElementById('api-state').textContent==='DISCONNECTED'")
        assert js('return '+button()+'.disabled')
    elif guard=='address':
        js("window.inventoryDriftFetch=window.fetch;window.fetch=async function(url,options){const response=await window.inventoryDriftFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();data.tags=data.tags.map(tag=>tag.tag_name==='Tank03_FillWaterOn'?{...tag,device_address:'M999'}:tag);return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
        wait_for("return document.getElementById('bool-address').textContent==='M999'")
        wait_for('return '+button()+'.disabled')
    else:
        js("window.inventoryDriftFetch=window.fetch;window.fetch=async function(url,options){const response=await window.inventoryDriftFetch(url,options);if(url!=='/api/status')return response;const data=await response.json();data.api_address='OTHER INVENTORY API';return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
        wait_for("return document.getElementById('api-address').textContent==='OTHER INVENTORY API'")
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='CLEAR BLOCKED BEFORE DISPATCH'")
    assert state['writes']==before


def test_inventory_keyboard_focus_and_latest_readback_are_preserved_during_polling(browser):
    state, _, _, js, wait_for=browser
    show_inventory(browser)
    js('window.inventoryFocused='+button()+';window.inventoryFocused.focus()')
    state['values']['Tank05_DoorOpenRemote']=1
    wait_for('return Boolean('+button('Tank05_DoorOpenRemote')+')')
    assert js('return document.activeElement===window.inventoryFocused&&window.inventoryFocused.isConnected')
    state['validation_advance']=True
    confirm_row_zero(browser)
    wait_for("return document.getElementById('test-clear-state').textContent==='API ACCEPTED 0 — WAITING FOR READBACK'")
    pending=records(browser)[-1]
    assert pending['zeroOnlyCleanup'] and pending['zeroAcceptedAt'] and not pending.get('zeroSeenAt')
    choose_command(browser,TAG)
    assert js("return document.getElementById('bool-one').disabled")
    assert js('return '+button()+'.disabled')
    stamp=state['freeze_stamp']
    time.sleep(.3)
    assert not records(browser)[-1].get('zeroSeenAt')
    state['freeze_stamp']=(datetime.fromisoformat(stamp)+timedelta(milliseconds=1)).isoformat()
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert records(browser)[-1]['zeroSeenAt'] and not records(browser)[-1].get('oneRequestedAt')
    assert state['writes']==[{'tag_name':TAG,'value':0}]
    js("document.querySelector('[data-nav=commands]').click()")
    choose_command(browser,TAG)
    js("document.getElementById('bool-new').click()")
    checklist_write(browser,1)
    saved=records(browser)
    assert saved[-2]['id']==pending['id'] and saved[-2]['zeroOnlyCleanup'] and not saved[-2].get('oneRequestedAt')
    assert saved[-1]['id']!=pending['id'] and not saved[-1].get('zeroOnlyCleanup') and saved[-1]['oneAcceptedAt']
    assert saved[-1].get('source')!='Manual cleanup'
    assert state['writes']==[{'tag_name':TAG,'value':0},{'tag_name':TAG,'value':1}]


def test_unknown_commands_retry_does_not_reuse_the_inventorys_older_zero_receipt(browser):
    state, _, _, js, wait_for=browser
    show_inventory(browser)
    state['validation_advance']=True
    confirm_row_zero(browser)
    wait_for("return document.getElementById('test-clear-state').textContent==='API ACCEPTED 0 — WAITING FOR READBACK'")
    accepted=records(browser)[-1]
    assert accepted['zeroAcceptedAt'] and not accepted.get('zeroSeenAt')
    js("document.querySelector('[data-nav=commands]').click()")
    choose_command(browser,TAG)
    state['write_fault']='unknown'
    js("document.getElementById('bool-zero').click();document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='CLEAR MONITORING INTERRUPTED'")
    latest=records(browser)[-1]
    assert latest['id']==accepted['id'] and latest['zeroRequestedAt']>accepted['zeroRequestedAt']
    assert not latest.get('zeroAcceptedAt') and not latest.get('zeroServerAt') and not latest.get('zeroCommandBaselineUtc')
    state['validation_advance']=False
    state['freeze_stamp']=None
    time.sleep(.5)
    assert not records(browser)[-1].get('zeroSeenAt')
    assert js("return document.getElementById('test-clear-state').textContent")=='CLEAR MONITORING INTERRUPTED'
    assert state['writes']==[{'tag_name':TAG,'value':0}]
