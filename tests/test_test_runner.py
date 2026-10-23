import asyncio
import json
import pytest
from server.config import ROOT
from server.log_service import LogService
from server.plc_client import MockPLCClient
from server.signal_service import SignalService
from server.test_runner import TestRunner

def setup(tmp_path, timeout=1200):
    client = MockPLCClient(ROOT / 'config/mock-tags.json')
    logs = LogService(tmp_path / 'events.jsonl')
    service = SignalService(client, logs, 3000)
    case = {'id':'door-open','name':'Tank 01 Door Open','command_tag':'Tank01_DoorOpenRemote','command_value':1,
            'feedback_tag':'Tank01_DoorOpened','expected_feedback':1,'timeout_ms':timeout,'poll_interval_ms':50,'reset_command':None}
    return client, TestRunner(service, logs, [case]), logs

def test_pass(tmp_path):
    async def run():
        _, runner, logs = setup(tmp_path)
        result = await runner.run('door-open')
        assert result['result'] == 'PASS' and result['actual_feedback'] == 1
        assert any(e['event'] == 'TEST_FINISH' for e in logs.get('tests'))
    asyncio.run(run())

def test_timeout(tmp_path):
    async def run():
        client, runner, _ = setup(tmp_path, timeout=100)
        result = await runner.run('door-open')
        assert result['result'] == 'TIMEOUT' and result['actual_feedback'] == 0
    asyncio.run(run())

def test_communication_failure(tmp_path):
    async def run():
        client, runner, _ = setup(tmp_path)
        client.fail_next_read = True
        result = await runner.run('door-open')
        assert result['result'] == 'COMMUNICATION ERROR'
        assert client.values['Tank01_DoorOpenRemote'] == 0
    asyncio.run(run())

def test_existing_feedback_is_blocked(tmp_path):
    async def run():
        client, runner, _ = setup(tmp_path)
        client.values['Tank01_DoorOpened'] = 1
        result = await runner.run('door-open')
        assert result['result'] == 'BLOCKED'
        assert result['write_dispatched'] is False
        assert client.values['Tank01_DoorOpenRemote'] == 0
    asyncio.run(run())

def test_supplier_unconfirmed_write_is_fail(tmp_path):
    async def run():
        client, runner, _ = setup(tmp_path)
        async def unconfirmed(tag_name, value):
            return {'tag_name': tag_name, 'value': value, 'written': False}
        client.write_signal = unconfirmed
        result = await runner.run('door-open')
        assert result['result'] == 'FAIL'
        assert result['actual_feedback'] is None
    asyncio.run(run())

@pytest.mark.parametrize('tank',[1,3,5,7,10,12,14])
def test_configured_door_open_close_pairs_pass(tmp_path,tank):
    async def run():
        client = MockPLCClient(ROOT / 'config/mock-tags.json')
        client.feedback_delay_s = 0.01
        logs = LogService(tmp_path / 'events.jsonl')
        service = SignalService(client,logs,3000)
        cases = json.loads((ROOT / 'config/test-cases.json').read_text())['tests']
        runner = TestRunner(service,logs,cases)
        for action,feedback in [('open','Opened'),('close','Closed')]:
            case = runner.cases[f'tank{tank:02d}-door-{action}']
            assert case['requires_confirmation'] is False
            assert case['feedback_tag'] == f'Tank{tank:02d}_Door{feedback}'
            result = await runner.run(case['id'])
            assert result['result'] == 'PASS' and result['actual_feedback'] == 1
        if tank == 1:
            assert client.by_name['Tank01_DoorOpenRemote']['device_address'] == 'M300'
            assert client.by_name['Tank01_DoorCloseRemote']['device_address'] == 'M301'
            assert client.by_name['Tank01_DoorOpened']['device_address'] == 'D1000.4'
            assert client.by_name['Tank01_DoorClosed']['device_address'] == 'D1000.5'
    asyncio.run(run())

def test_unconfirmed_candidates_stay_blocked(tmp_path):
    async def run():
        client, runner, _ = setup(tmp_path)
        runner.cases['door-open']['requires_confirmation'] = True
        with pytest.raises(ValueError,match='requires supplier confirmation'):
            await runner.run('door-open')
        assert client.values['Tank01_DoorOpenRemote'] == 0
    asyncio.run(run())



def test_feedback_change_in_final_validation_blocks_command(tmp_path):
    async def run():
        client, runner, _ = setup(tmp_path)
        original = client.read_signals
        reads = 0
        async def changed_before_write():
            nonlocal reads
            reads += 1
            if reads >= 2: client.values['Tank01_DoorOpened'] = 1
            return await original()
        client.read_signals = changed_before_write
        result = await runner.run('door-open')
        assert result['result'] == 'BLOCKED'
        assert client.values['Tank01_DoorOpenRemote'] == 0
    asyncio.run(run())


