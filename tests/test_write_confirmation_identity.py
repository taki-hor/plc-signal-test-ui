"""Stale write reviews are blocked using only the isolated loopback fake API."""
import json
import time

import pytest

from test_frontend_safety import browser, harness, pytestmark, choose_command

TAG = 'Tank01_FilterRemote'


def open_review(browser, surface):
    _, _, _, js, _ = browser
    if surface == 'manual':
        choose_command(browser, TAG)
        js("document.getElementById('bool-one').click()")
    elif surface == 'batch':
        js("document.querySelector('[data-nav=write]').click();document.querySelector('.batch-panel').open=true;document.getElementById('batch-json').value=JSON.stringify([{tag_name:'Tank01_FilterRemote',value:1}]);document.getElementById('batch-submit').click()")
    else:
        js("document.querySelector('[data-nav=write]').click();document.getElementById('write-tag').value='Tank01_FilterRemote';document.getElementById('write-tag').dispatchEvent(new Event('change'));document.getElementById('write-bool-one').click();document.getElementById('write-submit').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    js("window.identityPosts=[];window.identityFetch=window.fetch;window.fetch=async (url,options={})=>{if(options.method==='POST')window.identityPosts.push(url);return window.identityFetch(url,options)}")


def confirm_review(browser):
    _, _, _, js, wait_for = browser
    js("window.identityReviewFinished=false;document.getElementById('confirm-dialog').addEventListener('close',()=>setTimeout(()=>window.identityReviewFinished=true,0),{once:true});document.getElementById('confirm-yes').click()")
    wait_for('return window.identityReviewFinished')


def change_review_context(browser, change):
    _, _, _, js, wait_for = browser
    if change in ('api', 'mode'):
        mutation = "data.api_address='OTHER REVIEW API';" if change == 'api' else "data.mode='REAL';"
        js("window.changedIdentityFetch=window.fetch;window.fetch=async (url,options)=>{const response=await window.changedIdentityFetch(url,options);if(url!=='/api/status')return response;const data=await response.json();"+mutation+"return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
        condition = "document.getElementById('api-address').textContent==='OTHER REVIEW API'" if change == 'api' else "document.getElementById('mock-badge').classList.contains('hidden')"
        wait_for('return '+condition)
    else:
        field, value = {'address':('device_address','M999'), 'type':('data_type','Word'), 'permission':('read_write','R'), 'multiplier':('multiplier',0.1)}[change]
        js("window.changedIdentityFetch=window.fetch;window.identityCatalogReads=0;window.identityReviewOption=document.getElementById('write-tag').selectedOptions[0];window.fetch=async (url,options)=>{const response=await window.changedIdentityFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();data.tags=data.tags.map(tag=>tag.tag_name==="+json.dumps(TAG)+"?{...tag,"+json.dumps(field)+":"+json.dumps(value)+"}:tag);window.identityCatalogReads++;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
        wait_for('return window.identityCatalogReads>0&&!window.identityReviewOption.isConnected')
        wait_for("return document.getElementById('freshness').textContent==='FRESH'")


@pytest.mark.parametrize('surface', ['manual','batch'])
@pytest.mark.parametrize('change', ['address','type','permission','multiplier','api','mode'])
def test_changed_identity_blocks_before_observation_or_post(browser, surface, change):
    state, _, _, js, wait_for = browser
    open_review(browser, surface)
    change_review_context(browser, change)
    confirm_review(browser)
    assert js('return window.identityPosts') == []
    assert not state['writes']
    assert js("return Object.keys(localStorage).filter(k=>/^plc-(?:command-checklist|value-feedback):/.test(k)).every(k=>JSON.parse(localStorage.getItem(k)).length===0)")


def test_single_value_review_also_captures_multiplier(browser):
    state, _, _, js, wait_for = browser
    open_review(browser, 'single')
    change_review_context(browser, 'multiplier')
    confirm_review(browser)
    assert js('return window.identityPosts') == []
    assert not state['writes']


@pytest.mark.parametrize('surface', ['manual','batch','single'])
def test_unchanged_metadata_refresh_keeps_one_explicit_confirmed_write(browser, surface):
    state, _, _, js, wait_for = browser
    open_review(browser, surface)
    reads = state.get('catalog_reads',0)
    js("document.getElementById('refresh-btn').click()")
    wait_for("return document.getElementById('freshness').textContent==='FRESH'")
    for _ in range(20):
        if state.get('catalog_reads',0)>reads: break
        time.sleep(.05)
    assert state.get('catalog_reads',0)>reads
    confirm_review(browser)
    marker = "document.getElementById('bool-sent-one').dataset.verified==='true'" if surface=='manual' else "document.getElementById('batch-result').textContent.startsWith('BATCH ACCEPTED')" if surface=='batch' else "document.getElementById('write-result').textContent.startsWith('WRITE ACCEPTED')"
    wait_for('return '+marker)
    assert js('return window.identityPosts.length')==1
    expected = {'writes':[{'tag_name':TAG,'value':1}], 'confirmation':'CONFIRM BATCH WRITE'} if surface=='batch' else {'tag_name':TAG,'value':1}
    assert state['writes'] == [expected]
