"""Parallel feedback UI tests use isolated intercepted runs and the loopback fake API."""
import json
import time

import pytest

from test_frontend_safety import ROOT, browser, harness, pytestmark
from test_verifier_ui import start_test

KEY='plc-command-checklist:v1:MOCK:BROWSER TEST'
FILTER='tank01-filterremote'
HEATER='tank01-heaterremote'


def intercept_parallel(browser):
    _,_,_,js,_=browser
    tags={tag['tag_name']:tag for tag in json.loads((ROOT/'config/mock-tags.json').read_text())['tags']}
    commands={case['id']:{'name':case['name'],'tag':case['command_tag'],'address':tags[case['command_tag']]['device_address']}
              for case in json.loads((ROOT/'config/test-cases.json').read_text())['tests']}
    js("window.parallelFetch=window.fetch;window.parallelCommands="+json.dumps(commands)+";window.parallelRequests=[];window.parallelReplies={};"+"""
      window.fetch=async function(url,options){
        if(url!=='/api/test/run')return window.parallelFetch(url,options);
        const body=JSON.parse(options.body);window.parallelRequests.push(body);
        const command=window.parallelCommands[body.id],snapshot=await(await window.parallelFetch('/api/status')).json();
        const receipt={written:true,console_command_address:command.address,console_accepted_at:new Date().toISOString(),console_command_baseline_utc:snapshot.supplier_timestamp_utc};
        return new Promise(resolve=>{window.parallelReplies[body.id]=(result='OBSERVED',elapsed=100)=>resolve(new Response(JSON.stringify({result,actual_feedback:result==='TIMEOUT'?0:1,elapsed_ms:elapsed,http_status:200,mapping_under_test:body.mapping_under_test===true,end_mode:body.end_mode,command_address:command.address,write_response:receipt}),{status:200,headers:{'Content-Type':'application/json'}}))});
      }
    """)


def wait_started(browser,case):
    browser[4]('return typeof window.parallelReplies['+json.dumps(case)+"]==='function'")


def release(browser,case,result='OBSERVED',elapsed=100):
    browser[3]('window.parallelReplies['+json.dumps(case)+']('+json.dumps(result)+','+str(elapsed)+')')


def choose_run(browser,case):
    _,_,_,js,_=browser
    js("const select=document.getElementById('test-attempt-select');select.value=[...select.options].find(option=>option.dataset.caseId==="+json.dumps(case)+").value;select.dispatchEvent(new Event('change'))")


def stored(browser):
    return browser[3]('return JSON.parse(localStorage.getItem('+json.dumps(KEY)+')||"[]")')


def test_different_feedback_runs_finish_out_of_order_without_replacing_selected_result_or_human_choice(browser):
    state,_,_,js,wait_for=browser
    intercept_parallel(browser)
    start_test(browser,FILTER);wait_started(browser,FILTER)
    assert not js("return document.querySelector('[data-test-id="+HEATER+"] button[data-run-test]').disabled")
    start_test(browser,HEATER);wait_started(browser,HEATER)
    assert js('return window.parallelRequests.length')==2
    assert js("return document.getElementById('test-attempt-select').querySelectorAll('option[data-run-id]').length")==2
    assert js("return document.getElementById('test-attempt-count').textContent").startswith('2 waiting')
    selected=js("return document.getElementById('test-attempt-select').value")
    js("document.getElementById('test-attempt-select').focus()")
    release(browser,FILTER,'OBSERVED',111)
    wait_for("return document.querySelector('#test-attempt-select option[data-case-id="+FILTER+"]').textContent.startsWith('OBSERVED')")
    assert js("return document.getElementById('test-attempt-select').value")==selected
    assert js("return document.activeElement.id")=='test-attempt-select'
    assert js("return document.getElementById('test-result-state').dataset.state")=='RUNNING'
    assert js("return document.getElementById('test-active-command').textContent")=='Tank01_HeaterRemote = 1'
    choose_run(browser,FILTER)
    assert '111 ms' in js("return document.getElementById('test-backend-result').textContent")
    js("const choice=document.getElementById('test-operator-result');choice.value='pass';choice.dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('test-operator-state').textContent")=='PASS — YOUR CHECK'
    frozen=js("return document.getElementById('test-observation-timer').textContent")
    release(browser,HEATER,'TIMEOUT',222)
    wait_for("return document.querySelector('#test-attempt-select option[data-case-id="+HEATER+"]').textContent.startsWith('TIMEOUT')")
    assert js("return document.getElementById('test-active-command').textContent")=='Tank01_FilterRemote = 1'
    assert js("return document.getElementById('test-operator-state').textContent")=='PASS — YOUR CHECK'
    assert js("return document.getElementById('test-observation-timer').textContent")==frozen
    choose_run(browser,HEATER)
    assert '222 ms' in js("return document.getElementById('test-backend-result').textContent")
    assert js("return document.getElementById('test-operator-state').textContent")=='AWAITING YOUR CHECK'
    js("const choice=document.getElementById('test-operator-result');choice.value='fail';choice.dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('test-result-state').dataset.state")=='TIMEOUT'
    rows={record['tag_name']:record for record in stored(browser)}
    assert rows['Tank01_FilterRemote']['operatorResult']=='pass'
    assert rows['Tank01_HeaterRemote']['operatorResult']=='fail'
    assert js("return document.getElementById('test-attempt-count').textContent").startswith('0 waiting')
    assert not js("return document.querySelector('[data-test-id=tank03-filterremote] button[data-run-test]').disabled")
    assert not state['writes']


