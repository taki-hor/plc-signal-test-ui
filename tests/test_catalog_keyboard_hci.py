"""Catalogue keyboard checks use only the isolated loopback fake API."""
import json

from test_frontend_safety import ROOT, browser, harness, pytestmark

TAG='Tank01_TempAdj'
TAGS=json.loads((ROOT/'config/mock-tags.json').read_text())['tags']
ROW="[...document.querySelectorAll('#tag-table tr')].find(row=>row.cells[0].textContent==='"+TAG+"')"


def open_catalogue(browser):
    _,_,_,js,wait_for=browser
    js("document.querySelector('[data-nav=catalog]').click()")
    wait_for("return !document.getElementById('browser').classList.contains('hidden')&&Boolean("+ROW+"?.querySelector('button'))")


def test_catalogue_keeps_action_focus_and_dom_node_while_values_and_health_change(browser):
    state,_,_,js,wait_for=browser
    open_catalogue(browser)
    js("window.catalogueAction="+ROW+".querySelector('button');window.catalogueAction.focus();window.cataloguePolls=0;window.catalogueStale=false;window.catalogueFetch=window.fetch;window.fetch=async (url,options)=>{const response=await window.catalogueFetch(url,options);if(url==='/api/signals')window.cataloguePolls++;if(url!=='/api/status')return response;const data=await response.json();if(window.catalogueStale)data.data_fresh=false;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
    state['values'][TAG]=7.5
    wait_for("return window.cataloguePolls>=2&&"+ROW+".cells[8].textContent==='7.5'")
    assert js("return document.activeElement===window.catalogueAction&&window.catalogueAction==="+ROW+".querySelector('button')")
    assert js("return "+ROW+".cells[9].textContent")=='OK'
    js('window.catalogueStale=true')
    wait_for("return "+ROW+".cells[9].textContent==='FAILED'")
    assert js("return document.activeElement===window.catalogueAction&&window.catalogueAction.isConnected")
    js('window.catalogueStale=false')
    wait_for("return "+ROW+".cells[9].textContent==='OK'")
    assert js("return document.activeElement===window.catalogueAction&&window.catalogueAction==="+ROW+".querySelector('button')")
    assert not state['writes']


def test_catalogue_filters_and_metadata_refresh_rebuild_rows_and_actions_correctly(browser):
    state,_,_,js,wait_for=browser
    open_catalogue(browser)
    assert js("return document.querySelectorAll('#tag-table tr').length")==len(TAGS)
    assert js("return document.querySelectorAll('#tag-table button').length")==sum(t['read_write']=='W' for t in TAGS)
    js("window.catalogueOriginalRow="+ROW+";const query=document.getElementById('browser-search');query.value='"+TAG+"';query.dispatchEvent(new Event('input'))")
    assert js("return document.querySelectorAll('#tag-table tr').length") == 1
    assert not js('return window.catalogueOriginalRow.isConnected')
    js("const filter=document.getElementById('browser-rw');filter.value='R';filter.dispatchEvent(new Event('input'))")
    assert js("return document.querySelectorAll('#tag-table tr').length") == 0
    js("const filter=document.getElementById('browser-rw');filter.value='all';filter.dispatchEvent(new Event('input'));window.catalogueBeforeMetadata="+ROW+";window.catalogueFetch=window.fetch;window.fetch=async (url,options)=>{const response=await window.catalogueFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();data.tags=data.tags.map(tag=>tag.tag_name==='"+TAG+"'?{...tag,description:'HCI changed metadata',device_address:'D9999',read_write:'R'}:tag);return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};document.getElementById('refresh-btn').click()")
    wait_for("return "+ROW+"?.cells[2].textContent==='D9999'")
    assert js("return "+ROW+".cells[1].textContent")=='HCI changed metadata'
    assert js("return "+ROW+".cells[4].textContent")=='R'
    assert not js("return Boolean("+ROW+".querySelector('button'))")
    assert not js('return window.catalogueBeforeMetadata.isConnected')
    js("window.fetch=window.catalogueFetch;document.getElementById('refresh-btn').click()")
    wait_for("return Boolean("+ROW+"?.querySelector('button'))&&"+ROW+".cells[2].textContent==='D4010'")
    js("document.getElementById('browser-search').value='';document.getElementById('browser-search').dispatchEvent(new Event('input'))")
    assert js("return document.querySelectorAll('#tag-table tr').length")==len(TAGS)
    assert js("return document.querySelectorAll('#tag-table button').length")==sum(t['read_write']=='W' for t in TAGS)
    assert not state['writes']


def test_catalogue_action_has_signal_name_and_keyboard_selects_without_writing(browser):
    state,wd,prefix,js,wait_for=browser
    open_catalogue(browser)
    assert js("return "+ROW+".querySelector('button').getAttribute('aria-label')")=='Select '+TAG+' for write'
    js(ROW+".querySelector('button').focus()")
    wd(prefix+'/actions',{'actions':[{'type':'key','id':'keyboard','actions':[
        {'type':'keyDown','value':'\ue007'},{'type':'keyUp','value':'\ue007'}]}]})
    wait_for("return !document.getElementById('write').classList.contains('hidden')&&document.getElementById('write-tag').value==='"+TAG+"'")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert not state['writes']
