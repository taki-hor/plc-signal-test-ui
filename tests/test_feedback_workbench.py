"""Feedback workbench checks use only the isolated loopback fake API."""
import json
import time

import pytest

from test_frontend_safety import ROOT, browser, harness, pytestmark, choose_command, checklist_write
from test_verifier_ui import intercept_test, start_test

CASES=json.loads((ROOT/'config/test-cases.json').read_text())['tests']
TAGS={tag['tag_name']:tag for tag in json.loads((ROOT/'config/mock-tags.json').read_text())['tags']}
KEY='plc-command-checklist:v1:MOCK:BROWSER TEST'


def select_pair(browser,case):
    _,_,_,js,wait_for=browser
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')")
    js("document.querySelector('[data-select-test="+case+"]').click()")


def visible_pairs(browser):
    return browser[3]("return [...document.querySelectorAll('#test-list [data-test-id]:not(.hidden)')].map(card=>card.dataset.testId)")


def set_filter(browser,value):
    browser[3]("const select=document.getElementById('test-result-filter');select.value="+json.dumps(value)+";select.dispatchEvent(new Event('change'))")


def history_record(case_id,result):
    case=next(case for case in CASES if case['id']==case_id)
    at=int(time.time()*1000)-10000
    return {'id':case_id+'-manual-result','feedbackTestId':case_id,'tag_name':case['command_tag'],
            'address':TAGS[case['command_tag']]['device_address'],'startedAt':at,'oneRequestedAt':at,
            'oneAcceptedAt':at+100,'zeroAcceptedAt':at+200,'zeroSeenAt':at+300,'events':[],
            'operatorResult':result,'operatorResultAt':at+400,
            **({'operatorCompletedAt':at+400} if result=='pass' else {'issueAt':at+400})}


def test_feedback_workbench_has_a_compact_picker_and_selected_controls_without_a_fake_run(browser):
    state,wd,prefix,js,wait_for=browser
    wd(prefix+'/window/rect',{'width':1440,'height':1100})
    intercept_test(browser)
    select_pair(browser,'tank01-heaterremote')
    assert js("return document.getElementById('test-selected-name').textContent")=='Tank 01 HeaterRemote'
    assert js("const left=document.getElementById('test-picker').getBoundingClientRect(),right=document.getElementById('test-workspace').getBoundingClientRect();return left.right<right.left&&Math.abs(left.top-right.top)<2")
    assert js("return document.querySelectorAll('#test-list [data-test-id]').length")==len(CASES)==50
    assert js("return document.getElementById('test-workspace').contains(document.getElementById('test-timeout'))")
    assert js("return document.getElementById('test-timeout').value")=='15'
    assert js("return document.getElementById('test-result-detail').classList.contains('hidden')")
    assert js("return document.getElementById('test-result-state').dataset.state")=='NOT RUN'
    assert js("return document.getElementById('test-observation-timer').textContent")=='—'
    assert js("return document.getElementById('test-backend-result').classList.contains('hidden')")
    assert js('return window.testRequests')==[]
    assert not state['writes']


