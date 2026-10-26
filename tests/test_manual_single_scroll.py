"""The Manual0/1 browser uses page scrolling; tests use only the fake API."""
import pytest

from test_frontend_safety import browser, harness, pytestmark


@pytest.mark.parametrize('width',[1440,500])
def test_manual_last_command_and_controls_are_reachable_without_inner_scroll(browser,width):
    state,wd,prefix,js,wait_for=browser
    wd(prefix+'/window/rect',{'width':width,'height':1000})
    js("document.querySelector('[data-nav=commands]').click()")
    wait_for("return !document.getElementById('command-checklist').classList.contains('hidden')")
    assert js("return document.querySelectorAll('[data-command-tag]').length")==102
    assert js("return [...document.querySelectorAll('#command-checklist .bool-picker,#bool-list,#bool-log')].every(element=>{const style=getComputedStyle(element);return !['auto','scroll'].includes(style.overflowY)||element.scrollHeight<=element.clientHeight+1})")
    js("window.lastManualRow=[...document.querySelectorAll('[data-command-tag]')].at(-1);window.lastManualRow.scrollIntoView({block:'center'})")
    assert js("const rect=window.lastManualRow.getBoundingClientRect();return rect.top>=0&&rect.bottom<=innerHeight")
    expected=js('return window.lastManualRow.dataset.commandTag')
    js('window.lastManualRow.click()')
    wait_for("return document.getElementById('bool-name').textContent==="+repr(expected))
    assert js("const rect=document.getElementById('bool-name').getBoundingClientRect();return rect.top>=0&&rect.top<innerHeight")
    assert js("return document.documentElement.scrollWidth<=innerWidth")
    js("document.getElementById('bool-choose-another').click()")
    assert js("return document.activeElement.id")=='bool-search'
    assert js("const rect=document.getElementById('bool-search').getBoundingClientRect();return rect.top>=0&&rect.bottom<=innerHeight")
    assert js("return document.getElementById('bool-name').textContent")==expected
    assert not state['writes']
