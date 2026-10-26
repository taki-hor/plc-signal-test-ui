"""API-check evidence is exercised only with an in-memory PLC client."""
import asyncio
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import json

import pytest

from server.api_checks import APIChecks
from server.config import ROOT
from server.log_service import LogService
from server.plc_client import MockPLCClient
from server.signal_service import SignalService


def setup(tmp_path):
    client=MockPLCClient(ROOT/'config/mock-tags.json')
    logs=LogService(tmp_path/'events.jsonl','test-secret')
    service=SignalService(client,logs,3000)
    cases=json.loads((ROOT/'config/test-cases.json').read_text())['tests']
    service.api_checks=APIChecks(tmp_path/'checks.json',logs,'MOCK','MOCK',cases)
    return client,service


def row(service,name):
    return next(item for item in service.api_checks.public(service)['records'] if item['tag_name']==name)


@pytest.mark.parametrize('batch',[False,True])
def test_checked_requires_fresh_one_status_and_restored_zero_and_survives_restart(tmp_path,batch):
    async def run():
        client,service=setup(tmp_path);name='Tank01_FilterRemote';feedback='Tank01_FilterStatus'
        async def write(value):
            if batch:return await service.write_batch([{'tag_name':name,'value':value}])
            return await service.write(name,value)
        await write(1)
        assert row(service,name)['api_status']=='unchecked'
        client.values[feedback]=1;await service.read()
        assert row(service,name)['api_status']=='unchecked'
        await write(0)
        client.values[feedback]=0;await service.read()
        result=row(service,name)
        assert result['api_status']=='checked' and not result['pending']
        assert 'operator' not in json.dumps(result)
        service.api_checks=APIChecks(tmp_path/'checks.json',service.logs,'MOCK','MOCK',[])
        assert row(service,name)['api_status']=='checked'
    asyncio.run(run())


