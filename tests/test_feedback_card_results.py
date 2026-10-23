"""Feedback card human-result checks use only the isolated loopback fake API."""
import json
import time

import pytest

from test_frontend_safety import browser, harness, pytestmark, choose_command, checklist_write
from test_verifier_ui import intercept_test, start_test

CASE='tank01-door-open'
TAG='Tank01_DoorOpenRemote'
KEY='plc-command-checklist:v1:MOCK:BROWSER TEST'
CARD="document.querySelector('[data-test-id="+CASE+"]')"


def card_result(browser,case=CASE):
    return browser[3]("return document.querySelector('[data-test-id="+case+"] [data-card-result]').dataset.cardResult")


def mark(browser,value):
    browser[3]("const choice=document.getElementById('test-operator-result');choice.value="+json.dumps(value)+";choice.dispatchEvent(new Event('change'))")


def reload_records(browser,records):
    state,wd,prefix,js,wait_for=browser
    js('localStorage.setItem('+json.dumps(KEY)+','+json.dumps(json.dumps(records))+')')
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&Boolean(document.querySelector('[data-test-id="+CASE+"] [data-card-result]'))")


def saved_record(result=None,case=CASE,**extra):
    now=int(time.time()*1000)-5000
    record={'id':'saved-physical-check','tag_name':TAG,'address':'M300','startedAt':now,
            'oneRequestedAt':now,'oneAcceptedAt':now+100,'zeroAcceptedAt':now+200,
            'zeroSeenAt':now+300,'feedbackTestId':case,'feedbackState':'CONFIRMED','events':[]}
    if result=='pass': record.update(operatorResult='pass',operatorCompletedAt=now+400,operatorResultAt=now+400)
    if result=='fail': record.update(operatorResult='fail',issueAt=now+400,operatorResultAt=now+400)
    record.update(extra)
    return record


@pytest.mark.parametrize('api_result',['PASS','OBSERVED','TIMEOUT'])
def test_only_human_choices_update_card_indicators_without_changing_mapping_or_dispatch(browser,api_result):
    state,_,_,js,wait_for=browser
    intercept_test(browser,{'result':api_result,'actual_feedback':0 if api_result=='TIMEOUT' else 1,'elapsed_ms':1234,'http_status':200})
    start_test(browser)
    wait_for("return document.getElementById('test-result-state').dataset.state==="+json.dumps(api_result))
    assert card_result(browser)=='unchecked'
    assert js('return '+CARD+".dataset.operatorResult")=='unchecked'
    assert js('return '+CARD+".querySelector('.test-status').textContent")=='Local pair'
    js('window.savedCard='+CARD)
    requests=js('return window.testRequests')
    for value,label in [('pass','✓ Pass'),('fail','✕ Fail'),('unchecked','Not checked')]:
        mark(browser,value)
        assert card_result(browser)==value
        assert js('return '+CARD+".dataset.operatorResult")==value
        assert js('return '+CARD+".querySelector('[data-card-result]').textContent")==label
        assert js('return '+CARD+".querySelector('.test-status').textContent")=='Local pair'
        assert js("return document.getElementById('test-result-state').dataset.state")==api_result
        assert js('return window.savedCard==='+CARD)
    js(''+CARD+".querySelector('[data-card-result]').click()")
    assert js('return window.testRequests')==requests
    assert not state['writes']


@pytest.mark.parametrize('result',['pass','fail'])
def test_card_result_survives_catalogue_refresh_and_browser_reload_in_readonly_mode(browser,result):
    state,wd,prefix,js,wait_for=browser
    intercept_test(browser)
    start_test(browser)
    wait_for("return document.getElementById('test-result-state').dataset.state==='PASS'")
    mark(browser,result)
    assert card_result(browser)==result
    js("document.getElementById('refresh-btn').click()")
    wait_for("return document.querySelector('[data-test-id="+CASE+"] [data-card-result]').dataset.cardResult==="+json.dumps(result))
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.querySelector('[data-test-id="+CASE+"] [data-card-result]')?.dataset.cardResult==="+json.dumps(result))
    assert js("return document.getElementById('write-banner-title').textContent")=='READ-ONLY MODE'
    assert not state['writes']


def test_api_cycle_without_a_human_choice_remains_unchecked_and_cleanup_does_not_erase_a_check(browser):
    state,_,_,js,_=browser
    reload_records(browser,[saved_record()])
    assert card_result(browser)=='unchecked'
    reload_records(browser,[saved_record('pass'),saved_record(id='cleanup',zeroOnlyCleanup=True,operatorResult='unchecked')])
    assert card_result(browser)=='pass'
    reload_records(browser,[saved_record('pass'),saved_record(id='new-attempt',oneRequestedAt=None,oneAcceptedAt=None,operatorResult='unchecked')])
    assert card_result(browser)=='unchecked'
    assert not state['writes']


def test_manual_checklist_human_result_can_highlight_the_same_command_card(browser):
    state,_,_,js,wait_for=browser
    choose_command(browser,TAG)
    checklist_write(browser,1)
    js("document.getElementById('bool-mark-complete').click()")
    assert card_result(browser)=='pass'
    js("document.getElementById('bool-issue').click()")
    assert card_result(browser)=='fail'
    assert state['writes']==[{'tag_name':TAG,'value':1}]


@pytest.mark.parametrize('identity',['api','mode','address','case'])
def test_card_never_applies_another_api_mode_address_or_case_human_result(browser,identity):
    state,_,_,js,wait_for=browser
    reload_records(browser,[saved_record('pass')])
    assert card_result(browser)=='pass'
    if identity=='address':
        endpoint='/api/tags'
        change="data.tags=data.tags.map(tag=>tag.tag_name==='Tank01_DoorOpenRemote'?{...tag,device_address:'M999'}:tag);"
    elif identity=='case':
        endpoint='/api/test/cases'
        change="data.tests=data.tests.map(test=>test.id==='tank01-door-open'?{...test,id:'different-door-case'}:test);"
    else:
        endpoint='/api/status'
        change="data.api_address='OTHER CARD API';" if identity=='api' else "data.mode='REAL';"
    js("window.cardScopeFetch=window.fetch;window.fetch=async function(url,options){const response=await window.cardScopeFetch(url,options);if(url!=="+json.dumps(endpoint)+")return response;const data=await response.json();"+change+"return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
    case='different-door-case' if identity=='case' else CASE
    wait_for("return document.querySelector('[data-test-id="+case+"] [data-card-result]')?.dataset.cardResult==='unchecked'")
    assert not state['writes']