def test_feedback_snapshot_must_be_newer_than_command_acceptance(tmp_path):
    async def run():
        from datetime import datetime, timedelta, timezone
        client, runner, _ = setup(tmp_path)
        original = client.read_signals
        reads = 0
        async def cached_feedback():
            nonlocal reads
            reads += 1
            if reads >= 3: client.values['Tank01_DoorOpened'] = 1
            poll = await original()
            if reads == 3:
                poll['timestamp'] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
            if reads >= 4:
                poll['id'], poll['poll_count'] = 1, 1
            return poll
        client.read_signals = cached_feedback
        result = await runner.run('door-open')
        assert result['result'] == 'PASS' and reads >= 4
    asyncio.run(run())


@pytest.mark.parametrize('delay', [0.03, 1])
def test_feedback_read_cannot_pass_or_hang_past_deadline(tmp_path, delay):
    async def run():
        client, runner, _ = setup(tmp_path, timeout=10)
        original = client.read_signals
        reads = 0
        async def slow_feedback():
            nonlocal reads
            reads += 1
            if reads >= 3:
                await asyncio.sleep(delay)
                client.values['Tank01_DoorOpened'] = 1
            return await original()
        client.read_signals = slow_feedback
        result = await asyncio.wait_for(runner.run('door-open'), 0.2)
        assert result['result'] == 'TIMEOUT'
        assert result['actual_feedback'] is None
        assert not runner.lock.locked()
    asyncio.run(run())


def test_leaving_remote_during_feedback_blocks_pass(tmp_path):
    async def run():
        client, runner, _ = setup(tmp_path)
        original = client.read_signals
        reads = 0
        async def local_feedback():
            nonlocal reads
            reads += 1
            if reads >= 3:
                client.values.update(Remote=0, Local=1, Tank01_DoorOpened=1)
            return await original()
        client.read_signals = local_feedback
        result = await runner.run('door-open')
        assert result['result'] == 'BLOCKED' and 'left Remote' in result['error']
    asyncio.run(run())


def test_revocation_during_feedback_prevents_pass_and_reset(tmp_path):
    async def run():
        client, runner, _ = setup(tmp_path)
        runner.cases['door-open']['reset_command'] = {'tag_name':'Tank01_TempSV', 'value':25}
        original = client.read_signals
        reads = 0
        async def feedback():
            nonlocal reads
            reads += 1
            if reads >= 3: client.values['Tank01_DoorOpened'] = 1
            return await original()
        def authorize():
            if reads >= 3: raise ValueError('Write mode revoked')
        client.read_signals = feedback
        result = await runner.run('door-open', authorize=authorize)
        assert result['result'] == 'BLOCKED'
        assert client.values['Tank01_DoorOpenRemote'] == 1
        assert client.values['Tank01_TempSV'] == 0
    asyncio.run(run())


def candidate_setup(tmp_path, timeout=150):
    client, runner, logs = setup(tmp_path, timeout)
    case = runner.cases['door-open']
    case.update(id='candidate', name='Tank 01 Filter mapping under test', command_tag='Tank01_FilterRemote',
                feedback_tag='Tank01_FilterStatus', requires_confirmation=True)
    runner.cases = {'candidate':case}
    return client, runner, logs


def test_candidate_requires_explicit_opt_in_and_observed_is_not_pass(tmp_path):
    async def run():
        from datetime import datetime
        client, runner, logs = candidate_setup(tmp_path)
        with pytest.raises(ValueError,match='requires supplier confirmation'):
            await runner.run('candidate')
        original = client.read_signals
        reads = 0
        async def feedback():
            nonlocal reads
            reads += 1
            if reads >= 3: client.values['Tank01_FilterStatus'] = 1
            return await original()
        client.read_signals = feedback
        result = await runner.run('candidate', mapping_under_test=True, end_mode='hold')
        assert result['result'] == 'OBSERVED' and result['actual_feedback'] == 1
        assert result['mapping_under_test'] is True and result['end_mode'] == 'hold'
        assert result['command_address'] == client.by_name['Tank01_FilterRemote']['device_address']
        receipt = result['write_response']
        assert receipt['written'] is True
        assert datetime.fromisoformat(receipt['console_accepted_at']).tzinfo is not None
        assert datetime.fromisoformat(receipt['console_command_baseline_utc']) < datetime.fromisoformat(receipt['console_accepted_at'])
        assert runner.cases['candidate']['requires_confirmation'] is True
        assert client.values['Tank01_FilterRemote'] == 1
        writes = [e for e in logs.get() if e['event']=='WRITE']
        assert len(writes)==1 and writes[0]['value']==1
        events = logs.get('tests')
        assert all(e['mapping_under_test'] is True and e['end_mode']=='hold' for e in events)
        assert not any(e.get('result')=='PASS' for e in events)
    asyncio.run(run())


@pytest.mark.parametrize('kwargs', [
    {'mapping_under_test':None}, {'mapping_under_test':0}, {'mapping_under_test':1},
    {'mapping_under_test':'true'}, {'mapping_under_test':'false'}, {'mapping_under_test':[]},
    {'end_mode':None}, {'end_mode':True}, {'end_mode':[]}, {'end_mode':'auto'}, {'end_mode':'pulse'},
])
def test_invalid_test_modes_never_dispatch(tmp_path, kwargs):
    async def run():
        client, runner, logs = candidate_setup(tmp_path)
        with pytest.raises(ValueError,match='mapping_under_test must be|end_mode must be'):
            await runner.run('candidate', **kwargs)
        assert client.values['Tank01_FilterRemote']==0
        assert not any(e['event']=='WRITE' for e in logs.get())
    asyncio.run(run())


