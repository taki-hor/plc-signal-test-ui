"""Browser safety regressions use only a loopback fake API; never the line API."""
import json
import shutil
import socket
import subprocess
import threading
import time
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from server.config import ROOT

pytestmark = pytest.mark.skipif(not shutil.which('geckodriver') or not shutil.which('firefox'),
                                reason='Firefox and geckodriver are required for browser regressions')


@pytest.fixture(scope='module')
def harness(tmp_path_factory):
    state = {'writes': [], 'fault': None, 'release': threading.Event(), 'values':{}, 'last_poll':None, 'freeze_stamp':None, 'mode':False, 'write_fault':None, 'status_hold':False, 'clear_hold':False, 'clear_entered':threading.Event(), 'clear_release':threading.Event(), 'clear_outcome':'accepted', 'validation_advance':False, 'omit_baseline':False}
    tags = json.loads((ROOT / 'config/mock-tags.json').read_text())['tags']
    cases = json.loads((ROOT / 'config/test-cases.json').read_text())['tests']

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT / 'frontend'), **kwargs)

        def log_message(self, *args): pass

        def reply(self, data, code=200, malformed=False):
            body = b'not-json' if malformed else json.dumps(data).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            try: self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError): pass

        def do_GET(self):
            if not self.path.startswith('/api/'): return super().do_GET()
            if self.path == '/api/signals' and state['fault'] == 'signals_hang':
                state['release'].wait(5)
            if ((self.path == '/api/signals' and state['fault'] == 'signals_503')
                    or (self.path == '/api/status' and state['fault'] == 'status_503')):
                return self.reply({'error':'Injected test connection failure'}, 503)
            if self.path == '/api/status' and state['fault'] == 'invalid_json':
                return self.reply({}, malformed=True)
            stamp = state['freeze_stamp'] or datetime.now(timezone.utc).isoformat()
            if self.path == '/api/signals': state['last_poll'] = stamp
            else: stamp = state['last_poll'] or stamp
            data = {
                '/api/tags': {'tags':tags},
                '/api/signals': {**{t['tag_name']:0 for t in tags}, **state['values'], 'timestamp':stamp, 'Remote':1},
                '/api/status': {'supplier_api_connected':True, 'plc_mode':'REMOTE', 'data_fresh':True,
                                'tags_ok':len(tags), 'tags_failed':0, 'api_address':'BROWSER TEST',
                                'last_successful_request':stamp, 'supplier_timestamp':stamp,
                                'data_age_ms':0, 'mode':'MOCK', 'last_error':None, 'supplier_timestamp_utc':stamp,
                                **({} if state['status_hold'] else {'write_mode_enabled':state['mode']}),
                                'catalog_warnings':[], 'poll_interval_ms':250, 'stale_after_ms':500},
                '/api/test/cases': {'tests':cases},
            }
            self.reply(data.get(self.path, {'logs':[]}))

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))) or '{}')
            if self.path == '/api/mode/enable':
                state['mode'] = True
                return self.reply({'write_token':'offline-test-token', 'expires_seconds':1800})
            if self.path in ('/api/write', '/api/write/batch'):
                if not state['mode']:
                    return self.reply({'detail':'WRITE TEST MODE is disabled or expired','write_dispatched':False},403)
                if state['write_fault'] == 'unknown': return self.reply({'error':'Uncertain supplier outcome'},502)
                if state['write_fault'] == 'before_dispatch': return self.reply({'error':'Read failed before dispatch','write_dispatched':False},503)
                if body.get('value') == 0 and state['clear_hold']:
                    state['clear_entered'].set(); state['clear_release'].wait(5)
                    if state['clear_outcome'] == 'blocked': return self.reply({'error':'Read failed before clear dispatch','write_dispatched':False},503)
                    if state['clear_outcome'] == 'unknown': return self.reply({'error':'Clear acknowledgement lost'},502)
                command_stamp = state['last_poll']
                if state['validation_advance']:
                    command_stamp = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
                    state['freeze_stamp'] = command_stamp
                requested_writes = body.get('writes', [body])
                read_baseline = {'supplier_timestamp':command_stamp, 'supplier_timestamp_utc':command_stamp,
                    'values':{t['tag_name']:state['values'].get(t['tag_name'],0) for t in tags if t['read_write']=='R'},
                    'mappings':[{k:c[k] for k in ('command_tag','command_value','feedback_tag','expected_feedback','requires_confirmation')}
                                for c in cases if any(w['tag_name']==c['command_tag'] and w['value']==c['command_value'] for w in requested_writes)]}
                state['writes'].append(body)
                case = next((c for c in cases if c['command_tag'] == body.get('tag_name') and c['command_value'] == body.get('value') and not c['requires_confirmation']), None)
                baseline = None if not case else {'feedback_tag':case['feedback_tag'], 'expected_feedback':case['expected_feedback'],
                    'value_before':state['values'].get(case['feedback_tag'],0), 'supplier_timestamp_utc':command_stamp}
                for item in body.get('writes', [body]): state['values'][item['tag_name']] = item['value']
                return self.reply({'written':True, **body, 'console_batch_accepted':True, 'console_accepted_at':datetime.now(timezone.utc).isoformat(), 'console_feedback_baseline':baseline,
                                   **({} if state['omit_baseline'] else {'console_command_baseline_utc':command_stamp,'console_read_baseline':read_baseline})})
            state['mode'] = False
            self.reply({'write_mode':'OFF'})

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        driver_port = sock.getsockname()[1]
    log = (tmp_path_factory.mktemp('browser') / 'geckodriver.log').open('w')
    driver = subprocess.Popen([shutil.which('geckodriver'), '--host','127.0.0.1','--port',str(driver_port)],
                              stdout=log, stderr=subprocess.STDOUT)
    http = httpx.Client(base_url=f'http://127.0.0.1:{driver_port}', timeout=30, trust_env=False)
    def wd(path, data=None, method=None):
        response = http.request(method or ('POST' if data is not None else 'GET'), path, json=data)
        response.raise_for_status()
        return response.json()['value']
    session = None
    try:
        for _ in range(100):
            try: wd('/status'); break
            except httpx.HTTPError: time.sleep(.1)
        session = wd('/session', {'capabilities':{'alwaysMatch':{'browserName':'firefox',
                         'moz:firefoxOptions':{'args':['-headless']}}}})['sessionId']
        prefix = f'/session/{session}'
        def js(script): return wd(prefix + '/execute/sync', {'script':script, 'args':[]})
        def wait_for(script):
            for _ in range(60):
                if js(script): return
                time.sleep(.1)
            pytest.fail(f'Browser condition did not become true: {script}')
        yield state, wd, prefix, js, wait_for, f'http://127.0.0.1:{server.server_port}/'
    finally:
        state['release'].set(); state['clear_release'].set()
        if session:
            try: wd(f'/session/{session}', method='DELETE')
            except httpx.HTTPError: pass
        http.close()
        driver.terminate()
        driver.wait(timeout=15)
        server.shutdown()
        log.close()


