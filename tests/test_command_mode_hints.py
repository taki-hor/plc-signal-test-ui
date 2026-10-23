"""Manual hints are guidance only; these checks use the loopback fake API."""
import json

from server.config import ROOT
from test_frontend_safety import browser, harness, pytestmark, choose_command
from test_verifier_ui import intercept_test

TAGS=json.loads((ROOT/'config/mock-tags.json').read_text())['tags']


def test_manual_hold_hints_are_limited_and_never_claim_unconfirmed_rules_are_verified(browser):
    state, _, _, js, wait_for=browser
    commands=[tag for tag in TAGS if tag['read_write']=='W' and tag['data_type']=='Bool']
    template=next(tag for tag in commands if tag['tag_name']=='MainInlet')
    probes=commands+[{**template,'tag_name':'Unknown_FillWaterOn'},{**template,'tag_name':'Tank17_FilterRemote'}]
    js("window.hintRules=null;import('/js/command-guidance.js').then(({commandGuidance})=>window.hintRules="+json.dumps(probes)+".map(tag=>({name:tag.tag_name,...commandGuidance(tag)})))")
    wait_for('return window.hintRules!==null')
    rules=js('return window.hintRules')
    hinted=[rule for rule in rules if rule.get('hint')=='hold']
    assert len(hinted)==47 and all(rule['kind']=='hold' and not rule.get('confirmed') for rule in hinted)
    assert {rule['name'] for rule in rules if rule.get('confirmed')} == {'Tank01_DoorOpenRemote','Tank01_DoorCloseRemote'}
    assert all(not rule.get('hint') for rule in rules if rule['name'].endswith(('Auto','RemoteStart')))
    assert all(not rule.get('hint') and not rule.get('confirmed') for rule in rules[-2:])
    assert not state['writes']


def test_hint_markers_preserve_manual_defaults_user_choice_and_single_confirmation(browser):
    state, _, _, js, wait_for=browser
    choose_command(browser,'Tank01_FilterRemote')
    assert js("return !document.getElementById('bool-hold-hint').classList.contains('hidden')&&document.getElementById('bool-hold-hint').textContent==='Hint'")
    assert js("return document.getElementById('bool-mode-manual').checked")
    js("document.getElementById('bool-mode-hold').click()")
    initial=js("return document.getElementById('poll-time').textContent")
    wait_for("return document.getElementById('poll-time').textContent!=="+json.dumps(initial))
    assert js("return document.getElementById('bool-mode-hold').checked")
    js("document.getElementById('bool-mode-manual').click();document.getElementById('refresh-btn').click()")
    initial=js("return document.getElementById('poll-time').textContent")
    wait_for("return document.getElementById('poll-time').textContent!=="+json.dumps(initial))
    assert js("return document.getElementById('bool-mode-manual').checked")
    for name in ['Tank02_AirAgitationAuto','Tank01_RemoteStart']:
        choose_command(browser,name)
        assert js("return document.getElementById('bool-hold-hint').classList.contains('hidden')&&document.getElementById('bool-mode-manual').checked")
    choose_command(browser,'Tank01_DoorOpenRemote')
    assert js("return !document.getElementById('bool-manual-confirmed').classList.contains('hidden')&&document.getElementById('bool-manual-confirmed').textContent==='Confirmed'")
    choose_command(browser,'Tank03_DoorOpenRemote')
    assert js("return document.getElementById('bool-manual-confirmed').classList.contains('hidden')")
    intercept_test(browser)
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')")
    js("document.querySelector('[data-test-id=tank01-filterremote] button').click()")
    assert js("return document.getElementById('confirm-body').querySelector('[data-mode-hint=hold]').textContent") == 'Hint'
    assert js("return document.getElementById('test-mode-manual').checked")
    js("document.getElementById('confirm-dialog').close('cancel')")
    assert js('return window.testRequests') == []
    assert js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST')||'[]').length") == 0
    assert not state['writes']
