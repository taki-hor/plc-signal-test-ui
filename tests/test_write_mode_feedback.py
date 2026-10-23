"""Global write-mode errors use only the isolated loopback API."""
import pytest

from test_frontend_safety import browser, harness, pytestmark


@pytest.mark.parametrize('route',['verify','commands','signals'])
def test_failed_enable_is_visible_on_every_route_and_success_clears_it(browser,route):
    state,wd,prefix,js,wait_for=browser
    js("document.querySelector('[data-nav="+route+"]').click();document.getElementById('mode-btn').click()")
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'&&!document.getElementById('mode-btn').disabled")
    js("window.modeTestFetch=window.fetch;window.fetch=async (url,options)=>url==='/api/mode/enable'?new Response(JSON.stringify({detail:'Mode permission denied',write_dispatched:false}),{status:403,headers:{'Content-Type':'application/json'}}):window.modeTestFetch(url,options);document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for("return !document.getElementById('mode-btn').disabled&&document.getElementById('mode-error').getClientRects().length>0")
    assert 'Mode permission denied' in js("return document.getElementById('mode-error').textContent")
    assert js("return document.getElementById('mode-error').getAttribute('role')")=='alert'
    assert js("return document.getElementById('write-submit').disabled")
    js("document.getElementById('refresh-btn').click()")
    wait_for("return document.getElementById('freshness').textContent==='FRESH'")
    assert js("return document.getElementById('mode-error').getClientRects().length>0")
    js("document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/dismiss',{})
    wait_for("return !document.getElementById('mode-btn').disabled")
    assert 'Mode permission denied' in js("return document.getElementById('mode-error').textContent")
    js("window.fetch=window.modeTestFetch;document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for("return document.getElementById('write-banner-title').textContent==='WRITE TEST MODE ENABLED'&&!document.getElementById('mode-btn').disabled")
    assert js("return document.getElementById('mode-error').classList.contains('hidden')&&document.getElementById('mode-error').textContent===''")
    assert not state['writes']


def test_failed_disable_reports_global_error_and_keeps_writes_locked(browser):
    state,wd,prefix,js,wait_for=browser
    js("document.querySelector('[data-nav=commands]').click();window.modeTestFetch=window.fetch;window.fetch=async (url,options)=>url==='/api/mode/disable'?new Response(JSON.stringify({detail:'Disable connection failed'}),{status:503,headers:{'Content-Type':'application/json'}}):window.modeTestFetch(url,options);document.getElementById('mode-btn').click()")
    wait_for("return !document.getElementById('mode-btn').disabled&&document.getElementById('mode-error').getClientRects().length>0")
    assert 'Disable connection failed' in js("return document.getElementById('mode-error').textContent")
    assert js("return document.getElementById('write-submit').disabled&&document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    js("window.fetch=window.modeTestFetch;document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for("return document.getElementById('write-banner-title').textContent==='WRITE TEST MODE ENABLED'&&!document.getElementById('mode-btn').disabled")
    assert js("return document.getElementById('mode-error').classList.contains('hidden')&&document.getElementById('mode-error').textContent===''")
    assert not state['writes']