@pytest.fixture
def browser(harness):
    state, wd, prefix, js, wait_for, url = harness
    state['fault'] = None
    state['clear_hold'] = False; state['clear_outcome'] = 'accepted'; state['clear_entered'].clear(); state['clear_release'].clear()
    state['mode'] = False; state['status_hold'] = False; state['write_fault'] = None
    state['writes'].clear(); state['validation_advance']=False; state['omit_baseline']=False
    state['values'].clear(); state['last_poll'] = None; state['freeze_stamp'] = None
    state['release'].clear()
    wd(prefix + '/url', {'url':url})
    js('localStorage.clear()')
    wd(prefix + '/url', {'url':url})
    wait_for("return document.getElementById('freshness').textContent==='FRESH' && document.getElementById('write-tag').options.length>0")
    js("document.getElementById('mode-btn').click()")
    wd(prefix + '/alert/accept', {})
    wait_for("return !document.getElementById('write-submit').disabled")
    yield state, wd, prefix, js, wait_for
    state['fault'] = None
    state['release'].set(); state['clear_release'].set()
    wd(prefix + '/url', {'url':'about:blank'})


@pytest.mark.parametrize('batch', [False, True])
def test_escape_after_confirm_never_sends_another_write(browser, batch):
    state, wd, prefix, js, wait_for = browser
    if batch:
        review = "document.getElementById('batch-json').value=JSON.stringify([{tag_name:'Tank01_TempAdj',value:-5}]); document.getElementById('batch-submit').click()"
    else:
        review = "document.getElementById('write-tag').value='Tank01_TempAdj'; document.getElementById('write-value').value='-5'; document.getElementById('write-submit').click()"
    js(review)
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('confirm-dialog').returnValue==='confirm'")
    for _ in range(40):
        if len(state['writes']) == 1: break
        time.sleep(.05)
    assert len(state['writes']) == 1
    js(review)
    wd(prefix + '/actions', {'actions':[{'type':'key','id':'keyboard','actions':[
        {'type':'keyDown','value':'\ue00c'}, {'type':'keyUp','value':'\ue00c'}]}]})
    wait_for("return !document.getElementById('confirm-dialog').open")
    time.sleep(.2)
    assert len(state['writes']) == 1


@pytest.mark.parametrize('fault', ['signals_503','status_503','invalid_json','signals_hang'])
def test_failed_or_hung_refresh_removes_healthy_state_and_write_controls(browser, fault):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    assert not js("return document.getElementById('bool-one').disabled")
    state['fault'] = fault
    wait_for("return document.getElementById('api-state').textContent==='DISCONNECTED' && document.getElementById('write-submit').disabled")
    assert js("return document.getElementById('bool-one').disabled && document.getElementById('bool-zero').disabled")
    assert js("return document.getElementById('freshness').textContent!=='FRESH'")
    assert js("return document.getElementById('global-health').textContent==='CONNECTION ERROR'")
    assert not state['writes']


def choose_command(browser, name):
    _, _, _, js, wait_for = browser
    selector = json.dumps('[data-command-tag="' + name + '"]')
    js(f'document.querySelector({selector}).click()')
    wait_for("return document.getElementById('bool-name').textContent===" + json.dumps(name))


