"""Bool value choices use the isolated loopback API and never write to the line."""
import json

import pytest

from test_frontend_safety import browser, harness, pytestmark

BOOL = 'Tank01_FilterRemote'


def select_tag(browser, name):
    browser[3]("document.querySelector('[data-nav=write]').click();document.getElementById('write-tag').value="+json.dumps(name)+";document.getElementById('write-tag').dispatchEvent(new Event('change'))")


@pytest.mark.parametrize('value',[0,1])
def test_bool_choice_requires_review_and_confirmation_before_one_write(browser,value):
    state, _, _, js, wait_for=browser
    select_tag(browser,BOOL)
    assert js("return document.getElementById('write-value').classList.contains('hidden')")
    assert not js("return document.getElementById('write-bool-control').classList.contains('hidden')")
    js("document.getElementById('write-bool-"+('one' if value else 'zero')+"').click()")
    assert js("return document.getElementById('write-value').value")==str(value)
    assert not state['writes']
    js("document.getElementById('write-submit').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    assert js("return [...document.querySelectorAll('#confirm-body .detail-grid strong')].at(-1).textContent")==str(value)
    assert not state['writes']
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('write-result').textContent.startsWith('WRITE ACCEPTED')")
    assert state['writes']==[{'tag_name':BOOL,'value':value}]


def test_cancelling_bool_review_and_editing_readonly_choice_send_nothing(browser):
    state, _, _, js, wait_for=browser
    select_tag(browser,BOOL)
    js("document.getElementById('write-bool-one').click();document.getElementById('write-submit').click();document.getElementById('confirm-dialog').close('cancel')")
    assert not state['writes']
    state['mode']=False
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    js("document.getElementById('write-bool-zero').click()")
    assert js("return document.getElementById('write-value').value")=='0'
    assert js("return document.getElementById('write-submit').disabled")
    assert not state['writes']


def test_bool_draft_survives_status_and_catalog_refresh(browser):
    state, _, _, js, wait_for=browser
    select_tag(browser,BOOL)
    js("document.getElementById('write-bool-one').click();window.previousBoolOption=document.getElementById('write-tag').selectedOptions[0];document.getElementById('refresh-btn').click()")
    wait_for("return !window.previousBoolOption.isConnected")
    assert js("return document.getElementById('write-tag').value")==BOOL
    assert js("return document.getElementById('write-bool-one').checked&&document.getElementById('write-value').value==='1'")
    js("document.getElementById('write-value-label').click()")
    assert js("return document.getElementById('write-bool-one').checked")
    state['values'][BOOL]=1
    wait_for("return [...document.getElementById('write-detail').querySelectorAll('span')].find(item=>item.textContent==='Current').nextElementSibling.textContent==='1'")
    assert js("return document.getElementById('write-bool-one').checked")
    assert not state['writes']


@pytest.mark.parametrize('value',[0,1])
def test_prepared_bool_value_selects_matching_radio_without_dispatch(browser,value):
    state, _, _, js, wait_for=browser
    js("window.boolControls=null;const script=document.createElement('script');script.type='module';script.textContent=\"import * as controls from '/js/controls.js';window.boolControls=controls;\";document.body.appendChild(script)")
    wait_for('return window.boolControls!==null')
    assert js('return window.boolControls.prepareWrite('+json.dumps(BOOL)+','+str(value)+')')
    assert js("return location.hash")=='#/write'
    assert js("return document.getElementById('write-bool-"+('one' if value else 'zero')+"').checked")
    assert js("return document.getElementById('write-value').value")==str(value)
    assert not state['writes']


def test_numeric_setpoint_keeps_input_and_negative_value_validation(browser):
    state, _, _, js, wait_for=browser
    select_tag(browser,'Tank01_TempAdj')
    assert not js("return document.getElementById('write-value').classList.contains('hidden')")
    assert js("return document.getElementById('write-bool-control').classList.contains('hidden')")
    js("document.getElementById('write-value').value='-5';document.getElementById('write-submit').click()")
    assert js("return [...document.querySelectorAll('#confirm-body .detail-grid strong')].at(-1).textContent")=='-5'
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('write-result').textContent.startsWith('WRITE ACCEPTED')")
    assert state['writes']==[{'tag_name':'Tank01_TempAdj','value':-5}]


def test_invalid_numeric_draft_defaults_only_on_entering_bool_and_invalid_bool_cannot_dispatch(browser):
    state, _, _, js, _=browser
    select_tag(browser,'Tank01_TempSV')
    js("document.getElementById('write-value').value='25'")
    select_tag(browser,BOOL)
    assert js("return document.getElementById('write-value').value==='0'&&document.getElementById('write-bool-zero').checked")
    js("document.getElementById('write-value').value='2';document.getElementById('write-submit').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert 'Bool accepts 0 or 1' in js("return document.getElementById('write-result').textContent")
    assert not state['writes']


def test_programmatic_valid_bool_input_matches_visible_choice_before_confirmation(browser):
    state, _, _, js, _=browser
    select_tag(browser,BOOL)
    js("document.getElementById('write-value').value='1';document.getElementById('write-submit').click()")
    assert js("return document.getElementById('write-bool-one').checked")
    assert js("return [...document.querySelectorAll('#confirm-body .detail-grid strong')].at(-1).textContent")=='1'
    js("document.getElementById('confirm-dialog').close('cancel')")
    assert not state['writes']


@pytest.mark.parametrize('change',['address','type','permission','selection','api','mode'])
def test_changed_review_identity_blocks_before_observation_or_post(browser,change):
    state, _, _, js, wait_for=browser
    select_tag(browser,BOOL)
    js("document.getElementById('write-bool-one').click();document.getElementById('write-submit').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    js("window.reviewPosts=[];window.reviewFetch=window.fetch;window.fetch=async function(url,options={}){if(options.method==='POST')window.reviewPosts.push(url);return window.reviewFetch(url,options)}")
    if change=='selection':
        js("document.getElementById('write-tag').value='Tank01_HeaterRemote';document.getElementById('write-tag').dispatchEvent(new Event('change'))")
    elif change in ('api','mode'):
        mutation="data.api_address='OTHER API AFTER REVIEW';" if change=='api' else "data.mode='REAL';"
        js("window.reviewStatusFetch=window.fetch;window.fetch=async function(url,options){const response=await window.reviewStatusFetch(url,options);if(url!=='/api/status')return response;const data=await response.json();"+mutation+"return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
        if change=='api': wait_for("return document.getElementById('api-address').textContent==='OTHER API AFTER REVIEW'")
        else: wait_for("return document.getElementById('mock-badge').classList.contains('hidden')")
    else:
        field,value={'address':('device_address','M999'),'type':('data_type','Word'),'permission':('read_write','R')}[change]
        js("window.reviewCatalogFetch=window.fetch;window.previousReviewOption=document.getElementById('write-tag').selectedOptions[0];window.fetch=async function(url,options){const response=await window.reviewCatalogFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();data.tags=data.tags.map(tag=>tag.tag_name==="+json.dumps(BOOL)+"?{...tag,"+json.dumps(field)+":"+json.dumps(value)+"}:tag);return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
        wait_for('return !window.previousReviewOption.isConnected')
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('write-result').textContent.includes('Review the command again')")
    assert js('return window.reviewPosts')==[]
    assert not state['writes']
    assert js("return !localStorage.getItem('plc-value-feedback:v1:MOCK:BROWSER TEST')||JSON.parse(localStorage.getItem('plc-value-feedback:v1:MOCK:BROWSER TEST')).length===0")


def test_unchanged_catalog_refresh_preserves_reviewed_bool_and_allows_one_confirmed_write(browser):
    state, _, _, js, wait_for=browser
    select_tag(browser,BOOL)
    js("document.getElementById('write-bool-one').click();document.getElementById('write-submit').click();window.unchangedReviewOption=document.getElementById('write-tag').selectedOptions[0];document.getElementById('refresh-btn').click()")
    wait_for('return !window.unchangedReviewOption.isConnected')
    assert js("return document.getElementById('confirm-dialog').open&&document.getElementById('write-bool-one').checked")
    assert not state['writes']
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('write-result').textContent.startsWith('WRITE ACCEPTED')")
    assert state['writes']==[{'tag_name':BOOL,'value':1}]
