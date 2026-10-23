"""Live signal grouping checks use only the isolated loopback browser harness."""
import json

import pytest

from server.config import ROOT
from test_frontend_safety import harness, pytestmark

TAGS = json.loads((ROOT/'config/mock-tags.json').read_text())['tags']
GROUPS = ['Alarm','System']+[f'Tank{number:02}' for number in range(1,17)]
READ_COUNTS = [80,3,11,6,11,6,11,6,15,5,6,12,6,8,7,12,6,10]
ALL_COUNTS = [80,4,24,12,23,12,23,12,30,9,12,24,11,16,14,24,12,20]


@pytest.fixture
def live_signals(harness):
    state, wd, prefix, js, wait_for, url = harness
    state['fault'] = None
    state['mode'] = False
    state['values'].clear()
    state['writes'].clear()
    state['last_poll'] = None
    state['freeze_stamp'] = None
    wd(prefix+'/window/rect',{'width':1440,'height':1000})
    wd(prefix+'/url',{'url':url+'#/signals'})
    js('localStorage.clear()')
    wd(prefix+'/refresh',{})
    wait_for("return document.getElementById('freshness').textContent==='FRESH'&&document.getElementById('write-tag').options.length===141")
    yield state, wd, prefix, js, wait_for
    state['fault'] = None
    wd(prefix+'/url',{'url':'about:blank'})


def test_default_read_signals_show_every_tag_in_manual_groups_and_full_descriptions(live_signals):
    state, wd, prefix, js, wait_for = live_signals
    assert js("return document.getElementById('signal-filter').value") == 'R'
    assert js("return document.querySelectorAll('#signal-list .signal-card').length") == 221
    names = js("return [...document.querySelectorAll('#signal-list [data-signal-tag]')].map(card=>card.dataset.signalTag)")
    assert set(names) == {tag['tag_name'] for tag in TAGS if tag['read_write']=='R'}
    assert js("return [...document.querySelectorAll('#signal-list [data-signal-group]')].map(section=>section.dataset.signalGroup)") == GROUPS
    assert js("return [...document.querySelectorAll('#signal-list .signal-group-count')].map(count=>count.textContent)") == [f'{count} signals' for count in READ_COUNTS]
    assert js("return document.querySelector('#signal-list .signal-group-header h2').textContent") == 'Alarms'
    assert js("return document.getElementById('signal-total').textContent") == '221 / 362 signals'
    wd(prefix+'/window/rect',{'width':390,'height':900})
    description = next(tag['description'] for tag in TAGS if tag['tag_name']=='Tank01_TempPV')
    assert js("return document.querySelector('[data-signal-tag=Tank01_TempPV] small').textContent") == description
    assert js("const text=document.querySelector('[data-signal-tag=Tank01_TempPV] small'),style=getComputedStyle(text);return style.whiteSpace==='normal'&&style.textOverflow!=='ellipsis'&&text.scrollWidth<=text.clientWidth+1&&text.scrollHeight<=text.clientHeight+1")
    assert js("return document.documentElement.scrollWidth<=innerWidth+1")
    assert state['mode'] is False and not state['writes']


def test_all_signals_include_final_tags_and_tank01a_in_tank01(live_signals):
    state, _, _, js, wait_for = live_signals
    js("document.getElementById('signal-filter').value='all';document.getElementById('signal-filter').dispatchEvent(new Event('input'))")
    wait_for("return document.querySelectorAll('#signal-list .signal-card').length===362")
    assert set(js("return [...document.querySelectorAll('#signal-list [data-signal-tag]')].map(card=>card.dataset.signalTag)")) == {tag['tag_name'] for tag in TAGS}
    assert js("return [...document.querySelectorAll('#signal-list [data-signal-group]')].map(section=>section.dataset.signalGroup)") == GROUPS
    assert js("return [...document.querySelectorAll('#signal-list .signal-group-count')].map(count=>count.textContent)") == [f'{count} signals' for count in ALL_COUNTS]
    assert js("return document.querySelector('[data-signal-tag=Tank01A_USSV]').closest('[data-signal-group]').dataset.signalGroup") == 'Tank01'
    assert js("return document.querySelector('#signal-list [data-signal-group=Tank01] .signal-group-grid').querySelectorAll('.signal-card').length") == 24
    assert js("return document.querySelector('#signal-list .signal-group:last-child .signal-card:last-child').dataset.signalTag") == TAGS[-1]['tag_name'] == 'Tank16_WaterFlow'
    assert 'Showing first 120' not in js("return document.getElementById('signal-list').textContent")
    assert js("return document.getElementById('signal-total').textContent") == '362 / 362 signals'
    assert not state['writes']