def checklist_write(browser, value):
    _, _, _, js, wait_for = browser
    button = 'bool-one' if value == 1 else 'bool-zero'
    assert not js(f"return document.getElementById('{button}').disabled")
    js(f"document.getElementById('{button}').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    js("document.getElementById('confirm-yes').click()")
    check = 'bool-sent-one' if value == 1 else 'bool-sent-zero'
    wait_for(f"return document.getElementById('{check}').dataset.verified==='true'")


def test_binary_catalog_single_confirmation_and_read_only_guards(browser):
    state, _, _, js, wait_for = browser
    assert js("return document.querySelectorAll('[data-command-tag]').length") == 102
    assert js("return document.querySelector('[data-command-tag=Tank01_DoorOpened]')===null")
    assert js("return document.getElementById('write-tag').options.length") == 141
    assert js("return document.getElementById('bool-one').disabled && document.getElementById('bool-zero').disabled")
    choose_command(browser, 'Tank01_DoorOpenRemote')
    assert not js("return document.getElementById('bool-one').disabled")
    js("document.getElementById('bool-search').value='Tank01_Door'; document.getElementById('bool-search').dispatchEvent(new Event('input'))")
    assert js("return [...document.querySelectorAll('[data-command-tag]')].filter(e=>!e.classList.contains('hidden')).length") == 2
    js("document.getElementById('mode-btn').click()")
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    assert js("return document.getElementById('bool-one').disabled && document.getElementById('bool-zero').disabled")
    assert not state['writes']


def test_binary_checklist_timer_persistence_and_exports(browser):
    state, wd, prefix, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser, 1)
    assert state['writes'] == [{'tag_name':'Tank01_DoorOpenRemote','value':1}]
    assert js("return document.querySelectorAll('#command-checklist input[type=checkbox]').length") == 0
    time.sleep(.2)
    assert js("return document.getElementById('bool-timer').textContent!=='00:00.0'")
    js("document.querySelector('#bool-log details').open=true")
    time.sleep(.6)
    assert js("return document.querySelector('#bool-log details').open")
    checklist_write(browser, 0)
    wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    wait_for("return document.getElementById('bool-result').textContent==='API CYCLE COMPLETE'")
    js("document.getElementById('bool-notes').value='=SUM(1,2)'; document.getElementById('bool-notes').dispatchEvent(new Event('input')); document.getElementById('bool-notes').dispatchEvent(new Event('change'))")
    assert len(state['writes']) == 2
    js("window.exportBlob=null; URL.createObjectURL=blob=>{window.exportBlob=blob;return 'blob:offline-test'}; HTMLAnchorElement.prototype.click=function(){}; document.getElementById('bool-export-csv').click()")
    js("window.exportText=null; window.exportBlob.text().then(t=>window.exportText=t)")
    wait_for('return window.exportText!==null')
    exported = js('return window.exportText')
    assert 'API accepted 1' in exported and 'API accepted 0' in exported and 'Later supplier poll verified command 0' in exported
    assert "'=SUM(1,2)" in exported and 'offline-test-token' not in exported
    assert 'console_accepted_at' in exported.splitlines()[0] and 'zero_baseline_supplier_timestamp_utc' in exported.splitlines()[0]
    js("document.getElementById('bool-export-json').click(); window.exportText=null; window.exportBlob.text().then(t=>window.exportText=t)")
    wait_for('return window.exportText!==null')
    data = json.loads(js('return window.exportText'))
    assert len(data['checklist']) == 102 and len(data['attempts']) == 1
    assert all(e['elapsed_ms'] >= 0 for e in data['attempts'][0]['events'])
    assert data['attempts'][0]['zeroSeenAt'] and data['attempts'][0]['finishedAt']
    url = wd(prefix + '/url')
    wd(prefix + '/url', {'url':url})
    wait_for("return document.querySelectorAll('[data-command-tag]').length===102")
    wait_for("return document.getElementById('bool-progress').textContent.startsWith('1 / 102 API cycles complete')")
    assert js("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    assert js("return document.querySelectorAll('#command-checklist input[type=checkbox]').length") == 0
    assert len(state['writes']) == 2


@pytest.mark.parametrize('ahead', [False, True])
def test_zero_verification_rejects_an_old_poll_even_when_value_is_zero(browser, ahead):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser, 1)
    state['freeze_stamp'] = state['last_poll']
    if ahead:
        # A slightly fast corrected supplier clock must not make cached 0 pass.
        state['freeze_stamp'] = (datetime.now(timezone.utc) + timedelta(seconds=2)).isoformat()
        state['values']['Tank01_DoorOpenRemote'] = 0
        expected = json.dumps(state['freeze_stamp'])
        wait_for(f"return document.getElementById('poll-time').textContent===new Date({expected}).toLocaleString() && document.getElementById('bool-value').textContent==='0'")
    checklist_write(browser, 0)
    time.sleep(.8)
    assert not js("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    state['freeze_stamp'] = None
    wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    assert len(state['writes']) == 2


def test_pending_command_blocks_other_commands_and_issue_can_be_cleared(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser, 1)
    choose_command(browser, 'Tank01_DoorCloseRemote')
    assert js("return document.getElementById('bool-one').disabled && document.getElementById('bool-zero').disabled")
    choose_command(browser, 'Tank01_DoorOpenRemote')
    js("document.getElementById('bool-issue').click()")
    assert js("return document.getElementById('bool-result').textContent==='ISSUE'")
    assert not js("return document.getElementById('bool-zero').disabled")
    checklist_write(browser, 0)
    wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    assert js("return document.getElementById('bool-result').textContent==='ISSUE'")
    assert not js("return document.getElementById('bool-new').disabled")
    js("document.getElementById('bool-new').click()")
    assert js("return document.querySelectorAll('#command-checklist input[type=checkbox]').length") == 0
    assert js("return JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith('plc-command-checklist:')))).length") == 2
    assert [w['value'] for w in state['writes']] == [1,0]


@pytest.mark.parametrize('value', [1, 0])
def test_cancel_checklist_confirmation_sends_nothing(browser, value):
    state, wd, prefix, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    button = 'bool-one' if value == 1 else 'bool-zero'
    js(f"document.getElementById('{button}').click()")
    assert js("return document.querySelectorAll('dialog[open]').length") == 1
    wd(prefix + '/actions', {'actions':[{'type':'key','id':'keyboard','actions':[
        {'type':'keyDown','value':'\ue00c'}, {'type':'keyUp','value':'\ue00c'}]}]})
    wait_for("return !document.getElementById('confirm-dialog').open")
    assert not state['writes']


def test_new_attempt_does_not_start_timer_and_completion_stops_before_clear(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser, 0)
    wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    js("document.getElementById('bool-new').click()")
    time.sleep(.3)
    assert js("return document.getElementById('bool-timer').textContent") == '00:00.0'
    assert js("return document.getElementById('bool-new').disabled")
    checklist_write(browser, 1)
    wait_for("return document.getElementById('bool-completion').textContent==='WAITING'")
    time.sleep(.3)
    state['values']['Tank01_DoorOpened'] = 1
    wait_for("return document.getElementById('bool-completion').textContent==='CONFIRMED'")
    stopped = js("return document.getElementById('bool-timer').textContent")
    time.sleep(.4)
    assert js("return document.getElementById('bool-timer').textContent") == stopped
    assert [w['value'] for w in state['writes']] == [0,1]
    assert 'send 0' in js("return document.getElementById('bool-write-hint').textContent").lower()
    checklist_write(browser, 0)
    wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    assert js("return document.getElementById('bool-timer').textContent") == stopped
    record = js("return JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith('plc-command-checklist:')))).at(-1)")
    assert record['feedback_elapsed_ms'] == record['feedbackStoppedAt'] - record['oneRequestedAt']
    assert record['oneRequestedAt'] > record['startedAt']
    assert any(e['action']=='Completion feedback: CONFIRMED' for e in record['events'])


def test_mode_off_blocks_click_and_server_rejection_does_not_lock_checklist(browser):
    state, wd, prefix, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    # Simulate a restarted backend before the next status response catches it.
    state['status_hold'] = True; state['mode'] = False
    js("document.getElementById('bool-one').click(); document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('bool-result').textContent==='BLOCKED'")
    assert not state['writes']
    assert js("return document.getElementById('bool-pending').classList.contains('hidden')")
    assert js("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    js("document.getElementById('bool-one').click()")
    assert not js("return document.getElementById('confirm-dialog').open")
    state['status_hold'] = False
    js("document.getElementById('mode-btn').click()")
    wd(prefix + '/alert/accept', {})
    wait_for("return !document.getElementById('bool-one').disabled")
    checklist_write(browser, 1)
    assert [w['value'] for w in state['writes']] == [1]


def test_status_revokes_a_stale_browser_token_before_any_command(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    state['mode'] = False
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    assert js("return document.getElementById('bool-one').disabled && document.getElementById('bool-zero').disabled")
    assert not state['writes']


def test_unknown_write_outcome_still_requires_manual_clear(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    state['write_fault'] = 'unknown'
    js("document.getElementById('bool-one').click(); document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('bool-completion').textContent==='OUTCOME UNKNOWN'")
    choose_command(browser, 'Tank01_DoorCloseRemote')
    assert js("return document.getElementById('bool-one').disabled")
    choose_command(browser, 'Tank01_DoorOpenRemote')
    assert not js("return document.getElementById('bool-zero').disabled")
    assert not state['writes']


@pytest.mark.parametrize('already_set', [False, True])
def test_feedback_cannot_pass_from_a_cached_poll_or_preexisting_state(browser, already_set):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    if already_set: state['values']['Tank01_DoorOpened'] = 1
    else: state['freeze_stamp'] = state['last_poll']
    checklist_write(browser, 1)
    state['values']['Tank01_DoorOpened'] = 1
    if already_set:
        wait_for("return document.getElementById('bool-completion').textContent==='ALREADY SET BEFORE WRITE'")
    else:
        time.sleep(.5)
        assert js("return document.getElementById('bool-completion').textContent==='WAITING'")
        state['freeze_stamp'] = None
        wait_for("return document.getElementById('bool-completion').textContent==='CONFIRMED'")


def test_historical_local_403_is_recovered_without_a_false_clear(browser):
    state, wd, prefix, js, wait_for = browser
    key = js("return Object.keys(localStorage).find(k=>k.startsWith('plc-command-checklist:'))")
    # No existing attempt means localStorage has not been written yet.
    key = key or 'plc-command-checklist:v1:MOCK:BROWSER TEST'
    old = {'id':'legacy-rejection','tag_name':'Tank01_DoorOpenRemote','address':'M300', 'startedAt':1000, 'oneRequestedAt':1000,
           'events':[{'at':'2026-10-22T08:08:55.416Z','elapsed_ms':14,'http_status':403,
                      'action':'Write 1 outcome requires review: WRITE TEST MODE is disabled or expired'}]}
    js('localStorage.setItem('+json.dumps(key)+','+json.dumps(json.dumps([old]))+')')
    url=wd(prefix+'/url');wd(prefix+'/url',{'url':url})
    wait_for("return document.querySelectorAll('[data-command-tag]').length===102")
    choose_command(browser, 'Tank01_DoorOpenRemote')
    wait_for("return document.getElementById('bool-result').textContent==='BLOCKED'")
    assert js("return document.getElementById('bool-pending').classList.contains('hidden')")
    assert not state['writes']


def test_non_door_can_be_kept_at_one_and_cleared_during_another_pending_command(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_FilterRemote')
    checklist_write(browser, 1)
    wait_for("return !document.getElementById('bool-keep').disabled")
    js("document.getElementById('bool-keep').click()")
    assert js("return document.getElementById('bool-result').textContent") == 'KEPT AT 1'
    assert js("return !document.getElementById('bool-held').classList.contains('hidden')")
    assert js("return document.getElementById('bool-pending').classList.contains('hidden')")
    assert js("return document.getElementById('bool-new').disabled")
    assert len(state['writes']) == 1
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser, 1)
    choose_command(browser, 'Tank01_FilterRemote')
    assert not js("return document.getElementById('bool-zero').disabled")
    checklist_write(browser, 0)
    wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    assert js("return document.getElementById('bool-held').classList.contains('hidden')")
    assert [w['tag_name'] for w in state['writes']] == ['Tank01_FilterRemote','Tank01_DoorOpenRemote','Tank01_FilterRemote']
    assert [w['value'] for w in state['writes']] == [1,1,0]


def test_keep_at_one_requires_new_readback_and_never_applies_to_a_door(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_FilterRemote')
    state['freeze_stamp'] = state['last_poll']
    checklist_write(browser, 1)
    time.sleep(.4)
    assert js("return document.getElementById('bool-keep').disabled")
    state['freeze_stamp'] = None
    wait_for("return !document.getElementById('bool-keep').disabled")
    js("document.getElementById('bool-keep').click()")
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser, 1)
    wait_for("return document.getElementById('bool-value').textContent==='1'")
    assert js("return document.getElementById('bool-keep').disabled")
    js("document.getElementById('bool-keep').click()")
    assert not js("return document.getElementById('bool-pending').classList.contains('hidden')")
    assert len(state['writes']) == 2


def test_an_old_read_only_status_response_does_not_revoke_new_write_mode(browser):
    _, wd, prefix, js, wait_for = browser
    js("document.getElementById('mode-btn').click()")
    wait_for("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
    js("window.originalFetch=window.fetch; window.releaseOldStatus=null; window.fetch=async function(url,opts){const response=await window.originalFetch(url,opts);if(url==='/api/status' && !window.releaseOldStatus){return new Promise(resolve=>{window.releaseOldStatus=()=>resolve(response)});}return response;}")
    wait_for("return typeof window.releaseOldStatus==='function'")
    js("document.getElementById('mode-btn').click()")
    wd(prefix+'/alert/accept',{})
    wait_for("return document.getElementById('write-banner-title').textContent==='WRITE TEST MODE ENABLED'")
    js("window.releaseOldStatus();window.fetch=window.originalFetch")
    time.sleep(.3)
    assert js("return document.getElementById('write-banner-title').textContent==='WRITE TEST MODE ENABLED'")


def test_notes_before_first_send_survive_selection_and_reload_without_starting_timer(browser):
    state, wd, prefix, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    js("document.getElementById('bool-notes').value='Expected door opening; no command sent yet.';document.getElementById('bool-notes').dispatchEvent(new Event('input'))")
    choose_command(browser, 'Tank01_DoorCloseRemote')
    choose_command(browser, 'Tank01_DoorOpenRemote')
    assert js("return document.getElementById('bool-notes').value") == 'Expected door opening; no command sent yet.'
    url=wd(prefix+'/url');wd(prefix+'/url',{'url':url})
    wait_for("return document.querySelectorAll('[data-command-tag]').length===102")
    choose_command(browser, 'Tank01_DoorOpenRemote')
    wait_for("return document.getElementById('bool-notes').value==='Expected door opening; no command sent yet.'")
    assert js("return document.getElementById('bool-notes').value") == 'Expected door opening; no command sent yet.'
    assert js("return document.getElementById('bool-timer').textContent") == '00:00.0'
    assert not state['writes']


def test_pre_dispatch_read_failure_does_not_require_clear_and_can_be_retried(browser):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    state['write_fault']='before_dispatch'
    js("document.getElementById('bool-one').click();document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('bool-result').textContent==='BLOCKED'")
    assert js("return document.getElementById('bool-pending').classList.contains('hidden')")
    assert not state['writes']
    state['write_fault']=None
    checklist_write(browser,1)
    assert [w['value'] for w in state['writes']] == [1]


@pytest.mark.parametrize('outcome',['accepted','blocked','unknown'])
def test_completion_during_a_clear_request_cannot_be_falsely_confirmed(browser,outcome):
    state, _, _, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser,1)
    state['clear_hold']=True;state['clear_outcome']=outcome
    js("document.getElementById('bool-zero').click();document.getElementById('confirm-yes').click()")
    assert state['clear_entered'].wait(2)
    state['values']['Tank01_DoorOpened']=1
    wait_for("return document.getElementById('bool-feedback').textContent.includes('Tank01_DoorOpened = 1')")
    assert js("return document.getElementById('bool-completion').textContent") != 'CONFIRMED'
    state['clear_release'].set()
    expected={'accepted':'CLEARED BEFORE COMPLETION','blocked':'CONFIRMED','unknown':'CLEAR OUTCOME UNKNOWN'}[outcome]
    wait_for("return document.getElementById('bool-completion').textContent==="+json.dumps(expected))
    record=js("return JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith('plc-command-checklist:')))).at(-1)")
    if outcome != 'blocked': assert record.get('feedback_elapsed_ms') is None
    assert [w['value'] for w in state['writes']] == ([1,0] if outcome=='accepted' else [1])


@pytest.mark.parametrize('inflight,expected',[('SENDING','OUTCOME UNKNOWN'),('CLEARING','CLEAR OUTCOME UNKNOWN'),('WAITING','MONITORING INTERRUPTED')])
def test_reload_recovers_an_unfinished_transport_without_auto_sending(browser,inflight,expected):
    state, wd, prefix, js, wait_for=browser
    record={'id':'interrupted-request','tag_name':'Tank01_DoorOpenRemote','address':'M300','startedAt':1000,'oneRequestedAt':1000,
            'oneAcceptedAt':1001 if inflight in ('CLEARING','WAITING') else None,'feedbackState':inflight,'events':[]}
    js("localStorage.setItem('plc-command-checklist:v1:MOCK:BROWSER TEST',"+json.dumps(json.dumps([record]))+")")
    url=wd(prefix+'/url');wd(prefix+'/url',{'url':url})
    wait_for("return document.querySelectorAll('[data-command-tag]').length===102")
    choose_command(browser,'Tank01_DoorOpenRemote')
    wait_for("return document.getElementById('bool-completion').textContent==="+json.dumps(expected))
    assert js("return !document.getElementById('bool-pending').classList.contains('hidden')")
    assert js("return document.getElementById('bool-timer').textContent") == '—'
    assert not state['writes']


@pytest.mark.parametrize('completed_while_closed', [False, True])
def test_reloading_waiting_feedback_interrupts_timing_but_preserves_manual_clear(browser, completed_while_closed):
    state, wd, prefix, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser, 1)
    wait_for("return document.getElementById('bool-completion').textContent==='WAITING'")
    url = wd(prefix + '/url')
    wd(prefix + '/url', {'url':'about:blank'})
    if completed_while_closed:
        state['values']['Tank01_DoorOpened'] = 1
    wd(prefix + '/url', {'url':url})
    wait_for("return document.querySelectorAll('[data-command-tag]').length===102 && document.getElementById('freshness').textContent==='FRESH'")
    choose_command(browser, 'Tank01_DoorOpenRemote')
    assert js("return document.getElementById('bool-completion').textContent") == 'MONITORING INTERRUPTED'
    assert js("return document.getElementById('bool-timer').textContent") == '—'
    assert js("return document.getElementById('write-banner-title').textContent") == 'READ-ONLY MODE'
    assert js("return !document.getElementById('bool-pending').classList.contains('hidden')")
    assert js("return document.getElementById('bool-one').disabled && document.getElementById('bool-zero').disabled")
    state['values']['Tank01_DoorOpened'] = 1
    wait_for("return document.getElementById('bool-feedback').textContent.includes('Tank01_DoorOpened = 1')")
    assert js("return document.getElementById('bool-completion').textContent") == 'MONITORING INTERRUPTED'
    record = js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST')).at(-1)")
    assert record.get('feedback_elapsed_ms') is None
    assert any(e['action'] == 'Completion feedback: MONITORING INTERRUPTED' for e in record['events'])
    assert [w['value'] for w in state['writes']] == [1]
    js("document.getElementById('mode-btn').click()")
    wd(prefix + '/alert/accept', {})
    wait_for("return !document.getElementById('bool-zero').disabled")
    checklist_write(browser, 0)
    wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    assert js("return document.getElementById('bool-completion').textContent") == 'MONITORING INTERRUPTED'
    assert [w['value'] for w in state['writes']] == [1, 0]


def test_reloading_preserves_previously_observed_completion_timing(browser):
    state, wd, prefix, js, wait_for = browser
    choose_command(browser, 'Tank01_DoorOpenRemote')
    checklist_write(browser, 1)
    state['values']['Tank01_DoorOpened'] = 1
    wait_for("return document.getElementById('bool-completion').textContent==='CONFIRMED'")
    before = js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST')).at(-1)")
    url = wd(prefix + '/url')
    wd(prefix + '/url', {'url':url})
    wait_for("return document.querySelectorAll('[data-command-tag]').length===102 && document.getElementById('freshness').textContent==='FRESH'")
    choose_command(browser, 'Tank01_DoorOpenRemote')
    assert js("return document.getElementById('bool-completion').textContent") == 'CONFIRMED'
    after = js("return JSON.parse(localStorage.getItem('plc-command-checklist:v1:MOCK:BROWSER TEST')).at(-1)")
    assert after['feedback_elapsed_ms'] == before['feedback_elapsed_ms']
    assert after['feedbackStoppedAt'] == before['feedbackStoppedAt']
    assert after['events'] == before['events']
    assert [w['value'] for w in state['writes']] == [1]


@pytest.mark.parametrize('value',[1,0])
@pytest.mark.parametrize('missing_baseline',[False,True])
def test_readback_requires_final_backend_snapshot_not_frontend_snapshot(browser,value,missing_baseline):
    state, _, _, js, wait_for=browser
    choose_command(browser,'Tank01_FilterRemote')
    if value==0: checklist_write(browser,1)
    state['validation_advance']=True;state['omit_baseline']=missing_baseline
    checklist_write(browser,value)
    stamp=state['freeze_stamp']
    wait_for("return document.getElementById('poll-time').textContent===new Date("+json.dumps(stamp)+").toLocaleString()")
    time.sleep(.4)
    if value==1:
        assert js("return document.getElementById('bool-keep').disabled")
    else:
        assert not js("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    state['freeze_stamp']=(datetime.fromisoformat(stamp)+timedelta(milliseconds=1)).isoformat()
    if missing_baseline:
        time.sleep(.5)
        assert 'final pre-write timestamp' in js("return document.getElementById('bool-write-hint').textContent")
        if value==1: assert js("return document.getElementById('bool-keep').disabled")
        else: assert not js("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    elif value==1:
        wait_for("return !document.getElementById('bool-keep').disabled")
    else:
        wait_for("return document.getElementById('bool-read-zero').dataset.verified==='true'")
    assert [w['value'] for w in state['writes']] == ([1] if value==1 else [1,0])


def manual_write(browser, name='Tank01_DoorOpenRemote', value=1):
    _, _, _, js, wait_for = browser
    js("document.querySelector('[data-nav=write]').click();document.getElementById('write-tag').value="+json.dumps(name)+";document.getElementById('write-tag').dispatchEvent(new Event('change'));document.getElementById('write-value').value="+json.dumps(str(value))+";document.getElementById('write-submit').click()")
    assert js("return document.getElementById('confirm-dialog').open")
    js("document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('write-result').textContent.includes('WRITE ')")


def manual_records(js):
    return js("return JSON.parse(localStorage.getItem('plc-value-feedback:v1:MOCK:BROWSER TEST')||'[]')")


def test_value_page_shows_all_read_signals_and_both_door_positions_without_writes(browser):
    state, _, _, js, wait_for = browser
    js("document.querySelector('[data-nav=write]').click();document.getElementById('write-tag').value='Tank01_DoorOpenRemote';document.getElementById('write-tag').dispatchEvent(new Event('change'))")
    assert js("return document.querySelectorAll('#write-feedback-table tr').length") == 221
    assert js("return document.querySelector('#write-feedback-table tr').dataset.readTag") == 'Tank01_DoorOpened'
    assert js("return [...document.querySelectorAll('[data-feedback-tag]')].map(e=>e.dataset.feedbackTag)") == ['Tank01_DoorClosed','Tank01_DoorOpened']
    state['values']['Tank01_DoorOpened'] = 1
    wait_for("return document.querySelector('[data-feedback-tag=Tank01_DoorOpened] strong').textContent==='1'")
    js("document.getElementById('write-feedback-scope').value='related';document.getElementById('write-feedback-scope').dispatchEvent(new Event('input'))")
    assert js("return [...document.querySelectorAll('#write-feedback-table tr')].every(e=>e.dataset.readTag.startsWith('Tank01_'))")
    js("document.getElementById('write-feedback-search').value='DoorClosed';document.getElementById('write-feedback-search').dispatchEvent(new Event('input'))")
    assert js("return document.querySelectorAll('#write-feedback-table tr').length") == 1
    assert not state['writes'] and not manual_records(js)


def test_value_write_records_before_and_later_door_feedback_and_exports_evidence(browser):
    state, _, _, js, wait_for = browser
    state['values']['Tank01_DoorClosed'] = 1
    manual_write(browser)
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('WAITING')")
    state['values'].update(Tank01_DoorOpened=1,Tank01_DoorClosed=0)
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('EXPECTED FEEDBACK OBSERVED')")
    record = manual_records(js)[-1]
    assert record['before']['values']['Tank01_DoorOpened'] == 0
    assert record['before']['values']['Tank01_DoorClosed'] == 1
    assert record['after']['values']['Tank01_DoorOpened'] == 1
    assert record['after']['values']['Tank01_DoorClosed'] == 0
    assert record['after']['supplier_timestamp_utc'] > record['before']['supplier_timestamp_utc']
    assert len(record['after']['values']) == 221
    for fmt in ['json','csv']:
        js("window.feedbackExport=null;URL.createObjectURL=b=>{b.text().then(t=>window.feedbackExport=t);return 'blob:test'};HTMLAnchorElement.prototype.click=function(){};document.getElementById('write-feedback-export-"+fmt+"').click()")
        wait_for('return window.feedbackExport!==null')
        content=js('return window.feedbackExport')
        if fmt=='json': assert json.loads(content)['records'][-1]['feedback'][0]['state']=='EXPECTED FEEDBACK OBSERVED'
        else: assert 'Tank01_DoorOpened' in content and 'before_timestamp_utc' in content and 'EXPECTED FEEDBACK OBSERVED' in content
    assert state['writes']==[{'tag_name':'Tank01_DoorOpenRemote','value':1}]


@pytest.mark.parametrize('missing', [False,True])
def test_value_feedback_rejects_cached_or_missing_final_baseline(browser,missing):
    state, _, _, js, wait_for = browser
    state['validation_advance']=True;state['omit_baseline']=missing
    manual_write(browser)
    state['values']['Tank01_DoorOpened']=1
    stamp=state['freeze_stamp']
    wait_for("return document.querySelector('[data-feedback-tag=Tank01_DoorOpened] strong').textContent==='1'")
    assert manual_records(js)[-1]['after'] is None
    state['freeze_stamp']=(datetime.fromisoformat(stamp)+timedelta(milliseconds=1)).isoformat()
    if missing:
        time.sleep(.5)
        assert manual_records(js)[-1]['state']=='MISSING BASELINE'
        assert manual_records(js)[-1]['after'] is None
    else:
        wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('EXPECTED FEEDBACK OBSERVED')")
    assert len(state['writes'])==1


@pytest.mark.parametrize('kind',['candidate','already_set','zero'])
def test_value_feedback_does_not_claim_unconfirmed_preexisting_or_zero_command_completion(browser,kind):
    state, _, _, js, wait_for = browser
    name='Tank01_FilterRemote' if kind=='candidate' else 'Tank01_DoorOpenRemote'
    if kind=='already_set': state['values']['Tank01_DoorOpened']=1
    manual_write(browser,name,0 if kind=='zero' else 1)
    state['values']['Tank01_FilterStatus']=1
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('READ SNAPSHOT RECORDED')")
    record=manual_records(js)[-1]
    assert all(f['state']!='EXPECTED FEEDBACK OBSERVED' for f in record['feedback'])
    if kind=='candidate': assert record['feedback'][0]['state']=='NEEDS CONFIRMATION'
    if kind=='already_set': assert record['feedback'][0]['state']=='ALREADY SET BEFORE WRITE'
    if kind=='zero': assert record['feedback']==[]


@pytest.mark.parametrize('interruption',['reload','stale'])
def test_value_feedback_interruptions_preserve_record_without_resuming_completion(browser,interruption):
    state, wd, prefix, js, wait_for=browser
    manual_write(browser)
    if interruption=='reload':
        wd(prefix+'/refresh',{})
        wait_for("return document.getElementById('write-tag').options.length>0")
        js("document.getElementById('write-tag').value='Tank01_DoorOpenRemote';document.getElementById('write-tag').dispatchEvent(new Event('change'))")
        wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('MONITORING INTERRUPTED')")
        assert js("return document.getElementById('write-banner-title').textContent")=='READ-ONLY MODE'
    else:
        state['fault']='signals_503'
        wait_for("return document.getElementById('write-feedback-health').textContent==='STALE / NO DATA'")
        state['fault']=None
    state['values']['Tank01_DoorOpened']=1
    wait_for("return document.querySelector('[data-feedback-tag=Tank01_DoorOpened] strong').textContent==='1'")
    assert manual_records(js)[-1]['state']=='MONITORING INTERRUPTED'
    wait_for("return !document.getElementById('write-feedback-capture').disabled")
    js("document.getElementById('write-feedback-capture').click()")
    assert manual_records(js)[-1]['state']=='MONITORING INTERRUPTED'
    assert manual_records(js)[-1]['after']['source']=='Operator snapshot'
    assert len(state['writes'])==1


@pytest.mark.parametrize('fault,expected',[('before_dispatch','BLOCKED BEFORE DISPATCH'),('unknown','OUTCOME UNKNOWN')])
def test_value_feedback_retains_rejected_or_uncertain_write_without_inventing_feedback(browser,fault,expected):
    state, _, _, js, wait_for=browser
    state['write_fault']=fault
    manual_write(browser)
    assert manual_records(js)[-1]['state']==expected
    assert manual_records(js)[-1]['after'] is None
    assert not state['writes']


def test_value_batch_captures_reads_for_each_command_without_promoting_candidate_mapping(browser):
    state, _, _, js, wait_for=browser
    writes=[{'tag_name':'Tank01_DoorOpenRemote','value':1},{'tag_name':'Tank01_FilterRemote','value':1}]
    js("document.querySelector('[data-nav=write]').click();document.getElementById('batch-json').value="+json.dumps(json.dumps(writes))+";document.getElementById('batch-submit').click();document.getElementById('confirm-yes').click()")
    wait_for("return document.getElementById('batch-result').textContent.startsWith('BATCH ACCEPTED')")
    assert js("return document.getElementById('write-tag').value")=='Tank01_DoorOpenRemote'
    state['values'].update(Tank01_DoorOpened=1,Tank01_FilterStatus=1)
    wait_for("return document.getElementById('write-feedback-result').textContent.startsWith('EXPECTED FEEDBACK OBSERVED')")
    record=manual_records(js)[-1]
    assert record['writes']==writes
    assert record['feedback'][1]['state']=='NEEDS CONFIRMATION'
    js("document.getElementById('write-tag').value='Tank01_FilterRemote';document.getElementById('write-tag').dispatchEvent(new Event('change'))")
    assert 'Tank01_FilterStatus: NEEDS CONFIRMATION' in js("return document.getElementById('write-feedback-result').textContent")
    assert len(state['writes'])==1


def test_value_numeric_reading_can_be_captured_later_without_another_write(browser):
    state, _, _, js, wait_for=browser
    manual_write(browser,'Tank01_TempSV',25)
    wait_for("return !document.getElementById('write-feedback-capture').disabled")
    state['values']['Tank01_TempPV']=24.5
    wait_for("return document.querySelector('[data-read-tag=Tank01_TempPV] td:nth-child(5)').textContent==='24.5'")
    assert manual_records(js)[-1]['after']['values']['Tank01_TempPV']==0
    js("document.getElementById('write-feedback-capture').click()")
    record=manual_records(js)[-1]
    assert record['after']['values']['Tank01_TempPV']==24.5
    assert record['after']['source']=='Operator snapshot'
    assert record['state']=='READ SNAPSHOT RECORDED'
    assert record['feedback']==[]
    assert state['writes']==[{'tag_name':'Tank01_TempSV','value':25}]
