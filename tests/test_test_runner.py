import asyncio
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