def test_search_group_and_type_filters_combine_and_empty_results_can_be_cleared(live_signals):
    state, _, _, js, wait_for = live_signals
    js("document.getElementById('signal-filter').value='Bool';document.getElementById('signal-group').value='Tank01';document.getElementById('signal-search').value='remote';document.getElementById('signal-search').dispatchEvent(new Event('input'))")
    expected = {'Tank01_DoorCloseRemote','Tank01_DoorOpenRemote','Tank01_FilterRemote','Tank01_HeaterRemote','Tank01_RemoteStart','Tank01_USRemote'}
    assert set(js("return [...document.querySelectorAll('#signal-list [data-signal-tag]')].map(card=>card.dataset.signalTag)")) == expected
    assert js("return document.querySelectorAll('#signal-list [data-signal-group]').length") == 1
    assert js("return document.querySelector('#signal-list .signal-group-count').textContent") == '6 signals'
    js("document.getElementById('signal-filter').value='W';document.getElementById('signal-search').value='m320';document.getElementById('signal-search').dispatchEvent(new Event('input'))")
    assert js("return [...document.querySelectorAll('#signal-list [data-signal-tag]')].map(card=>card.dataset.signalTag)") == ['Tank01_FilterRemote']
    js("document.getElementById('signal-filter').value='Word';document.getElementById('signal-search').value='ussv';document.getElementById('signal-search').dispatchEvent(new Event('input'))")
    assert js("return [...document.querySelectorAll('#signal-list [data-signal-tag]')].map(card=>card.dataset.signalTag)") == ['Tank01A_USSV','Tank01B_USSV']
    js("document.getElementById('signal-search').value='not-in-the-catalog';document.getElementById('signal-search').dispatchEvent(new Event('input'))")
    assert js("return document.getElementById('signal-list').textContent") == 'No matching signals.'
    assert js("return document.getElementById('signal-total').textContent") == '0 / 362 signals'
    js("document.getElementById('signal-search').value='';document.getElementById('signal-group').value='all';document.getElementById('signal-filter').value='R';document.getElementById('signal-filter').dispatchEvent(new Event('input'))")
    wait_for("return document.querySelectorAll('#signal-list .signal-card').length===221")
    assert not state['writes']


def test_final_previously_truncated_card_updates_and_shows_connection_failures(live_signals):
    state, _, _, js, wait_for = live_signals
    selector = "document.querySelector('[data-signal-tag=Tank16_WaterFlow]')"
    state['values']['Tank16_WaterFlow'] = 37
    wait_for('return '+selector+"?.querySelector('.value').textContent==='37'")
    assert not js('return '+selector+".classList.contains('failed')")
    state['fault'] = 'signals_503'
    wait_for("return document.getElementById('api-state').textContent==='DISCONNECTED'")
    assert js('return '+selector+".classList.contains('failed')")
    assert js("return [...document.querySelectorAll('#signal-list .signal-card')].every(card=>card.classList.contains('failed'))")
    state['values']['Tank16_WaterFlow'] = 38
    state['fault'] = None
    wait_for('return '+selector+"?.querySelector('.value').textContent==='38'&&!"+selector+".classList.contains('failed')")
    assert js("return document.querySelectorAll('#signal-list .signal-card').length") == 221
    assert state['mode'] is False and not state['writes']