def test_parallel_runs_keep_their_own_timeout_mode_and_elapsed_timer(browser):
    state,_,_,js,wait_for=browser
    intercept_parallel(browser)
    js("const input=document.getElementById('test-timeout');input.value='75';input.dispatchEvent(new Event('input'))")
    start_test(browser,FILTER,mode='manual0');wait_started(browser,FILTER)
    time.sleep(.25)
    js("const input=document.getElementById('test-timeout');input.value='15';input.dispatchEvent(new Event('input'))")
    start_test(browser,HEATER,mode='hold');wait_started(browser,HEATER)
    assert js("return document.getElementById('test-active-timeout').textContent")=='15 seconds'
    assert 'Hold 1' in js("return document.getElementById('test-operation-mode').textContent")
    choose_run(browser,FILTER)
    assert js("return document.getElementById('test-active-timeout').textContent")=='75 seconds'
    assert 'Manual 0' in js("return document.getElementById('test-operation-mode').textContent")
    assert float(js("return document.getElementById('test-observation-timer').textContent").split()[0])>=.2
    requests=js('return window.parallelRequests')
    assert requests[0]['timeout_ms']==75000 and requests[0]['end_mode']=='manual0'
    assert 'timeout_ms' not in requests[1] and requests[1]['end_mode']=='hold'
    release(browser,HEATER);release(browser,FILTER)
    wait_for("return document.getElementById('test-attempt-count').textContent.startsWith('0 waiting')")
    assert {record['tag_name']:record['timeout_ms'] for record in stored(browser)}=={'Tank01_FilterRemote':75000,'Tank01_HeaterRemote':15000}
    assert not state['writes']


def test_same_command_and_opposed_door_stay_blocked_while_other_tests_can_start(browser):
    state,_,_,js,_=browser
    intercept_parallel(browser)
    start_test(browser,'tank01-door-open');wait_started(browser,'tank01-door-open')
    assert js("return document.querySelector('[data-test-id=tank01-door-open] button[data-run-test]').disabled")
    assert js("return document.querySelector('[data-test-id=tank01-door-close] button[data-run-test]').disabled")
    assert not js("return document.querySelector('[data-test-id="+FILTER+"] button[data-run-test]').disabled")
    js("document.querySelector('[data-test-id=tank01-door-open] button[data-run-test]').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert js('return window.parallelRequests.length')==1
    release(browser,'tank01-door-open','TIMEOUT')
    assert not state['writes']


def test_manual_clear_during_one_wait_does_not_finish_or_replace_another_run(browser):
    state,_,_,js,wait_for=browser
    intercept_parallel(browser)
    start_test(browser,FILTER,mode='hold');wait_started(browser,FILTER)
    start_test(browser,HEATER);wait_started(browser,HEATER)
    state['values']['Tank01_FilterRemote']=1
    wait_for("return !document.querySelector('[data-clear-command=Tank01_FilterRemote]').disabled")
    js("document.querySelector('[data-clear-command=Tank01_FilterRemote]').click();document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('test-clear-state').textContent==='VERIFIED 0'")
    assert state['writes']==[{'tag_name':'Tank01_FilterRemote','value':0}]
    choose_run(browser,FILTER)
    assert 'RELEASED TO 0' in js("return document.getElementById('test-hold-state').textContent")
    choose_run(browser,HEATER)
    assert js("return document.getElementById('test-active-command').textContent")=='Tank01_HeaterRemote = 1'
    assert js("return document.getElementById('test-result-state').dataset.state")=='RUNNING'
    release(browser,FILTER,'INTERRUPTED',300)
    wait_for("return document.querySelector('#test-attempt-select option[data-case-id="+FILTER+"]').textContent.startsWith('INTERRUPTED')")
    assert js("return document.getElementById('test-active-command').textContent")=='Tank01_HeaterRemote = 1'
    assert js("return document.getElementById('test-result-state').dataset.state")=='RUNNING'
    row=next(record for record in stored(browser) if record['tag_name']=='Tank01_FilterRemote')
    assert row['zeroSeenAt'] and not row.get('operatorCompletedAt')
    choose_run(browser,FILTER)
    assert js("return document.getElementById('test-result-state').dataset.state")=='INTERRUPTED'
    assert js("return document.getElementById('test-operator-state').textContent")=='AWAITING YOUR CHECK'
    release(browser,HEATER,'TIMEOUT',400)
    wait_for("return document.getElementById('test-attempt-count').textContent.startsWith('0 waiting')")
    assert state['writes']==[{'tag_name':'Tank01_FilterRemote','value':0}]
