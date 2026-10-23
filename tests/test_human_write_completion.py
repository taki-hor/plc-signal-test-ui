"""Human completion is a local audit choice; all writes use the loopback fake API."""
import csv
import io
import json

import pytest

from test_frontend_safety import browser, harness, manual_records, manual_write, pytestmark

KEY = 'plc-value-feedback:v1:MOCK:BROWSER TEST'


def select_tag(js, name):
    js("document.querySelector('[data-nav=write]').click();document.getElementById('write-tag').value="+json.dumps(name)+";document.getElementById('write-tag').dispatchEvent(new Event('change'))")


def export_feedback(js, wait_for, format):
    js("window.humanExport=null;URL.createObjectURL=blob=>{blob.text().then(text=>window.humanExport=text);return 'blob:local-test'};HTMLAnchorElement.prototype.click=function(){};document.getElementById('write-feedback-export-"+format+"').click()")
    wait_for('return window.humanExport!==null')
    return js('return window.humanExport')


def choose_result(js,value):
    js("const choice=document.getElementById('write-feedback-operator-result');choice.value="+json.dumps(value)+";choice.dispatchEvent(new Event('change'))")


def spy_on_posts(js):
    js("window.humanPosts=[];window.humanFetch=window.fetch;window.fetch=(url,options={})=>{if(options.method==='POST')window.humanPosts.push(url);return window.humanFetch(url,options)}")


def test_observed_api_feedback_needs_human_mark_and_exports_reversible_persisted_choice(browser):
    state, wd, prefix, js, wait_for = browser
    manual_write(browser)
    state['values']['Tank01_DoorOpened'] = 1
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('EXPECTED FEEDBACK OBSERVED')")
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'AWAITING YOUR CHECK'
    assert not manual_records(js)[-1].get('operatorCompletedAt')
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.getElementById('write-tag').options.length>0")
    select_tag(js,'Tank01_DoorOpenRemote')
    assert js("return document.getElementById('write-banner-title').textContent") == 'READ-ONLY MODE'
    assert not js("return document.getElementById('write-feedback-operator-result').disabled")
    spy_on_posts(js)
    choose_result(js,'pass')
    record=manual_records(js)[-1]
    assert record['operatorCompletedAt'] and record['state']=='EXPECTED FEEDBACK OBSERVED'
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'PASS — YOUR CHECK'
    event=record['operatorEvents'][-1]
    assert event['action']=='Marked Pass by operator'
    assert event['write_id']==record['id'] and event['writes']==record['writes']
    assert event['mode']=='MOCK' and event['api_address']=='BROWSER TEST'
    assert event['api_result']=='EXPECTED FEEDBACK OBSERVED'
    exported=json.loads(export_feedback(js,wait_for,'json'))['records'][-1]
    assert exported['operatorCompletedAt']==record['operatorCompletedAt']
    rows=list(csv.DictReader(io.StringIO(export_feedback(js,wait_for,'csv'))))
    assert rows and all(row['operator_result']=='pass' for row in rows)
    assert rows[0]['operator_completed_at']==record['operatorCompletedAt']
    assert rows[0]['operator_result_at']==record['operatorResultAt']
    assert json.loads(rows[0]['operator_events'])[-1]==event
    api_fields={key:record.get(key) for key in ('state','before','after','feedback','requested_at','accepted_at')}
    choose_result(js,'fail')
    failed=manual_records(js)[-1]
    assert failed['operatorResult']=='fail' and failed['operatorCompletedAt'] is None
    assert js("return document.getElementById('write-feedback-operator-state').textContent")=='FAIL — YOUR CHECK'
    assert js("return document.getElementById('write-feedback-operator-state').dataset.cardResult")=='fail'
    assert failed['operatorEvents'][-1]['previous_operator_result']=='pass'
    assert failed['operatorEvents'][-1]['previous_operator_result_at']==record['operatorResultAt']
    assert failed['operatorEvents'][-1]['previous_operator_completed_at']==record['operatorCompletedAt']
    assert {key:failed.get(key) for key in api_fields}==api_fields
    choose_result(js,'pass')
    corrected=manual_records(js)[-1]
    assert corrected['operatorResult']=='pass' and corrected['operatorCompletedAt']
    assert corrected['operatorEvents'][-1]['previous_operator_result']=='fail'
    assert {key:corrected.get(key) for key in api_fields}==api_fields
    choose_result(js,'unchecked')
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'AWAITING YOUR CHECK'
    undone=manual_records(js)[-1]
    assert undone['operatorCompletedAt'] is None and undone['state']==record['state']
    assert undone['operatorEvents'][-1]['action']=='Marked Not checked by operator'
    assert undone['operatorEvents'][-1]['previous_operator_completed_at']==corrected['operatorCompletedAt']
    assert js('return window.humanPosts')==[]
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.getElementById('write-tag').options.length>0")
    select_tag(js,'Tank01_DoorOpenRemote')
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'AWAITING YOUR CHECK'
    assert len(manual_records(js)[-1]['operatorEvents'])==4
    assert state['writes']==[{'tag_name':'Tank01_DoorOpenRemote','value':1}]


