import asyncio
from pathlib import Path
import pytest
from server.config import ROOT
from server.log_service import LogService
from server.plc_client import MockPLCClient
from server.signal_service import SignalService
from server.models import ValidationError

def make_service(tmp_path):
    client = MockPLCClient(ROOT / 'config/mock-tags.json')
    logs = LogService(tmp_path / 'events.jsonl', 'private-secret')
    return client, SignalService(client, logs, 3000), logs

def test_mock_catalog_and_read(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        tags = await service.load_tags()
        poll = await service.read()
        assert len(tags) == 361
        assert poll['tags_ok'] == len(tags) and poll['tags_failed'] == 0
        assert service.fresh() and service.remote()
        assert next(t for t in tags if t.tag_name == 'Tank01_TempSV').device_address == 'D4020'
    asyncio.run(run())

def test_service_blocks_read_only_and_bad_values(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        with pytest.raises(ValidationError, match='read-only'):
            await service.write('Tank01_DoorOpened', 1)
        with pytest.raises(ValidationError, match='above'):
            await service.write('Tank01_TempSV', 1000)
        with pytest.raises(ValidationError, match='Bool'):
            await service.write('Tank01_DoorOpenRemote', 2)
        assert client.values['Tank01_DoorOpenRemote'] == 0
    asyncio.run(run())

def test_mock_write_and_delayed_feedback(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        result = await service.write('Tank01_DoorOpenRemote', 1)
        assert result['written'] is True
        assert client.values['Tank01_DoorOpened'] == 0
        await asyncio.sleep(.55)
        assert (await service.read())['Tank01_DoorOpened'] == 1
        assert (await service.write('Tank01_TempSV', 25.0))['value'] == 25.0
    asyncio.run(run())

def test_remote_and_stale_fail_closed(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        client.values['Remote'] = 0
        with pytest.raises(ValidationError, match='Remote'):
            await service.write('Tank01_TempSV', 25)
        client.values['Remote'] = 1
        service.stale_ms = -1
        with pytest.raises(ValidationError, match='stale'):
            await service.write('Tank01_TempSV', 25)
    asyncio.run(run())

def test_api_key_redacted_from_log(tmp_path):
    logs = LogService(tmp_path / 'events.jsonl', 'private-secret')
    logs.add('ERROR', error='request failed private-secret', api_key='private-secret')
    assert 'private-secret' not in (tmp_path / 'events.jsonl').read_text()
    assert 'private-secret' not in logs.export('all','json')[0]

def test_null_tag_is_not_fresh_even_if_supplier_count_claims_success(tmp_path):
    async def run():
        client, service, logs = make_service(tmp_path)
        await service.load_tags()
        client.values['Tank01_DoorOpened'] = None
        await service.read()
        assert not service.fresh()
        assert 'Tank01_DoorOpened' in logs.get()[-1]['failed_tags']
        with pytest.raises(ValidationError, match='stale'):
            await service.write('Tank01_TempSV', 25)
    asyncio.run(run())
