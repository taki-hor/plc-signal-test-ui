import asyncio
from dataclasses import replace

import httpx
import pytest

from server.config import ROOT
from server.log_service import LogService
from server.plc_client import MockPLCClient
from server.signal_service import SignalService
from server.test_runner import TestRunner


@pytest.fixture
def console(monkeypatch, tmp_path):
    from server import app as console
    logs = LogService(tmp_path / 'events.jsonl', 'mock-secret-canary')
    client = MockPLCClient(ROOT / 'config/mock-tags.json')
    service = SignalService(client, logs, 3000)
    monkeypatch.setattr(console, 'client', client)
    monkeypatch.setattr(console, 'service', service)
    monkeypatch.setattr(console, 'logs', logs)
    monkeypatch.setattr(console, 'runner', TestRunner(service, logs, console.cases))
    monkeypatch.setattr(console, 'write_tokens', {})
    monkeypatch.setattr(console, 'settings', replace(console.settings, mock_mode=True, api_key='mock-secret-canary'))
    return console


def test_startup_and_reads_do_not_write_or_expose_api_key(console):
    async def run():
        transport = httpx.ASGITransport(app=console.app, client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            for path in ['/', '/api/tags', '/api/signals', '/api/status', '/api/test/cases', '/api/logs/export']:
                response = await browser.get(path)
                assert response.status_code == 200
                assert 'mock-secret-canary' not in response.text
            status = (await browser.get('/api/status')).json()
            assert status['write_mode_default']=='OFF' and status['data_fresh']
            assert all(console.client.values[t['tag_name']]==0 for t in console.client.tags if t['read_write']=='W')
            assert not console.write_tokens
            assert not any(e['event'].startswith('WRITE') for e in console.logs.get())
            assert any(w['device_address']=='D1036' for w in status['catalog_warnings'])
    asyncio.run(run())


@pytest.mark.parametrize('guard',['mode_off','non_loopback','cross_origin','expired','remote_off','stale','read_only'])
def test_write_guards_remain_enforced(console,guard):
    async def run():
        host = '192.0.2.1' if guard=='non_loopback' else '127.0.0.1'
        transport = httpx.ASGITransport(app=console.app,client=(host,1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = 'unauthorized'
            if guard not in ('mode_off','non_loopback'):
                mode = await browser.post('/api/mode/enable')
                assert mode.status_code == 200
                token = mode.json()['write_token']
            headers = {'X-Write-Token':token}
            if guard=='cross_origin': headers['Origin']='http://untrusted.test'
            if guard=='expired': console.write_tokens[token]=0
            if guard=='remote_off': console.client.values['Remote']=0
            if guard=='stale': console.service.stale_ms=-1
            name = 'Tank01_DoorOpened' if guard=='read_only' else 'Tank01_TempAdj'
            before = console.client.values[name]
            response = await browser.post('/api/write',headers=headers,json={'tag_name':name,'value':-5.0})
            assert response.status_code == (400 if guard in ('remote_off','stale','read_only') else 403)
            assert console.client.values[name]==before
            assert response.json()['write_dispatched'] is False
    asyncio.run(run())


def test_confirmed_mode_write_negative_value_and_disable(console):
    async def run():
        transport = httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            headers = {'X-Write-Token':token}
            body = {'tag_name':'Tank01_TempAdj','value':-5.0}
            response = await browser.post('/api/write',headers=headers,json=body)
            assert response.status_code==200 and response.json()['value']==-5.0
            assert (await browser.get('/api/signals')).json()['Tank01_TempAdj']==-5.0
            response = await browser.post('/api/write/batch',headers=headers,json={'writes':[body]})
            assert response.status_code==400
            assert (await browser.post('/api/mode/disable',headers=headers)).status_code==200
            assert (await browser.post('/api/write',headers=headers,json=body)).status_code==403
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['single', 'batch', 'test'])
@pytest.mark.parametrize('revoke', ['disable', 'expire'])
def test_mode_revocation_during_validation_prevents_dispatch(console, kind, revoke):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        original = console.client.list_tags
        async def gated_tags():
            entered.set()
            await release.wait()
            return await original()
        console.client.list_tags = gated_tags
        transport = httpx.ASGITransport(app=console.app, client=('127.0.0.1', 1234))
        async with httpx.AsyncClient(transport=transport, base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            headers = {'X-Write-Token': token}
            path, body = {
                'single': ('/api/write', {'tag_name':'Tank01_TempSV', 'value':25}),
                'batch': ('/api/write/batch', {'writes':[{'tag_name':'Tank01_TempSV', 'value':25}], 'confirmation':'CONFIRM BATCH WRITE'}),
                'test': ('/api/test/run', {'id':'tank01-door-open'}),
            }[kind]
            pending = asyncio.create_task(browser.post(path, headers=headers, json=body))
            await asyncio.wait_for(entered.wait(), 1)
            if revoke == 'disable':
                assert (await browser.post('/api/mode/disable', headers=headers)).status_code == 200
            else:
                console.write_tokens[token] = 0
            release.set()
            response = await asyncio.wait_for(pending, 2)
            if kind == 'test':
                assert response.status_code == 200 and response.json()['result'] == 'BLOCKED'
            else:
                assert response.status_code == 403
            assert all(console.client.values[t['tag_name']] == 0 for t in console.client.tags if t['read_write'] == 'W')
            assert not any(e['event'] in ('WRITE', 'WRITE_BATCH') for e in console.logs.get())
    asyncio.run(run())


@pytest.mark.parametrize('first,second', [('test','single'),('test','batch'),('single','test'),('batch','single')])
def test_commands_cannot_overlap_an_active_write_or_test(console, first, second):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        original = console.client.list_tags
        async def gated_tags():
            entered.set()
            await release.wait()
            return await original()
        console.client.list_tags = gated_tags
        transport = httpx.ASGITransport(app=console.app, client=('127.0.0.1', 1234))
        async with httpx.AsyncClient(transport=transport, base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            headers = {'X-Write-Token':token}
            requests = {
                'single': ('/api/write', {'tag_name':'Tank01_TempSV','value':25}),
                'batch': ('/api/write/batch', {'writes':[{'tag_name':'Tank01_TempSV','value':25}], 'confirmation':'CONFIRM BATCH WRITE'}),
                'test': ('/api/test/run', {'id':'tank01-door-open'}),
            }
            path, body = requests[first]
            pending = asyncio.create_task(browser.post(path, headers=headers, json=body))
            await asyncio.wait_for(entered.wait(), 1)
            path, body = requests[second]
            response = await browser.post(path, headers=headers, json=body)
            assert response.status_code == 400 and 'running' in response.text
            release.set()
            assert (await asyncio.wait_for(pending, 2)).status_code == 200
            assert not console.service.command_lock.locked()
    asyncio.run(run())


@pytest.mark.parametrize('path,body', [
    ('/api/write/batch', {'writes':[{'tag_name':[], 'value':1}], 'confirmation':'CONFIRM BATCH WRITE'}),
    ('/api/test/run', {'id':[]}),
])
def test_malformed_command_identity_is_a_validation_error(console, path, body):
    async def run():
        transport = httpx.ASGITransport(app=console.app, client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            response = await browser.post(path, headers={'X-Write-Token':token}, json=body)
            assert response.status_code == 400
            assert not any(e['event'] in ('WRITE','WRITE_BATCH') for e in console.logs.get())
    asyncio.run(run())



def test_write_receipt_and_poll_times_are_comparable_utc(console):
    async def run():
        from datetime import datetime, timedelta, timezone
        from zoneinfo import ZoneInfo
        console.service.timestamp_timezone = ZoneInfo('Asia/Hong_Kong')
        console.service.timestamp_offset_seconds = 44
        original = console.client.read_signals
        async def naive_supplier_poll():
            poll = await original()
            poll['timestamp'] = (datetime.now(timezone.utc) - timedelta(seconds=44)).astimezone(ZoneInfo('Asia/Hong_Kong')).replace(tzinfo=None).isoformat()
            return poll
        console.client.read_signals = naive_supplier_poll
        transport = httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            r = await browser.post('/api/write',headers={'X-Write-Token':token},json={'tag_name':'Tank01_DoorOpenRemote','value':0})
            assert r.status_code == 200 and r.json()['written'] is True
            accepted = datetime.fromisoformat(r.json()['console_accepted_at'])
            command_baseline = datetime.fromisoformat(r.json()['console_command_baseline_utc'])
            assert command_baseline == console.service.poll_time() and command_baseline <= accepted
            poll = (await browser.get('/api/signals')).json()
            status = (await browser.get('/api/status')).json()
            stamp = datetime.fromisoformat(status['supplier_timestamp_utc'])
            assert accepted.tzinfo is not None and stamp.tzinfo is not None
            assert stamp >= accepted and status['data_fresh']
            assert status['supplier_timestamp'] == poll['timestamp']
            assert datetime.fromisoformat(poll['timestamp']).tzinfo is None
    asyncio.run(run())


def test_status_tracks_only_its_own_write_token(console):
    async def run():
        transport = httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            assert not (await browser.get('/api/status')).json()['write_mode_enabled']
            assert (await browser.get('/api/status',headers={'X-Write-Token':token})).json()['write_mode_enabled']
            console.write_tokens.clear()
            assert not (await browser.get('/api/status',headers={'X-Write-Token':token})).json()['write_mode_enabled']
    asyncio.run(run())


def test_write_feedback_baseline_is_final_read_and_only_confirmed_mapping(console):
    async def run():
        transport = httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            r = await browser.post('/api/write',headers={'X-Write-Token':token},json={'tag_name':'Tank01_DoorOpenRemote','value':1})
            baseline = r.json()['console_feedback_baseline']
            assert baseline['feedback_tag']=='Tank01_DoorOpened' and baseline['value_before']==0
            assert baseline['expected_feedback']==1
            assert baseline['supplier_timestamp_utc']==console.service.last_poll['timestamp']
            assert baseline['supplier_timestamp_utc']==r.json()['console_command_baseline_utc']
            r = await browser.post('/api/write',headers={'X-Write-Token':token},json={'tag_name':'Tank01_FilterRemote','value':1})
            assert r.json()['console_feedback_baseline'] is None
    asyncio.run(run())


@pytest.mark.parametrize('tag_name,value', [('Tank01_FilterRemote',1), ('Tank01_FilterRemote',0), ('Tank01_DoorOpenRemote',0)])
def test_write_command_baseline_uses_final_validated_poll_for_unmapped_and_zero_writes(console,tag_name,value):
    async def run():
        from datetime import datetime, timedelta, timezone
        from zoneinfo import ZoneInfo
        console.service.timestamp_timezone = ZoneInfo('Asia/Hong_Kong')
        console.service.timestamp_offset_seconds = 44
        initial = datetime.now(timezone.utc) - timedelta(seconds=1)
        final = initial + timedelta(seconds=2)
        stamps = iter([initial, final])
        original_read = console.client.read_signals
        async def advancing_supplier_poll():
            poll = await original_read()
            poll['timestamp'] = (next(stamps) - timedelta(seconds=44)).astimezone(console.service.timestamp_timezone).replace(tzinfo=None).isoformat()
            return poll
        console.client.read_signals = advancing_supplier_poll
        await console.service.load_tags()
        await console.service.read()
        assert console.service.poll_time() == initial
        dispatched_baselines = []
        original_write = console.client.write_signal
        async def capture_dispatch(tag_name,value):
            dispatched_baselines.append(console.service.poll_time().isoformat())
            return await original_write(tag_name,value)
        console.client.write_signal = capture_dispatch
        transport = httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            response = await browser.post('/api/write',headers={'X-Write-Token':token},json={'tag_name':tag_name,'value':value})
            assert response.status_code == 200 and response.json()['written'] is True
            baseline = response.json()['console_command_baseline_utc']
            assert baseline == final.isoformat() == dispatched_baselines[0]
            assert baseline != initial.isoformat()
            assert datetime.fromisoformat(baseline).tzinfo is timezone.utc
            assert response.json()['console_feedback_baseline'] is None
            assert response.json()['console_read_baseline']['supplier_timestamp_utc'] == baseline
    asyncio.run(run())


@pytest.mark.parametrize('batch', [False, True])
def test_manual_write_records_all_live_read_values_and_mapping_evidence_before_dispatch(console, batch):
    async def run():
        # The final validation read must be the source, including newly added live tags.
        template = next(t for t in console.client.tags if t['tag_name']=='Tank01_DoorOpened')
        console.client.tags.append({**template,'tag_name':'Supplier_NewFeedback','device_address':'M999'})
        console.client.values['Supplier_NewFeedback'] = 7
        console.client.values['Tank01_DoorClosed'] = 1
        expected = {t['tag_name']: console.client.values[t['tag_name']] for t in console.client.tags if t['read_write']=='R'}
        writes = [{'tag_name':'Tank01_DoorOpenRemote','value':1},{'tag_name':'Tank01_FilterRemote','value':1}] if batch else [{'tag_name':'Tank01_DoorOpenRemote','value':1}]
        transport = httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            body = {'writes':writes,'confirmation':'CONFIRM BATCH WRITE'} if batch else writes[0]
            r = await browser.post('/api/write/batch' if batch else '/api/write',headers={'X-Write-Token':token},json=body)
            assert r.status_code == 200
            data = r.json(); snapshot = data['console_read_baseline']
            assert snapshot['values'] == expected
            assert 'Tank01_DoorOpenRemote' not in snapshot['values']
            assert snapshot['supplier_timestamp_utc'] == console.service.poll_time().isoformat()
            assert data['console_accepted_at']
            assert snapshot['mappings'][0]['feedback_tag'] == 'Tank01_DoorOpened'
            assert snapshot['mappings'][0]['requires_confirmation'] is False
            if batch:
                assert data['console_batch_accepted'] is True
                assert snapshot['mappings'][1]['requires_confirmation'] is True
            assert 'mock-secret-canary' not in r.text
    asyncio.run(run())


def test_manual_read_baseline_does_not_infer_zero_feedback_or_use_writable_feedback(console):
    async def run():
        transport = httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            for value in [0,1]:
                if value == 1:
                    next(t for t in console.client.tags if t['tag_name']=='Tank01_DoorOpened')['read_write']='W'
                r = await browser.post('/api/write',headers={'X-Write-Token':token},json={'tag_name':'Tank01_DoorOpenRemote','value':value})
                assert r.status_code==200
                snapshot = r.json()['console_read_baseline']
                assert snapshot['mappings']==[]
                if value == 1: assert 'Tank01_DoorOpened' not in snapshot['values']
    asyncio.run(run())


@pytest.mark.parametrize('result', [{'writes':[]}, {'writes':[{'tag_name':'Tank01_TempSV','value':25,'written':False}]}, {'writes':[{'tag_name':'Tank01_TempSV','value':99,'written':True}]}])
def test_batch_missing_rejected_or_mismatched_receipt_is_not_confirmed(console,result):
    async def run():
        async def incomplete(writes): return result
        console.client.write_batch = incomplete
        transport=httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token=(await browser.post('/api/mode/enable')).json()['write_token']
            r=await browser.post('/api/write/batch',headers={'X-Write-Token':token},json={'writes':[{'tag_name':'Tank01_TempSV','value':25}],'confirmation':'CONFIRM BATCH WRITE'})
            assert r.status_code==200 and r.json()['console_batch_accepted'] is False
            assert r.json()['console_accepted_at'] is None
    asyncio.run(run())


@pytest.mark.parametrize('batch',[False,True])
@pytest.mark.parametrize('phase',['tags','read','dispatch'])
def test_supplier_failure_before_dispatch_is_distinct_from_unknown_write(console,batch,phase):
    from server.plc_client import PLCError
    async def run():
        async def fail(*args):
            if phase=='dispatch': console.client.values['Tank01_TempSV']=25
            raise PLCError(503,'Injected supplier failure')
        setattr(console.client,{'tags':'list_tags','read':'read_signals','dispatch':'write_batch' if batch else 'write_signal'}[phase],fail)
        transport=httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token=(await browser.post('/api/mode/enable')).json()['write_token']
            body={'tag_name':'Tank01_TempSV','value':25}
            if batch: body={'writes':[body],'confirmation':'CONFIRM BATCH WRITE'}
            r=await browser.post('/api/write/batch' if batch else '/api/write',headers={'X-Write-Token':token},json=body)
            assert r.status_code==503
            if phase=='dispatch':
                assert r.json().get('write_dispatched') is not False
                assert console.client.values['Tank01_TempSV']==25
            else:
                assert r.json().get('write_dispatched') is False
                assert console.client.values['Tank01_TempSV']==0
    asyncio.run(run())


def test_candidate_endpoint_opt_in_records_observation_without_promoting_configuration(console):
    async def run():
        candidate=console.runner.cases['tank01-filterremote'].copy()
        candidate['timeout_ms']=150
        console.runner.cases[candidate['id']]=candidate
        original=console.client.read_signals
        reads=0
        async def feedback():
            nonlocal reads
            reads+=1
            if reads>=3: console.client.values['Tank01_FilterStatus']=1
            return await original()
        console.client.read_signals=feedback
        transport=httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token=(await browser.post('/api/mode/enable')).json()['write_token']
            headers={'X-Write-Token':token}
            rejected=await browser.post('/api/test/run',headers=headers,json={'id':candidate['id']})
            assert rejected.status_code==400
            response=await browser.post('/api/test/run',headers=headers,json={'id':candidate['id'],'mapping_under_test':True,'end_mode':'hold'})
            assert response.status_code==200
            result=response.json()
            assert result['result']=='OBSERVED' and result['mapping_under_test'] is True and result['end_mode']=='hold'
            assert result['write_response']['console_accepted_at']
            assert result['write_response']['console_command_baseline_utc']
            assert result['command_address']==console.client.by_name['Tank01_FilterRemote']['device_address']
            assert candidate['requires_confirmation'] is True
            assert next(c for c in (await browser.get('/api/test/cases')).json()['tests'] if c['id']==candidate['id'])['requires_confirmation'] is True
            assert console.client.values['Tank01_FilterRemote']==1
    asyncio.run(run())


@pytest.mark.parametrize('options', [
    {'mapping_under_test':'true'}, {'mapping_under_test':1}, {'mapping_under_test':None},
    {'mapping_under_test':True,'end_mode':'auto'}, {'mapping_under_test':True,'end_mode':None},
    {'mapping_under_test':True,'end_mode':True}, {'mapping_under_test':True,'end_mode':[]},
    {'mapping_under_test':True,'end_mode':'hold'},
])
def test_test_endpoint_rejects_invalid_modes_before_writing(console, options):
    async def run():
        transport=httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token=(await browser.post('/api/mode/enable')).json()['write_token']
            response=await browser.post('/api/test/run',headers={'X-Write-Token':token},json={'id':'tank01-door-open',**options})
            assert response.status_code==400
            assert console.client.values['Tank01_DoorOpenRemote']==0
            assert not any(e['event']=='WRITE' for e in console.logs.get())
    asyncio.run(run())
