"""Feedback tank filtering uses a native select and an isolated fake API."""
import json
import re

from test_frontend_safety import ROOT, browser, harness, pytestmark
from test_verifier_ui import intercept_test, start_test

CASES=json.loads((ROOT/'config/test-cases.json').read_text())['tests']
GROUPS=sorted({'Tank'+re.match(r'Tank(\d{2})',case['command_tag'])[1] for case in CASES})


def show_feedback(browser):
    _,_,_,js,wait_for=browser
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')&&document.getElementById('test-tank-select').options.length>1")


def visible_ids(js):
    return js("return [...document.querySelectorAll('#test-list [data-test-id]:not(.hidden)')].map(card=>card.dataset.testId)")


def select_tank(js,tank):
    js("const select=document.getElementById('test-tank-select');select.focus({preventScroll:true});select.value="+json.dumps(tank)+";select.dispatchEvent(new Event('change'))")


def test_feedback_tank_select_filters_every_case_without_dispatch(browser):
    state,_,_,js,_=browser
    intercept_test(browser);show_feedback(browser)
    assert js("return [...document.getElementById('test-tank-select').options].map(option=>option.value)")==['all',*GROUPS]
    assert js("return document.getElementById('test-tank-select').tagName")=='SELECT'
    assert js("return document.getElementById('test-tank-tabs')") is None
    assert visible_ids(js)==[case['id'] for case in CASES]
    for tank in GROUPS:
        select_tank(js,tank)
        expected=[case['id'] for case in CASES if case['command_tag'].startswith(tank+'_')]
        assert visible_ids(js)==expected
        assert js("return document.querySelectorAll('#test-list [data-test-id]').length")==len(CASES)
        assert f'{len(expected)} of {len(CASES)} pairs' in js("return document.getElementById('test-tank-count').textContent")
    select_tank(js,'all')
    assert visible_ids(js)==[case['id'] for case in CASES]
    assert js("return document.getElementById('test-list').getAttribute('role')")=='region'
    assert not state['writes'] and js('return window.testRequests')==[]
    assert not js("return document.getElementById('confirm-dialog').open")


def test_feedback_tank_select_keeps_focus_selection_and_narrow_layout_on_refresh(browser):
    state,wd,prefix,js,wait_for=browser
    intercept_test(browser);show_feedback(browser);select_tank(js,GROUPS[0])
    js("window.focusedFeedbackTank=document.activeElement;window.originalFeedbackCard=document.querySelector('#test-list [data-test-id]')")
    state['values']['Tank01_TempPV']=17
    wait_for("return document.querySelector('#signal-list [data-signal-tag=Tank01_TempPV] .value')?.textContent==='17'")
    assert js('return document.activeElement===window.focusedFeedbackTank')
    js("document.getElementById('refresh-btn').click()")
    wait_for('return !window.originalFeedbackCard.isConnected')
    assert js('return document.activeElement===window.focusedFeedbackTank&&window.focusedFeedbackTank.isConnected')
    assert js("return document.getElementById('test-tank-select').value")==GROUPS[0]
    wd(prefix+'/window/rect',{'width':500,'height':900})
    js("document.getElementById('test-tank-select').scrollIntoView({block:'center'})")
    assert js("const rect=document.getElementById('test-tank-select').getBoundingClientRect();return rect.left>=0&&rect.right<=innerWidth")
    assert js('return document.documentElement.scrollWidth<=innerWidth+1')
    assert not state['writes'] and js('return window.testRequests')==[]


def test_tank_filter_keeps_other_tanks_run_and_shared_clear_available(browser):
    state,_,_,js,wait_for=browser
    intercept_test(browser);start_test(browser,'tank01-door-open')
    wait_for("return document.getElementById('test-result-state').textContent.startsWith('PASS')")
    state['values'].update(Tank01_DoorOpenRemote=1,Tank01_DoorOpened=1)
    wait_for("return Boolean(document.querySelector('[data-clear-tag=Tank01_DoorOpenRemote]'))")
    before=js("return document.getElementById('test-backend-result').textContent")
    select_tank(js,'Tank02')
    assert visible_ids(js)==[case['id'] for case in CASES if case['command_tag'].startswith('Tank02_')]
    assert js("return document.getElementById('test-result').getClientRects().length>0")
    assert js("return document.getElementById('test-backend-result').textContent")==before
    assert js("return document.getElementById('test-operator-state').textContent")=='AWAITING YOUR CHECK'
    assert js("return document.getElementById('shared-write-signals').contains(document.querySelector('[data-clear-tag=Tank01_DoorOpenRemote]'))")
    assert not js("return document.querySelector('[data-clear-command=Tank01_DoorOpenRemote]').disabled")
    select_tank(js,'all')
    assert len(visible_ids(js))==len(CASES)
    assert len(js('return window.testRequests'))==1 and not state['writes']


def test_feedback_tank_select_tracks_case_groups_and_falls_back_after_removal(browser):
    state,_,_,js,wait_for=browser
    intercept_test(browser);show_feedback(browser);select_tank(js,'Tank01')
    js("window.feedbackGroupFetch=window.fetch;window.removeFeedbackTankOne=false;window.fetch=async function(url,options){const response=await window.feedbackGroupFetch(url,options);if(url!=='/api/test/cases')return response;const data=await response.json();data.tests.push({...data.tests[0],id:'extra-tank17-case',name:'Tank 17 test',command_tag:'Tank17_DoorOpenRemote'});if(window.removeFeedbackTankOne)data.tests=data.tests.filter(test=>!test.command_tag.startsWith('Tank01_'));return new Response(JSON.stringify(data),{status:response.status,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
    wait_for("return [...document.getElementById('test-tank-select').options].some(option=>option.value==='Tank17')")
    assert js("return document.activeElement.id")=='test-tank-select'
    assert js("return document.getElementById('test-tank-select').value")=='Tank01'
    select_tank(js,'Tank17')
    assert visible_ids(js)==['extra-tank17-case']
    assert js("return document.querySelector('[data-test-id=extra-tank17-case] button[data-run-test]').disabled")
    select_tank(js,'Tank01')
    js("window.removeFeedbackTankOne=true;document.getElementById('refresh-btn').click()")
    wait_for("return ![...document.getElementById('test-tank-select').options].some(option=>option.value==='Tank01')")
    assert js("return document.getElementById('test-tank-select').value")=='all'
    assert js("return document.activeElement.id")=='test-tank-select'
    assert visible_ids(js)==[case['id'] for case in CASES if not case['command_tag'].startswith('Tank01_')]+['extra-tank17-case']
    assert not state['writes'] and js('return window.testRequests')==[]