def test_selected_run_requires_one_confirmation_and_keeps_human_result_separate(browser):
    state,_,_,js,wait_for=browser
    intercept_test(browser,{'result':'TIMEOUT','actual_feedback':0,'elapsed_ms':15001,'http_status':200})
    select_pair(browser,'tank01-heaterremote')
    js("document.getElementById('test-run-selected').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    assert 'Tank01_HeaterRemote' in js("return document.getElementById('confirm-body').textContent")
    assert js("return document.getElementById('test-mode-hold').checked")
    assert js('return window.testRequests')==[]
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-result-state').dataset.state==='TIMEOUT'")
    assert js('return window.testRequests')==[{'id':'tank01-heaterremote','end_mode':'hold','mapping_under_test':True}]
    assert js("return document.getElementById('test-operator-result').value")=='unchecked'
    js("const choice=document.getElementById('test-operator-result');choice.value='fail';choice.dispatchEvent(new Event('change'))")
    assert js("return document.querySelector('[data-test-id=tank01-heaterremote]').dataset.operatorResult")=='fail'
    assert js("return document.getElementById('test-selected-human').textContent")=='Operator observed: Fail'
    assert js("return document.getElementById('test-result-state').dataset.state")=='TIMEOUT'
    assert '15001 ms' in js("return document.getElementById('test-backend-result').textContent")
    assert js("return document.getElementById('test-send-zero').getClientRects().length>0")
    assert len(js('return window.testRequests'))==1 and not state['writes']


def test_search_tank_and_human_result_filters_keep_all_pairs_and_saved_marks(browser):
    state,wd,prefix,js,wait_for=browser
    marks=[history_record('tank01-door-open','pass'),history_record('tank01-heaterremote','fail')]
    js('localStorage.setItem('+json.dumps(KEY)+','+json.dumps(json.dumps(marks))+')')
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.querySelector('[data-test-id=tank01-door-open]')?.dataset.operatorResult==='pass'")
    select_pair(browser,'tank01-door-open')
    assert js("return document.getElementById('test-selected-human').textContent")=='Operator verified: Pass'
    assert js("return document.getElementById('test-result-detail').classList.contains('hidden')")
    assert js("return document.getElementById('test-observation-timer').textContent")=='—'
    assert js("return document.getElementById('test-result-count').textContent")=='1 Pass · 1 Fail · 48 Not checked'
    set_filter(browser,'pass')
    assert visible_pairs(browser)==['tank01-door-open']
    js("const search=document.getElementById('test-search');search.value='Heater';search.dispatchEvent(new Event('input'))")
    assert visible_pairs(browser)==[]
    assert js("return !document.getElementById('test-case-empty').classList.contains('hidden')")
    js("document.getElementById('test-clear-filters').click();const tank=document.getElementById('test-tank-select');tank.value='Tank03';tank.dispatchEvent(new Event('change'))")
    assert set(visible_pairs(browser))=={case['id'] for case in CASES if case['command_tag'].startswith('Tank03_')}
    js("document.getElementById('test-clear-filters').click()")
    assert len(visible_pairs(browser))==50
    assert js("return document.querySelector('[data-test-id=tank01-door-open]').dataset.operatorResult")=='pass'
    assert js("return document.querySelector('[data-test-id=tank01-heaterremote]').dataset.operatorResult")=='fail'
    assert not state['writes']


def test_selecting_an_unrun_pair_does_not_show_another_runs_result_or_steal_focus(browser):
    state,_,_,js,wait_for=browser
    intercept_test(browser,hold=True)
    start_test(browser,'tank01-door-open')
    wait_for("return typeof window.releaseTest==='function'")
    select_pair(browser,'tank01-heaterremote')
    assert js("return document.getElementById('test-result-state').dataset.state")=='NOT RUN'
    assert js("return document.getElementById('test-observation-timer').textContent")=='—'
    js("document.getElementById('test-search').focus();window.releaseTest()")
    wait_for("return document.querySelector('#test-attempt-select option[data-case-id=tank01-door-open]').textContent.startsWith('PASS')")
    assert js("return document.getElementById('test-selected-name').textContent")=='Tank 01 HeaterRemote'
    assert js("return document.getElementById('test-result-state').dataset.state")=='NOT RUN'
    assert js('return document.activeElement.id')=='test-search'
    js("const select=document.getElementById('test-attempt-select');select.value=select.querySelector('option[data-case-id=tank01-door-open]').value;select.dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('test-selected-name').textContent")=='Tank 01 Door Open'
    assert js("return document.getElementById('test-result-state').dataset.state")=='PASS'
    assert js("return document.querySelector('[data-select-test=tank01-door-open]').getAttribute('aria-pressed')")=='true'
    assert len(js('return window.testRequests'))==1 and not state['writes']


def test_pair_labels_distinguish_local_configuration_from_supplier_confirmation(browser):
    state,_,_,js,_=browser
    select_pair(browser,'tank01-door-open')
    assert js("return document.querySelector('[data-test-id=tank01-door-open] .test-status').textContent")=='Local pair'
    assert js("return document.querySelector('[data-test-id=tank01-door-open] .test-status').dataset.state")=='CONFIGURED'
    assert 'reviewed docs' in js("return document.getElementById('test-selected-source').textContent")
    assert 'do not specify' in js("return document.getElementById('test-selected-source').textContent")
    assert js("return document.querySelectorAll('#test-list [data-needs-confirmation=false]').length")==14
    assert js("return document.querySelectorAll('#test-list [data-needs-confirmation=true]').length")==36
    assert js("return document.querySelector('.feedback-coverage a[href=\"#/commands\"]')!==null&&document.querySelector('.feedback-coverage a[href=\"#/write\"]')!==null")
    assert not state['writes']


@pytest.mark.parametrize('width',[1440,500])
def test_feedback_page_has_one_vertical_scroll_and_last_pair_controls_remain_reachable(browser,width):
    state,wd,prefix,js,wait_for=browser
    wd(prefix+'/window/rect',{'width':width,'height':1000})
    select_pair(browser,CASES[-1]['id'])
    metrics=js("const list=document.getElementById('test-list'),picker=document.getElementById('test-picker'),workspace=document.getElementById('test-workspace'),preview=document.getElementById('test-selected-pair');const css=getComputedStyle(list),rect=preview.getBoundingClientRect();return {overflow:css.overflowY,maxHeight:css.maxHeight,picker:getComputedStyle(picker).position,workspace:getComputedStyle(workspace).position,pageWidth:innerWidth,scrollWidth:document.documentElement.scrollWidth,pageHeight:innerHeight,scrollHeight:document.documentElement.scrollHeight,previewTop:rect.top,boxes:[...document.querySelectorAll('#test-workbench,#test-picker,#test-workspace,#test-tank-select,#test-list,#test-selected-pair')].map(element=>({id:element.id,width:element.getBoundingClientRect().width,left:element.getBoundingClientRect().left,columns:getComputedStyle(element).gridTemplateColumns,min:getComputedStyle(element).minWidth}))}")
    assert metrics['overflow']=='visible' and metrics['maxHeight']=='none'
    assert metrics['picker']!='sticky' and metrics['workspace']!='sticky'
    assert metrics['scrollWidth']<=metrics['pageWidth'],metrics
    assert metrics['scrollHeight']>metrics['pageHeight']
    assert 0<=metrics['previewTop']<metrics['pageHeight']
    assert js("return document.getElementById('test-selected-name').textContent")==CASES[-1]['name']
    assert js("return document.getElementById('test-run-selected').getClientRects().length>0")
    assert not state['writes']


def test_feedback_tank_selector_matches_native_manual_style_and_keeps_focus_and_selection(browser):
    state,_,_,js,wait_for=browser
    select_pair(browser,'tank01-door-open')
    assert js("return document.getElementById('test-tank-select').tagName")=='SELECT'
    assert not js("return document.getElementById('test-tank-tabs')")
    assert js("return document.querySelectorAll('#verify [role=tab]').length")==0
    groups=js("return [...document.getElementById('test-tank-select').options].map(option=>option.value)")
    assert groups[0]=='all' and 'Tank03' in groups and len(groups)>10
    js("const tank=document.getElementById('test-tank-select');window.savedTank=tank;tank.value='Tank03';tank.dispatchEvent(new Event('change'));tank.focus();document.getElementById('refresh-btn').click()")
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.querySelectorAll('#test-list [data-test-id]').length===50")
    assert js("return document.getElementById('test-tank-select').value")=='Tank03'
    assert js("return document.activeElement===window.savedTank&&window.savedTank===document.getElementById('test-tank-select')")
    assert all(case.startswith('tank03-') for case in visible_pairs(browser))
    assert not state['writes']


def go_page(browser,page):
    _,_,_,js,wait_for=browser
    js("document.querySelector('[data-nav="+page+"]').click()")
    wait_for("return document.querySelector('[data-nav="+page+"]').getAttribute('aria-current')==='page'")


def test_command_bits_bar_is_shared_by_all_write_pages_and_hidden_on_read_pages(browser):
    state,_,_,js,wait_for=browser
    state['values']['Tank03_FillWaterOn']=1
    go_page(browser,'verify')
    wait_for("return document.querySelector('[data-clear-tag=Tank03_FillWaterOn]')!==null")
    js("window.sharedCommandBar=document.getElementById('test-active-commands')")
    for page in ['verify','commands','write']:
        go_page(browser,page)
        assert js("return !document.getElementById('shared-write-signals').classList.contains('hidden')&&document.getElementById('test-active-commands').getClientRects().length>0")
        assert js("return document.getElementById('test-active-commands')===window.sharedCommandBar")
        assert js("return document.querySelectorAll('#test-active-commands').length")==1
    for page in ['overview','signals','tanks','alarms','catalog','logs']:
        go_page(browser,page)
        assert js("return document.getElementById('shared-write-signals').classList.contains('hidden')&&document.getElementById('test-active-commands').getClientRects().length===0")
    assert not state['writes']


@pytest.mark.parametrize('page',['verify','commands','write'])
def test_shared_command_bar_can_explicitly_clear_once_from_each_write_page_without_a_feedback_run(browser,page):
    state,_,_,js,wait_for=browser
    state['values']['Tank03_FillWaterOn']=1
    go_page(browser,page)
    wait_for("return document.querySelector('[data-clear-command=Tank03_FillWaterOn]')?.disabled===false")
    assert js("return document.getElementById('test-attempt-select').options.length")==1
    js("document.querySelector('[data-clear-command=Tank03_FillWaterOn]').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    assert 'Tank03_FillWaterOn' in js("return document.getElementById('confirm-body').textContent")
    assert 'Unclassified / no recorded plan' in js("return document.getElementById('confirm-body').textContent")
    assert 'No browser record — untracked readback' in js("return document.getElementById('confirm-body').textContent")
    assert 'does not guarantee that equipment stops' in js("return document.getElementById('confirm-body').textContent")
    assert not state['writes']
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes']==[{'tag_name':'Tank03_FillWaterOn','value':0}]
    assert js("return document.getElementById('shared-write-signals').getClientRects().length>0")
    assert js("return document.getElementById('test-last-clear').getClientRects().length>0")
    assert js("return getComputedStyle(document.getElementById('test-active-command-rows')).overflowY")=='visible'
    assert js("return document.getElementById('test-attempt-select').options.length")==1


@pytest.mark.parametrize('diagnostics',[False,True])
def test_backend_summary_only_shows_captured_diagnostic_fields_when_available(browser,diagnostics):
    state,_,_,js,wait_for=browser
    reply={'result':'TIMEOUT','actual_feedback':0,'elapsed_ms':15001,'http_status':200}
    if diagnostics: reply.update(command_readback=1,Remote=1,Local=0)
    intercept_test(browser,reply)
    start_test(browser)
    wait_for("return document.getElementById('test-result-state').dataset.state==='TIMEOUT'")
    summary=js("return document.getElementById('test-backend-result').textContent")
    if diagnostics:
        assert 'Command readback: 1' in summary and 'Remote: 1' in summary and 'Local: 0' in summary
        assert js("return document.getElementById('test-command-readback').textContent")=='0'
    else:
        assert 'Command readback:' not in summary and 'Remote:' not in summary and 'Local:' not in summary
    assert not state['writes']


@pytest.mark.parametrize('width',[1440,500])
def test_write_mode_control_is_compact_beside_refresh_and_keeps_confirmation_and_state_accessible(browser,width):
    state,wd,prefix,js,wait_for=browser
    wd(prefix+'/window/rect',{'width':width,'height':1000})
    js("document.getElementById('mode-btn').click()")
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'&&!document.getElementById('mode-btn').disabled")
    assert js("return document.getElementById('write-mode-state').textContent")=='WRITE MODE OFF'
    assert js("return document.getElementById('global-health').textContent")=='MONITORING READY'
    metrics=js("const control=document.getElementById('write-banner'),button=document.getElementById('mode-btn'),refresh=document.getElementById('refresh-btn'),rect=control.getBoundingClientRect(),b=button.getBoundingClientRect(),r=refresh.getBoundingClientRect();return {inHeader:!!control.closest('header.topbar'),sameActions:button.closest('.top-actions')===refresh.closest('.top-actions'),position:getComputedStyle(control).position,height:rect.height,buttonRight:b.right,refreshLeft:r.left,buttonTop:b.top,refreshTop:r.top,width:innerWidth,scrollWidth:document.documentElement.scrollWidth}")
    assert metrics['inHeader'] and metrics['sameActions'] and metrics['position']=='static'
    assert metrics['height']<=40 and metrics['scrollWidth']<=metrics['width'],metrics
    assert metrics['buttonRight']<=metrics['refreshLeft'] and abs(metrics['buttonTop']-metrics['refreshTop'])<3,metrics
    assert js("return document.getElementById('write-banner-note').classList.contains('sr-only')")
    assert js("return document.getElementById('mode-btn').getAttribute('aria-describedby')")=='write-banner-title write-banner-note'
    assert js("return document.getElementById('write-banner').getAttribute('role')")=='group'
    assert not state['mode'] and not state['writes']
    js("document.getElementById('mode-btn').click()")
    assert '30 minutes' in wd(prefix+'/alert/text')
    assert not state['mode'] and not state['writes']
    wd(prefix+'/alert/dismiss',{})
    wait_for("return !document.getElementById('mode-btn').disabled")
    assert js("return document.getElementById('write-mode-state').textContent")=='WRITE MODE OFF'
    js("document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for("return document.getElementById('write-banner-title').textContent==='WRITE TEST MODE ENABLED'")
    assert js("return document.getElementById('write-mode-state').textContent")=='WRITE MODE ON'
    assert js("return document.getElementById('global-health').textContent")=='READY TO TEST'
    assert '30 minutes' in js("return document.getElementById('mode-btn').title")
    state['mode']=False
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    assert js("return document.getElementById('write-mode-state').textContent")=='WRITE MODE OFF'
    assert js("return document.getElementById('global-health').textContent")=='MONITORING READY'
    assert not state['writes']


@pytest.mark.parametrize('intent',['manual0','hold','waiting'])
def test_shared_command_bar_separates_recorded_intent_live_bit_and_clear_plan(browser,intent):
    state,_,_,js,wait_for=browser
    tag='Tank01_FilterRemote'
    if intent=='waiting':
        intercept_test(browser,{'result':'OBSERVED','actual_feedback':1,'elapsed_ms':1234,'http_status':200},hold=True)
        start_test(browser,'tank01-filterremote',mode='hold')
        wait_for("return typeof window.releaseTest==='function'")
        state['values'][tag]=1
    else:
        choose_command(browser,tag)
        if intent=='hold': js("document.getElementById('bool-mode-hold').click()")
        checklist_write(browser,1)
        go_page(browser,'verify')
    expected={'manual0':'Needs 0','hold':'Recorded Hold 1','waiting':'Waiting for API'}[intent]
    row="document.querySelector('[data-clear-tag="+tag+"]')"
    wait_for('return '+row+"?.querySelector('.command-intent').textContent==="+json.dumps(expected))
    wait_for('return '+row+".querySelector('.command-readback').textContent==='Readback 1'")
    if intent=='hold':
        state['values'][tag]=0
        wait_for('return '+row+".querySelector('.command-readback').textContent==='Readback 0'")
        assert js('return '+row+".querySelector('.command-intent').textContent")=='Recorded Hold 1'
        assert tag in js("return document.getElementById('test-active-command-list').textContent")
    before=list(state['writes'])
    js(''+row+".querySelector('[data-clear-command]').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    confirmation=js("return document.getElementById('confirm-body').textContent")
    assert 'Recorded plan' in confirmation and ('Manual 0' if intent=='manual0' else 'Hold 1') in confirmation
    assert ('Feedback tests' if intent=='waiting' else 'Manual 0/1') in confirmation
    assert 'does not guarantee that equipment stops' in confirmation
    js("document.getElementById('confirm-dialog').close('cancel')")
    if intent=='waiting': js('window.releaseTest()')
    assert state['writes']==before


def test_review_selection_focuses_controls_and_readback_copy_does_not_invent_a_transition(browser):
    state,_,_,js,_=browser
    select_pair(browser,'tank01-door-open')
    assert js('return document.activeElement.id')=='test-selected-pair'
    assert js("return document.getElementById('test-selected-live').textContent")=='Command 0 · Feedback 0'
    assert js("return document.getElementById('bool-mark-complete').textContent")=='Mark Pass'
    assert js("return document.getElementById('bool-mark-incomplete').textContent")=='Mark Not checked'
    assert js("return document.getElementById('bool-issue').textContent")=='Record Fail'
    go_page(browser,'write')
    js("document.querySelector('.feedback-table').focus()")
    assert js("return document.activeElement===document.querySelector('.feedback-table')")
    assert js("return document.querySelector('.feedback-table').getAttribute('aria-label')")=='Read signals and recorded feedback'
    assert not state['writes']


def test_choose_another_pair_returns_to_picker_on_narrow_page_without_changing_saved_or_run_state(browser):
    state,wd,prefix,js,wait_for=browser
    wd(prefix+'/window/rect',{'width':500,'height':1000})
    intercept_test(browser,{'result':'TIMEOUT','actual_feedback':0,'elapsed_ms':15001,'http_status':200})
    js("const input=document.getElementById('test-timeout');input.value='75';input.dispatchEvent(new Event('input'))")
    start_test(browser,'tank01-door-open')
    wait_for("return document.getElementById('test-result-state').dataset.state==='TIMEOUT'")
    js("const choice=document.getElementById('test-operator-result');choice.value='fail';choice.dispatchEvent(new Event('change'));const input=document.getElementById('test-timeout');input.value='27';input.dispatchEvent(new Event('input'))")
    js("const search=document.getElementById('test-search');search.value='Remote';search.dispatchEvent(new Event('input'));const filter=document.getElementById('test-result-filter');filter.value='unchecked';filter.dispatchEvent(new Event('change'))")
    select_pair(browser,CASES[-1]['id'])
    assert js('return scrollY')>200
    before=js('return localStorage.getItem('+json.dumps(KEY)+')')
    requests=js('return window.testRequests')
    count=js("return document.getElementById('test-attempt-count').textContent")
    js("document.getElementById('test-choose-another').click()")
    assert js('return document.activeElement.id')=='test-search'
    assert js("const rect=document.getElementById('test-search').getBoundingClientRect();return rect.top>=0&&rect.bottom<=innerHeight")
    assert js("return document.getElementById('test-search').value")=='Remote'
    assert js("return document.getElementById('test-result-filter').value")=='unchecked'
    assert js("return document.getElementById('test-timeout').value")=='27'
    assert js("return document.getElementById('test-selected-name').textContent")==CASES[-1]['name']
    assert js("return document.querySelector('[data-select-test="+CASES[-1]['id']+"]').getAttribute('aria-pressed')")=='true'
    assert js("return document.getElementById('test-attempt-count').textContent")==count
    assert js('return localStorage.getItem('+json.dumps(KEY)+')')==before
    assert js('return window.testRequests')==requests
    assert not state['writes']
