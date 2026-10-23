"""Read-view health and identity regressions use only the loopback fake API."""
import json

from test_live_signals_ui import live_signals, harness, pytestmark, TAGS

READERS = [('signals','Tank01_TempPV','24.5'),('tanks','Tank01_TempPV','24.5'),('alarms','Alarm01','1')]


def row(view,tag):
    root = {'signals':'signal-list','tanks':'tank-grid','alarms':'alarm-list'}[view]
    return "document.querySelector('#"+root+" [data-signal-tag="+tag+"]')"


def show_view(browser,view):
    js, wait_for = browser[3:5]
    js("document.querySelector('[data-nav="+view+"]').click()")
    wait_for("return !document.getElementById('"+view+"').classList.contains('hidden')")


def test_tank_monitor_distinguishes_ab_channels_descriptions_and_read_write_roles(live_signals):
    state, wd, prefix, js, wait_for = live_signals
    show_view(live_signals,'tanks')
    js("document.querySelector('[data-tank=Tank01]').click()")
    wd(prefix+'/window/rect',{'width':390,'height':900})
    for suffix in ['A','B']:
        name='Tank01'+suffix+'_USSV'
        selector=row('tanks',name)
        assert js('return '+selector+".querySelector('.tank-name').textContent") == suffix+'_USSV'
        assert js('return '+selector+".closest('.tank-category').querySelector('h3').textContent") == 'Ultrasonic'
        assert js('return '+selector+".querySelector('.read-permission').textContent") == 'W · readback'
        description=next(tag['description'] for tag in TAGS if tag['tag_name']==name)
        assert js('return '+selector+".querySelector('.tank-description').textContent") == description
        assert js('const description='+selector+".querySelector('.tank-description'),style=getComputedStyle(description);return style.whiteSpace==='normal'&&style.textOverflow!=='ellipsis'&&description.scrollWidth<=description.clientWidth+1")
    assert js('return '+row('tanks','Tank01_TempPV')+".querySelector('.read-permission').textContent") == 'R · read-only'
    assert js('return '+row('tanks','Tank01_TempPV')+".querySelector('.value').textContent") == '0'
    assert js("return document.querySelectorAll('#tank-grid [data-signal-tag]').length") == 24
    assert state['mode'] is False and not state['writes']