@pytest.mark.parametrize('mapping_under_test', [False, True])
def test_door_hold_is_rejected_before_dispatch(tmp_path, mapping_under_test):
    async def run():
        client, runner, _ = setup(tmp_path)
        with pytest.raises(ValueError,match='Door commands require manual0'):
            await runner.run('door-open', mapping_under_test=mapping_under_test, end_mode='hold')
        assert client.values['Tank01_DoorOpenRemote']==0
    asyncio.run(run())


def test_mapping_under_test_rejects_configured_reset_instead_of_inferring_a_cycle(tmp_path):
    async def run():
        client, runner, logs = candidate_setup(tmp_path)
        runner.cases['candidate']['reset_command'] = {'tag_name':'Tank01_FilterRemote','value':0}
        with pytest.raises(ValueError,match='do not support automatic reset'):
            await runner.run('candidate', mapping_under_test=True)
        assert client.values['Tank01_FilterRemote']==0
        assert not any(e['event']=='WRITE' for e in logs.get())
    asyncio.run(run())


@pytest.mark.parametrize('guard', ['preexisting','final_baseline','stale','remote','feedback_stale','feedback_remote','authorize'])
def test_candidate_opt_in_keeps_existing_transition_and_write_guards(tmp_path, guard):
    async def run():
        from datetime import datetime, timedelta, timezone
        client, runner, logs = candidate_setup(tmp_path)
        original = client.read_signals
        reads = 0
        async def feedback():
            nonlocal reads
            reads += 1
            if guard=='preexisting' or guard=='final_baseline' and reads>=2 or reads>=3:
                client.values['Tank01_FilterStatus']=1
            if guard=='remote' or guard=='feedback_remote' and reads>=3: client.values['Remote']=0
            poll = await original()
            if guard=='stale' or guard=='feedback_stale' and reads>=3:
                poll['timestamp']=(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat()
            return poll
        def authorize():
            if guard=='authorize' and reads>=3: raise ValueError('Write mode revoked')
        client.read_signals=feedback
        result=await runner.run('candidate', authorize=authorize, mapping_under_test=True, end_mode='hold')
        assert result['result']=='BLOCKED'
        assert result['mapping_under_test'] is True
        if guard in ('feedback_stale','feedback_remote','authorize'):
            assert client.values['Tank01_FilterRemote']==1
            assert result['write_response']['written'] is True
        else:
            assert client.values['Tank01_FilterRemote']==0
        assert not any(e['event']=='WRITE' and e['value']==0 for e in logs.get())
    asyncio.run(run())


def test_candidate_cached_feedback_waits_for_new_source_snapshot(tmp_path):
    async def run():
        client, runner, _ = candidate_setup(tmp_path)
        original=client.read_signals
        reads=0
        baseline=None
        async def feedback():
            nonlocal reads, baseline
            reads+=1
            if reads>=3: client.values['Tank01_FilterStatus']=1
            poll=await original()
            if reads==2: baseline=poll['timestamp']
            if reads==3: poll['timestamp']=baseline
            return poll
        client.read_signals=feedback
        result=await runner.run('candidate',mapping_under_test=True)
        assert result['result']=='OBSERVED' and reads>=4
    asyncio.run(run())


def test_candidate_slow_feedback_deadline_keeps_command_without_auto_clear(tmp_path):
    async def run():
        client, runner, logs = candidate_setup(tmp_path,timeout=10)
        original=client.read_signals
        reads=0
        async def feedback():
            nonlocal reads
            reads+=1
            if reads>=3: await asyncio.sleep(.1)
            return await original()
        client.read_signals=feedback
        result=await asyncio.wait_for(runner.run('candidate',mapping_under_test=True),.2)
        assert result['result']=='TIMEOUT'
        assert client.values['Tank01_FilterRemote']==1
        assert not runner.lock.locked()
        assert not any(e['event']=='WRITE' and e['value']==0 for e in logs.get())
    asyncio.run(run())


@pytest.mark.parametrize('acknowledgement',[None,[], 'raise'])
def test_acted_write_with_bad_acknowledgement_keeps_dispatch_provenance(tmp_path,acknowledgement):
    async def run():
        client, runner, logs = candidate_setup(tmp_path)
        original=client.write_signal
        async def acted_without_ack(name,value):
            await original(name,value)
            if acknowledgement=='raise': raise ValueError('Reply processing failed after the write')
            return acknowledgement
        client.write_signal=acted_without_ack
        result=await runner.run('candidate',mapping_under_test=True,end_mode='hold')
        assert client.values['Tank01_FilterRemote']==1
        assert result['write_dispatched'] is True
        assert result['result']=='COMMUNICATION ERROR'
        assert not result.get('write_response')
        assert not any(event['event']=='WRITE' and event['value']==0 for event in logs.get())
        assert not runner.lock.locked()
    asyncio.run(run())