def test_batch_feedback_does_not_mark_complete_and_one_human_choice_covers_exact_batch(browser):
    state, _, _, js, wait_for = browser
    writes=[{'tag_name':'Tank01_DoorOpenRemote','value':1},{'tag_name':'Tank01_FilterRemote','value':1}]
    js("document.querySelector('[data-nav=write]').click();document.getElementById('batch-json').value="+json.dumps(json.dumps(writes))+";document.getElementById('batch-submit').click();document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('batch-result').textContent.startsWith('BATCH ACCEPTED')")
    state['values'].update(Tank01_DoorOpened=1,Tank01_FilterStatus=1)
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('EXPECTED FEEDBACK OBSERVED')")
    assert not manual_records(js)[-1].get('operatorCompletedAt')
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'AWAITING YOUR CHECK'
    spy_on_posts(js)
    choose_result(js,'fail')
    failed=manual_records(js)[-1]
    assert failed['operatorEvents'][-1]['writes']==writes
    select_tag(js,'Tank01_FilterRemote')
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'FAIL — YOUR CHECK'
    assert manual_records(js)[-1]['id']==failed['id']
    choose_result(js,'pass')
    assert manual_records(js)[-1]['operatorEvents'][-1]['writes']==writes
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'PASS — YOUR CHECK'
    assert 'NEEDS CONFIRMATION' in js("return document.getElementById('write-feedback-result').textContent")
    assert js('return window.humanPosts')==[] and len(state['writes'])==1