def test_null_and_missing_values_have_worded_no_data_markers_in_all_three_views(live_signals):
    state, _, _, js, wait_for = live_signals
    state['values'].update(Tank01_TempPV=None,Alarm01=None)
    for view,tag,_ in READERS:
        selector=row(view,tag)
        wait_for('return '+selector+"?.querySelector('.read-state')?.textContent==='NO DATA'")
        show_view(live_signals,view)
        assert js('return '+selector+".querySelector('.value').textContent") == 'NO DATA'
        assert js('return '+selector+".classList.contains('failed')")
        assert js('return '+selector+".querySelector('.read-state').getClientRects().length>0")
    state['values'].update(Tank01_TempPV=24.5,Alarm01=1)
    for view,tag,value in READERS:
        wait_for('return '+row(view,tag)+"?.querySelector('.value').textContent==="+json.dumps(value)+'&&!'+row(view,tag)+".querySelector('.read-state')")
    js("window.readValueFetch=window.fetch;window.omitReadValues=true;window.fetch=async function(url,options){const response=await window.readValueFetch(url,options);if(url!=='/api/signals'||!window.omitReadValues)return response;const data=await response.json();delete data.Tank01_TempPV;delete data.Alarm01;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
    for view,tag,_ in READERS:
        wait_for('return '+row(view,tag)+"?.querySelector('.read-state')?.textContent==='NO DATA'")
        assert js('return '+row(view,tag)+".querySelector('.value').textContent") == 'NO DATA'
    js('window.omitReadValues=false')
    for view,tag,value in READERS:
        wait_for('return '+row(view,tag)+"?.querySelector('.value').textContent==="+json.dumps(value)+'&&!'+row(view,tag)+".classList.contains('failed')")
    assert state['mode'] is False and not state['writes']


def test_all_read_views_mark_stale_and_disconnected_cache_then_recover_live_values(live_signals):
    state, _, _, js, wait_for = live_signals
    state['values'].update(Tank01_TempPV=24.5,Alarm01=1)
    for view,tag,value in READERS:
        wait_for('return '+row(view,tag)+"?.querySelector('.value').textContent==="+json.dumps(value))
    js("window.readHealthFetch=window.fetch;window.readStale=true;window.fetch=async function(url,options){const response=await window.readHealthFetch(url,options);if(url!=='/api/status'||!window.readStale)return response;const data=await response.json();data.data_fresh=false;return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})}")
    for view,tag,value in READERS:
        selector=row(view,tag)
        wait_for('return '+selector+"?.querySelector('.read-state')?.textContent==='STALE'")
        show_view(live_signals,view)
        assert js('return '+selector+".querySelector('.value').textContent") == value
        assert js('return '+selector+".classList.contains('failed')")
        assert js('return '+selector+".querySelector('.read-state').getClientRects().length>0")
    state['fault']='signals_503'
    for view,tag,value in READERS:
        wait_for('return '+row(view,tag)+"?.querySelector('.read-state')?.textContent==='DISCONNECTED · last value'")
        assert js('return '+row(view,tag)+".querySelector('.value').textContent") == value
    state['values'].update(Tank01_TempPV=25.5,Alarm01=0)
    js('window.readStale=false')
    state['fault']=None
    for view,tag,value in [('signals','Tank01_TempPV','25.5'),('tanks','Tank01_TempPV','25.5'),('alarms','Alarm01','0')]:
        selector=row(view,tag)
        wait_for('return '+selector+"?.querySelector('.value').textContent==="+json.dumps(value)+'&&!'+selector+".querySelector('.read-state')&&!"+selector+".classList.contains('failed')")
    assert state['mode'] is False and not state['writes']


def test_tank_tabs_support_all_tanks_keyboard_focus_polling_and_mobile_overflow(live_signals):
    state, wd, prefix, js, wait_for = live_signals
    show_view(live_signals,'tanks')
    assert js("return document.getElementById('tank-select').getAttribute('role')") == 'tablist'
    assert js("return [...document.querySelectorAll('#tank-select [role=tab]')].map(tab=>tab.dataset.tank)") == [f'Tank{number:02}' for number in range(1,17)]
    assert js("return [...document.querySelectorAll('#tank-select [role=tab]')].every(tab=>tab.getAttribute('aria-controls')==='tank-grid')")
    js("document.querySelector('[data-tank=Tank16]').click()")
    assert js("return document.querySelector('[data-tank=Tank16]').getAttribute('aria-selected')") == 'true'
    assert set(js("return [...document.querySelectorAll('#tank-grid [data-signal-tag]')].map(row=>row.dataset.signalTag)")) == {tag['tag_name'] for tag in TAGS if tag['tag_name'].startswith('Tank16_')}
    for key,tank in [('\ue011','Tank01'),('\ue014','Tank02'),('\ue010','Tank16'),('\ue014','Tank01'),('\ue012','Tank16'),('\ue012','Tank15')]:
        wd(prefix+'/actions',{'actions':[{'type':'key','id':'tank-keys','actions':[{'type':'keyDown','value':key},{'type':'keyUp','value':key}]}]})
        assert js('return document.activeElement.dataset.tank') == tank
        assert js("return document.querySelector('#tank-select [aria-selected=true]').dataset.tank") == tank
    assert js("return document.querySelectorAll('#tank-select [tabindex=\"0\"]').length") == 1
    assert js("return document.getElementById('tank-grid').getAttribute('aria-labelledby')") == 'tank-tab-Tank15'
    state['values']['Tank15_WaterFlow']=17
    wait_for('return '+row('tanks','Tank15_WaterFlow')+"?.querySelector('.value').textContent==='17'")
    assert js('return document.activeElement.dataset.tank') == 'Tank15'
    assert js("return document.querySelector('#tank-select [aria-selected=true]').dataset.tank") == 'Tank15'
    wd(prefix+'/window/rect',{'width':390,'height':900})
    wd(prefix+'/actions',{'actions':[{'type':'key','id':'tank-keys','actions':[{'type':'keyDown','value':'\ue010'},{'type':'keyUp','value':'\ue010'}]}]})
    assert js("return document.getElementById('tank-select').scrollWidth>document.getElementById('tank-select').clientWidth")
    wait_for("const tabs=document.getElementById('tank-select').getBoundingClientRect(),selected=document.querySelector('[data-tank=Tank16]').getBoundingClientRect();return selected.left>=tabs.left-1&&selected.right<=tabs.right+1")
    assert js('return document.activeElement.dataset.tank') == 'Tank16'
    assert js("return document.documentElement.scrollWidth<=innerWidth+1")
    assert state['mode'] is False and not state['writes']
