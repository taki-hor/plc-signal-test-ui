"""Human-result labels and keyboard selection use only the fake API."""
from test_frontend_safety import browser, harness, pytestmark, choose_command, checklist_write


def test_manual_uses_pass_fail_unchecked_badges_and_filters_without_extra_writes(browser):
    state,_,_,js,wait_for=browser
    tag='Tank01_FilterRemote'
    choose_command(browser,tag);checklist_write(browser,1)
    row="document.querySelector('[data-command-tag=Tank01_FilterRemote]')"
    before=js("return document.getElementById('bool-result').textContent")
    js("document.getElementById('bool-mark-complete').click()")
    assert js('return '+row+".dataset.operatorResult")=='pass'
    assert 'Pass' in js('return '+row+".querySelector('.manual-result-badge').textContent")
    assert js("return document.getElementById('bool-operator-state').textContent")=='PASS — YOUR CHECK'
    js("document.getElementById('bool-filter').value='complete';document.getElementById('bool-filter').dispatchEvent(new Event('input'))")
    assert js("return [...document.querySelectorAll('[data-command-tag]:not(.hidden)')].map(row=>row.dataset.commandTag)")==[tag]
    js("document.getElementById('bool-issue').click();document.getElementById('bool-filter').value='fail';document.getElementById('bool-filter').dispatchEvent(new Event('input'))")
    assert js('return '+row+".dataset.operatorResult")=='fail'
    assert 'Fail' in js('return '+row+".querySelector('.manual-result-badge').textContent")
    assert js("return document.getElementById('bool-operator-state').textContent")=='FAIL — YOUR CHECK'
    assert js("return [...document.querySelectorAll('[data-command-tag]:not(.hidden)')].map(row=>row.dataset.commandTag)")==[tag]
    js("document.getElementById('bool-mark-incomplete').click();document.getElementById('bool-filter').value='untested';document.getElementById('bool-filter').dispatchEvent(new Event('input'))")
    assert js('return '+row+".dataset.operatorResult")=='unchecked'
    assert js('return '+row+".querySelector('.manual-result-badge').textContent")=='Not checked'
    assert js('return !'+row+".classList.contains('hidden')")
    assert js("return document.getElementById('bool-result').textContent")==before
    assert state['writes']==[{'tag_name':tag,'value':1}]


def test_keyboard_selection_reaches_workspace_without_tabbing_through_all_commands(browser):
    state,wd,prefix,js,wait_for=browser
    js("document.querySelector('[data-nav=commands]').click()")
    wait_for("return !document.getElementById('command-checklist').classList.contains('hidden')")
    js("document.querySelector('[data-command-tag]').focus()")
    wd(prefix+'/actions',{'actions':[{'type':'key','id':'manual-select-key','actions':[{'type':'keyDown','value':'\ue007'},{'type':'keyUp','value':'\ue007'}]}]})
    wait_for("return document.activeElement.id==='bool-name'")
    wd(prefix+'/actions',{'actions':[{'type':'key','id':'manual-workspace-key','actions':[{'type':'keyDown','value':'\ue004'},{'type':'keyUp','value':'\ue004'}]}]})
    assert js("return Boolean(document.activeElement.closest('.bool-workspace'))")
    assert not js("return document.getElementById('confirm-dialog').open")
    assert not state['writes']