def test_auto_mode_uses_own_readback_without_promoting_actuator_status(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        await service.write(name,1);await service.read()
        assert row(service,name)['api_status']=='unchecked'
        assert client.values['Tank07_CoolerStatus']==0
        await service.write(name,0);await service.read()
        result=row(service,name)
        assert result['api_status']=='checked' and result['basis']=='Command readback only'
    asyncio.run(run())


def test_missing_status_is_failed_after_clear_and_does_not_hold_command_on(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank01_FilterRemote'
        await service.write(name,1);await service.read()
        await service.write(name,0);await service.read()
        result=row(service,name)
        assert result['api_status']=='failed' and not result['pending']
        assert 'status' in result['detail'] and 'readback verified' in result['detail']
        assert result['command_one_seen'] is True
        assert client.values[name]==0
    asyncio.run(run())


def test_alias_and_preexisting_baselines_never_claim_api_checked(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank03_FillWaterAuto'
        await service.write(name,1);await service.read()
        await service.write(name,0);await service.read()
        assert row(service,name)['api_status']=='unchecked'
    asyncio.run(run())


@pytest.mark.parametrize('field,value',[('device_address','M999'),('data_type','Word'),('multiplier',0.1)])
def test_metadata_change_invalidates_historical_check(tmp_path,field,value):
    async def run():
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        await service.write(name,1);await service.read();await service.write(name,0);await service.read()
        assert row(service,name)['api_status']=='checked'
        service.tags[name]=replace(service.tags[name],**{field:value})
        assert row(service,name)['api_status']=='unchecked'
    asyncio.run(run())


def test_storage_failure_cannot_prevent_explicit_clear(tmp_path,monkeypatch):
    async def run():
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        def broken(_):raise OSError('disk unavailable')
        monkeypatch.setattr(service.api_checks,'save',broken)
        assert (await service.write(name,1))['written'] is True
        assert (await service.write(name,0))['written'] is True
        assert client.values[name]==0
        assert service.api_checks.public(service)['error']
    asyncio.run(run())


def test_restart_never_replays_or_clears_an_unfinished_write(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        await service.write(name,1);await service.read()
        service.api_checks=APIChecks(tmp_path/'checks.json',service.logs,'MOCK','MOCK',[])
        assert row(service,name)['api_status']=='failed'
        assert client.values[name]==1
    asyncio.run(run())


def test_stale_or_pre_ack_samples_do_not_qualify(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        await service.write(name,1)
        poll=dict(service.last_poll);poll[name]=1
        service.api_checks.observe(service,poll)
        assert not service.api_checks.records[service.api_checks.key(name)]['one']['observed']
        poll['timestamp']=(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat()
        service.api_checks.observe(service,poll)
        assert not service.api_checks.records[service.api_checks.key(name)]['one']['observed']
        client.values[name]=0  # No fresh read ever observed the requested 1.
        await service.write(name,0);await service.read()
        assert row(service,name)['api_status']=='failed'
    asyncio.run(run())


def test_unverified_restoration_expires_without_issuing_another_write(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank01_FilterRemote';feedback='Tank01_FilterStatus'
        await service.write(name,1);client.values[feedback]=1;await service.read();await service.write(name,0)
        record=service.api_checks.records[service.api_checks.key(name)]
        record['zero']['accepted_at']=(datetime.now(timezone.utc)-timedelta(seconds=16)).isoformat()
        await service.read()
        result=row(service,name)
        assert result['api_status']=='failed' and result['pending']
        assert client.values[name]==0 and client.values[feedback]==1
    asyncio.run(run())


def test_ambiguous_remote_local_state_cannot_qualify(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        await service.write(name,1);client.values['Local']=1;await service.read()
        assert not service.api_checks.records[service.api_checks.key(name)]['one']['observed']
        client.values[name]=0;client.values['Local']=0
        await service.write(name,0);await service.read()
        assert row(service,name)['api_status']=='failed'
    asyncio.run(run())


def test_a_checked_label_without_complete_proof_is_not_published(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        await service.write(name,1)
        record=service.api_checks.records[service.api_checks.key(name)]
        record.update(api_status='checked',pending=False)
        assert row(service,name)['api_status']=='unchecked'
    asyncio.run(run())


def test_new_attempt_keeps_prior_pass_until_a_real_new_failure(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank01_FilterRemote';feedback='Tank01_FilterStatus'
        await service.write(name,1);client.values[feedback]=1;await service.read()
        await service.write(name,0);client.values[feedback]=0;await service.read()
        previous=row(service,name)
        journal_before=(tmp_path/'events.jsonl').read_text()
        await service.write(name,1);await service.read()
        pending=row(service,name)
        assert pending['api_status']=='checked' and pending['pending'] and pending['retained_result']
        assert pending['checked_at']==previous['checked_at'] and pending['started_at']==previous['started_at']
        assert pending['current_started_at']!=previous['started_at']
        assert 'Current attempt: Awaiting' in pending['detail']
        assert (tmp_path/'events.jsonl').read_text().startswith(journal_before)
        await service.write(name,0);await service.read()
        failure=row(service,name)
        assert failure['api_status']=='failed' and not failure['pending'] and not failure['retained_result']
        assert failure['started_at']==pending['current_started_at']
        assert client.values[name]==0
    asyncio.run(run())


def test_new_attempt_keeps_prior_failure_then_new_verified_pass_supersedes_it(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank01_FilterRemote';feedback='Tank01_FilterStatus'
        await service.write(name,1);await service.read();await service.write(name,0);await service.read()
        previous=row(service,name)
        assert previous['api_status']=='failed'
        await service.write(name,1)
        pending=row(service,name)
        assert pending['api_status']=='failed' and pending['pending'] and pending['retained_result']
        assert previous['detail'] in pending['detail']
        client.values[feedback]=1;await service.read();await service.write(name,0)
        client.values[feedback]=0;await service.read()
        result=row(service,name)
        assert result['api_status']=='checked' and not result['retained_result'] and not result['pending']
    asyncio.run(run())


@pytest.mark.parametrize('changed_tag',['Tank01_FilterRemote','Tank01_FilterStatus'])
def test_retained_result_cannot_survive_command_or_feedback_metadata_change(tmp_path,changed_tag):
    async def run():
        client,service=setup(tmp_path);name='Tank01_FilterRemote';feedback='Tank01_FilterStatus'
        await service.write(name,1);client.values[feedback]=1;await service.read()
        await service.write(name,0);client.values[feedback]=0;await service.read()
        await service.write(name,1)
        assert row(service,name)['api_status']=='checked'
        service.tags[changed_tag]=replace(service.tags[changed_tag],device_address='M999')
        result=row(service,name)
        assert result['api_status']=='unchecked' and not result['retained_result']
        assert result['identity_valid'] is False
        assert 'Metadata changed' in result['detail']
    asyncio.run(run())


def test_retained_snapshot_is_bounded_and_restart_failure_stays_visible(tmp_path):
    async def run():
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        for _ in range(3):
            await service.write(name,1);await service.read();await service.write(name,0);await service.read()
        await service.write(name,1)
        stored=service.api_checks.records[service.api_checks.key(name)]
        assert 'previous_result' not in stored['previous_result']
        assert service.api_checks.complete(stored['previous_result'])
        service.api_checks=APIChecks(tmp_path/'checks.json',service.logs,'MOCK','MOCK',[])
        result=row(service,name)
        assert result['api_status']=='failed' and not result['retained_result']
        assert 'restarted' in result['detail'] and client.values[name]==1
    asyncio.run(run())


def test_check_endpoint_loads_metadata_after_restart_before_returning_saved_results(tmp_path,monkeypatch):
    async def run():
        import httpx
        from server import app as module
        client,service=setup(tmp_path);name='Tank07_CoolerAuto'
        await service.write(name,1);await service.read();await service.write(name,0);await service.read()
        restarted=SignalService(client,service.logs,3000)
        restarted.api_checks=APIChecks(tmp_path/'checks.json',service.logs,'MOCK','MOCK',[])
        assert not restarted.tags
        monkeypatch.setattr(module,'service',restarted)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test') as browser:
            response=await browser.get('/api/checks')
        assert response.status_code==200
        assert next(r for r in response.json()['records'] if r['tag_name']==name)['api_status']=='checked'
        assert restarted.tags
    asyncio.run(run())
