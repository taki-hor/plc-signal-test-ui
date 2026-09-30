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