def test_each_selected_observation_keeps_its_own_human_choice_across_reload(browser):
    state, wd, prefix, js, wait_for = browser
    manual_write(browser,'Tank01_TempSV',25)
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('READ SNAPSHOT RECORDED')")
    choose_result(js,'pass')
    first=manual_records(js)[-1]
    manual_write(browser,'Tank01_TempSV',30)
    wait_for("return JSON.parse(localStorage.getItem("+json.dumps(KEY)+")).length===2&&JSON.parse(localStorage.getItem("+json.dumps(KEY)+")).at(-1).state!=='SENDING'")
    second=manual_records(js)[-1]
    assert second['id']!=first['id'] and not second.get('operatorCompletedAt')
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'AWAITING YOUR CHECK'
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.getElementById('write-tag').options.length>0")
    select_tag(js,'Tank01_TempSV')
    js("document.getElementById('write-feedback-record').value="+json.dumps(first['id'])+";document.getElementById('write-feedback-record').dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'PASS — YOUR CHECK'
    assert 'Pass' in js("return document.getElementById('write-feedback-record').selectedOptions[0].textContent")
    js("document.getElementById('write-feedback-record').value="+json.dumps(second['id'])+";document.getElementById('write-feedback-record').dispatchEvent(new Event('change'))")
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'AWAITING YOUR CHECK'
    assert len(state['writes'])==2


def test_legacy_api_observation_stays_unconfirmed_but_can_be_checked_while_disconnected(browser):
    state, wd, prefix, js, wait_for = browser
    manual_write(browser,'Tank01_TempSV',25)
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('READ SNAPSHOT RECORDED')")
    js("const rows=JSON.parse(localStorage.getItem("+json.dumps(KEY)+"));for(const row of rows){delete row.operatorCompletedAt;delete row.operatorEvents;row.state='EXPECTED FEEDBACK OBSERVED';row.finishedAt=Date.now()}localStorage.setItem("+json.dumps(KEY)+",JSON.stringify(rows))")
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.getElementById('write-tag').options.length>0")
    select_tag(js,'Tank01_TempSV')
    assert js("return document.getElementById('write-feedback-operator-state').textContent") == 'AWAITING YOUR CHECK'
    state['fault']='signals_503'
    wait_for("return document.getElementById('write-feedback-health').textContent==='STALE / NO DATA'")
    assert not js("return document.getElementById('write-feedback-operator-result').disabled")
    spy_on_posts(js)
    choose_result(js,'pass')
    assert manual_records(js)[-1]['operatorCompletedAt']
    assert manual_records(js)[-1]['state']=='EXPECTED FEEDBACK OBSERVED'
    assert js('return window.humanPosts')==[] and len(state['writes'])==1


@pytest.mark.parametrize('fault,eligible',[('before_dispatch',False),('unknown',True)])
def test_human_choice_requires_an_accepted_or_possibly_dispatched_write(browser,fault,eligible):
    state, _, _, js, wait_for = browser
    state['write_fault']=fault
    manual_write(browser)
    assert js("return document.getElementById('write-feedback-operator-result').disabled") is not eligible
    spy_on_posts(js)
    choose_result(js,'pass')
    record=manual_records(js)[-1]
    assert bool(record.get('operatorCompletedAt')) is eligible
    assert js('return window.humanPosts')==[] and not state['writes']
    if eligible:
        rows=list(csv.DictReader(io.StringIO(export_feedback(js,wait_for,'csv'))))
        assert len(rows)==1 and rows[0]['operator_result']=='pass'
        assert rows[0]['result']=='OUTCOME UNKNOWN' and rows[0]['read_tag']==''
        assert json.loads(rows[0]['operator_events'])[-1]['action']=='Marked Pass by operator'


def test_human_mark_is_disabled_during_an_inflight_write(browser):
    state, _, _, js, wait_for = browser
    state['clear_hold']=True
    js("document.querySelector('[data-nav=write]').click();document.getElementById('write-tag').value='Tank01_DoorOpenRemote';document.getElementById('write-tag').dispatchEvent(new Event('change'));document.getElementById('write-value').value='0';document.getElementById('write-submit').click();document.getElementById('confirm-yes').click()")
    assert state['clear_entered'].wait(2)
    assert manual_records(js)[-1]['state']=='SENDING'
    assert js("return document.getElementById('write-feedback-operator-result').disabled")
    choose_result(js,'pass')
    assert not manual_records(js)[-1].get('operatorCompletedAt')
    state['clear_release'].set()
    wait_for("return !document.getElementById('write-feedback-operator-result').disabled")
    assert state['writes']==[{'tag_name':'Tank01_DoorOpenRemote','value':0}]


@pytest.mark.parametrize('stamp,explicit,expected',[
    ('2026-10-23T07:00:00+00:00',None,'pass'),
    (1792738800000,None,'pass'),
    ('2026-10-23T07:00:00+00:00','fail','fail'),
    ('2026-10-23T07:00:00+00:00','unchecked','unchecked'),
    (0,None,'unchecked'),
    ('not-a-date',None,'unchecked'),
])
def test_legacy_completion_requires_valid_human_time_and_explicit_choices_override_it(browser,stamp,explicit,expected):
    state, wd, prefix, js, wait_for=browser
    manual_write(browser,'Tank01_TempSV',25)
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('READ SNAPSHOT RECORDED')")
    mutation="row.operatorResult="+json.dumps(explicit)+";" if explicit is not None else 'delete row.operatorResult;'
    js("const rows=JSON.parse(localStorage.getItem("+json.dumps(KEY)+"));const row=rows.at(-1);row.operatorCompletedAt="+json.dumps(stamp)+";delete row.operatorResultAt;delete row.operatorEvents;"+mutation+"localStorage.setItem("+json.dumps(KEY)+",JSON.stringify(rows))")
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.getElementById('write-tag').options.length>0")
    select_tag(js,'Tank01_TempSV')
    assert js("return document.getElementById('write-feedback-operator-result').value")==expected
    assert js("return document.getElementById('write-feedback-operator-state').dataset.cardResult")==expected
    assert manual_records(js)[-1]['state']=='READ SNAPSHOT RECORDED'
    assert not manual_records(js)[-1].get('operatorEvents')
    exported=list(csv.DictReader(io.StringIO(export_feedback(js,wait_for,'csv'))))
    assert exported and all(row['operator_result']==expected and row['result']=='READ SNAPSHOT RECORDED' for row in exported)
    assert state['writes']==[{'tag_name':'Tank01_TempSV','value':25}]
