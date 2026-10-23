"""Navigation and status regressions use the isolated loopback fake API."""
import json

import pytest

from test_frontend_safety import browser, harness, pytestmark


@pytest.mark.parametrize('width', [1440, 500])
@pytest.mark.parametrize('route', ['commands', 'verify', 'catalog'])
def test_route_focus_and_active_navigation_are_visible_without_dispatch(browser, width, route):
    state, wd, prefix, js, wait_for = browser
    wd(prefix+'/window/rect', {'width':width, 'height':1000})
    js('location.hash='+json.dumps('#/'+route))
    wait_for("return document.activeElement===document.querySelector('[data-page]:not(.hidden) h1')")
    assert js('return document.querySelectorAll("[data-nav][aria-current=page]").length') == 1
    if width == 500:
        assert js("const r=document.querySelector('[data-nav][aria-current=page]').getBoundingClientRect(),n=document.querySelector('.side-nav').getBoundingClientRect();return r.left>=n.left-1&&r.right<=n.right+1")
    js("document.getElementById('skip-link').focus();document.getElementById('skip-link').click()")
    assert js('return location.hash') == '#/'+route
    assert js("return document.activeElement===document.querySelector('[data-page]:not(.hidden) h1')")
    assert js("const r=document.activeElement.getBoundingClientRect(),sticky=document.querySelector(innerWidth<=900?'.sidebar':'.topbar').getBoundingClientRect();return r.top>=sticky.bottom-1&&r.top<innerHeight")
    assert not state['writes']


def test_control_names_and_write_dialog_remain_accessible_and_cancelable(browser):
    state, _, _, js, wait_for = browser
    for selector in ['browser-type','browser-rw','browser-group','browser-sort','log-kind','batch-json']:
        assert js('return document.getElementById('+json.dumps(selector)+').getAttribute("aria-label")')
    js("location.hash='#/write'")
    wait_for("return !document.getElementById('write').classList.contains('hidden')")
    js("document.getElementById('write-tag').value='Tank01_TempAdj';document.getElementById('write-tag').dispatchEvent(new Event('change'));document.getElementById('write-value').value='-5';document.getElementById('write-submit').focus();document.getElementById('write-submit').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    assert js("return document.getElementById('confirm-dialog').getAttribute('aria-labelledby')") == 'confirm-title'
    assert js("return document.getElementById('confirm-dialog').getAttribute('aria-describedby')") == 'confirm-warning'
    assert js("return document.activeElement.closest('#confirm-dialog')!==null")
    js("document.querySelector('#confirm-dialog button[value=cancel]').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert js("return document.activeElement.id") == 'write-submit'
    assert not state['writes']


def test_warning_details_preserve_all_messages_and_expansion_during_polling(browser):
    state, _, _, js, wait_for = browser
    js("window.hciWarningFetch=window.fetch;window.fetch=async (...args)=>{const r=await window.hciWarningFetch(...args);if(args[0]!=='/api/status')return r;const d=await r.json();d.catalog_warnings=Array.from({length:20},(_,i)=>({message:'Review supplier warning '+i}));return new Response(JSON.stringify(d),{status:200})};location.hash='#/overview'")
    wait_for("return !document.getElementById('catalog-warning').classList.contains('hidden')")
    assert js("return document.getElementById('catalog-warning-summary').textContent") == '20 catalog warnings — review details'
    assert not js("return document.getElementById('catalog-warning').open")
    assert 'Review supplier warning 19' in js("return document.getElementById('catalog-warning-detail').textContent")
    js("document.getElementById('catalog-warning').open=true;window.hciPollCount=document.getElementById('poll-time').textContent")
    js("document.getElementById('refresh-btn').click()")
    wait_for("return document.getElementById('catalog-warning').open&&document.getElementById('freshness').textContent==='FRESH'")
    assert not state['writes']


def test_unchanged_human_status_does_not_emit_repeated_live_region_mutations(browser):
    state, _, _, js, wait_for = browser
    js("window.hciMutations=0;window.hciDone=false;window.hciStatusObserver=new MutationObserver(items=>window.hciMutations+=items.length);for(const id of ['bool-operator-state','write-feedback-operator-state','write-feedback-result'])window.hciStatusObserver.observe(document.getElementById(id),{childList:true,subtree:true,characterData:true});setTimeout(()=>{window.hciStatusObserver.disconnect();window.hciDone=true},850)")
    wait_for('return window.hciDone')
    assert js('return window.hciMutations') == 0
    assert not state['writes']
