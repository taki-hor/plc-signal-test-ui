"""Hold/reset guidance uses the existing isolated browser harness, never the line."""
import json
import time

from server.config import ROOT
from test_frontend_safety import browser, harness, pytestmark, choose_command, checklist_write


def test_selected_guidance_explains_evidence_without_changing_controls_or_writing(browser):
    state, _, _, js, wait_for = browser
    js("document.querySelector('[data-nav=commands]').click()")
    for name, kind, evidence in [
        ('MainInlet','hold','inferred'),
        ('Tank01_FillWaterOn','hold','inferred'),
        ('Tank02_AirAgitationAuto','hold','polarity'),
        ('Tank07_CoolerOn','hold','inferred'),
        ('Tank01_FilterRemote','hold','supplier confirmation'),
        ('Tank01_DoorOpenRemote','reset','Operator confirmed'),
        ('Tank01_DoorCloseRemote','reset','Operator confirmed'),
        ('Tank03_DoorOpenRemote','reset','procedure remains unconfirmed'),
        ('Tank01_RemoteStart','unconfirmed','does not establish'),
    ]:
        choose_command(browser,name)
        assert js("return document.getElementById('bool-guidance').dataset.kind") == kind
        assert evidence in js("return document.getElementById('bool-rule-evidence').textContent")
        assert js("return document.getElementById('bool-guidance').getClientRects().length>0")
    choose_command(browser,'Tank02_AirAgitationAuto')
    assert 'Do not assume 0 stops' in js("return document.getElementById('bool-rule-zero').textContent")
    assert js("return document.getElementById('bool-one').textContent") == 'Send 1…'
    assert js("return document.getElementById('bool-zero').textContent") == 'Send 0…'
    assert js("return document.querySelectorAll('#command-checklist input[type=checkbox]').length") == 0
    assert not state['writes']


def test_guidance_model_matches_manual_and_rejects_unknown_names_or_changed_confirmation(browser):
    state, _, _, js, wait_for = browser
    tags=json.loads((ROOT/'config/mock-tags.json').read_text())['tags']
    writable=[t for t in tags if t['read_write']=='W' and t['data_type']=='Bool']
    template=next(t for t in writable if t['tag_name']=='Tank01_DoorOpenRemote')
    unknowns=[{**template,'tag_name':name,'device_address':f'M{900+i}'} for i,name in enumerate(
        ['Tank02_DoorOpenRemote','Tank16_CoolerOn','Tank08_FillWaterOn','Tank07_HeaterRemote','Tank17_FillWaterOn','NewCommand'])]
    changed={**template,'device_address':'M999'}
    probes=writable+unknowns+[changed]
    js("window.ruleProbe=null;import('/js/command-guidance.js').then(({commandGuidance})=>{window.ruleProbe="+json.dumps(probes)+".map(commandGuidance)})")
    wait_for("return window.ruleProbe!==null")
    rules=js('return window.ruleProbe')
    assert {kind:sum(r['kind']==kind for r in rules[:102]) for kind in ['hold','reset','unconfirmed']} == {'hold':72,'reset':14,'unconfirmed':16}
    assert sum(r.get('confirmed',False) for r in rules[:102]) == 2
    assert all(r['kind']=='unconfirmed' and r['confirmed'] is False for r in rules[102:108])
    assert rules[-1]['confirmed'] is False and 'unconfirmed' in rules[-1]['evidence']
    assert not state['writes']


def test_existing_single_confirmation_repeats_guidance_and_never_auto_clears(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser,'Tank01_DoorOpenRemote')
    js("document.getElementById('bool-one').click()")
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    dialog=js("return document.getElementById('confirm-body').textContent")
    assert 'Hold 1 while the door moves.' in dialog and 'Operator confirmed' in dialog
    assert 'One write only' in dialog
    js("document.getElementById('confirm-dialog').close('cancel')")
    assert not state['writes']
    checklist_write(browser,1)
    state['values']['Tank01_DoorOpened']=1
    wait_for("return document.getElementById('bool-completion').textContent==='CONFIRMED'")
    time.sleep(.4)
    assert state['writes'] == [{'tag_name':'Tank01_DoorOpenRemote','value':1}]
    js("document.getElementById('bool-zero').click()")
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    assert 'Send 0 after physical movement finishes.' in js("return document.getElementById('confirm-body').textContent")
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    assert state['writes'] == [{'tag_name':'Tank01_DoorOpenRemote','value':1},{'tag_name':'Tank01_DoorOpenRemote','value':0}]
