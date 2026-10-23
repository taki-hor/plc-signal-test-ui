"""Independent feedback waits use mock clients only; no line API is contacted."""
import asyncio
import json
from contextlib import asynccontextmanager

import pytest

from server.config import ROOT
from server.log_service import LogService
from server.models import ValidationError
from server.plc_client import MockPLCClient, PLCError
from server.signal_service import SignalService
from server.test_runner import TestRunner


def setup_parallel(tmp_path):
    client = MockPLCClient(ROOT / 'config/mock-tags.json')
    client.feedback_delay_s = 3600
    logs = LogService(tmp_path / 'events.jsonl')
    service = SignalService(client, logs, 3000)
    cases = [{**case, 'timeout_ms':300, 'poll_interval_ms':5} for case in
             json.loads((ROOT / 'config/test-cases.json').read_text())['tests']]
    return client, service, TestRunner(service, logs, cases), logs


@asynccontextmanager
async def waiting(service, runner, case_id):
    case = runner.cases[case_id]
    task = asyncio.create_task(runner.run(case_id, mapping_under_test=case['requires_confirmation']))
    try:
        for _ in range(1000):
            await asyncio.sleep(.001)
            if task.done():
                raise AssertionError(f'Test finished before feedback wait: {task.result()}')
            if any(run['case_id']==case_id for run in service.active_tests.values()) and not service.command_lock.locked():
                break
        else: raise AssertionError('Feedback wait did not start')
        yield task
    finally:
        if not task.done(): task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_independent_tests_finish_out_of_order_with_distinct_results_and_audit_ids(tmp_path):
    async def run():
        client, service, runner, logs = setup_parallel(tmp_path)
        async with waiting(service, runner, 'tank01-filterremote') as first:
            async with waiting(service, runner, 'tank01-heaterremote') as second:
                assert len(service.active_tests)==2 and not service.command_lock.locked()
                client.values['Tank01_HeaterStatus']=1
                second_result=await asyncio.wait_for(second, .2)
                assert second_result['result']=='OBSERVED' and not first.done()
                first_result=await first
                assert first_result['result']=='TIMEOUT'
                assert first_result['run_id']!=second_result['run_id']
                for result in (first_result,second_result):
                    entries=[e for e in logs.get('tests') if e.get('run_id')==result['run_id']]
                    assert entries[0]['event']=='TEST_START' and entries[-1]['event']=='TEST_FINISH'
                    assert all(e['test_name']==result['test_name'] for e in entries)
        assert not service.active_tests and not service.command_lock.locked()
        assert not any(e['event']=='WRITE' and e['value']==0 for e in logs.get())
    asyncio.run(run())


@pytest.mark.parametrize('batch',[False,True])
def test_unrelated_manual_write_is_allowed_during_feedback_wait(tmp_path,batch):
    async def run():
        client, service, runner, _ = setup_parallel(tmp_path)
        async with waiting(service, runner, 'tank01-filterremote') as first:
            async with service.command_lock:
                if batch: await service.write_batch([{'tag_name':'Tank01_TempSV','value':25}])
                else: await service.write('Tank01_TempSV',25)
            assert client.values['Tank01_TempSV']==25 and not first.done()
            client.values['Tank01_FilterStatus']=1
            assert (await first)['result']=='OBSERVED'
    asyncio.run(run())


@pytest.mark.parametrize('conflict',['same_command','address_alias','shared_feedback','feedback_address_alias','opposed_door'])
def test_conflicting_test_never_dispatches_while_other_feedback_waits(tmp_path,conflict):
    async def run():
        client, service, runner, logs = setup_parallel(tmp_path)
        first_id,second_id='tank01-filterremote','tank01-heaterremote'
        if conflict=='same_command':
            second_id=first_id
        elif conflict=='address_alias':
            client.by_name['Tank01_HeaterRemote']['device_address']=client.by_name['Tank01_FilterRemote']['device_address']
        elif conflict=='shared_feedback':
            runner.cases[second_id]['feedback_tag']='Tank01_FilterStatus'
        elif conflict=='feedback_address_alias':
            client.by_name['Tank01_HeaterStatus']['device_address']=client.by_name['Tank01_FilterStatus']['device_address']
        else:
            first_id,second_id='tank01-door-open','tank01-door-close'
            client.values['Tank01_DoorClosed']=0
        async with waiting(service, runner, first_id) as first:
            result=await runner.run(second_id,mapping_under_test=runner.cases[second_id]['requires_confirmation'])
            assert result['result']=='BLOCKED' and result['write_dispatched'] is False
            assert 'conflicts with active feedback test' in result['error']
            assert not first.done()
            assert len([e for e in logs.get() if e['event']=='WRITE'])==1
    asyncio.run(run())


@pytest.mark.parametrize('batch',[False,True])
@pytest.mark.parametrize('conflict',['same_command','address_alias','opposed_door'])
def test_conflicting_manual_nonzero_write_is_rejected_atomically(tmp_path,batch,conflict):
    async def run():
        client, service, runner, logs = setup_parallel(tmp_path)
        first_id,name='tank01-filterremote','Tank01_FilterRemote'
        if conflict=='address_alias':
            name='Tank01_HeaterRemote'
            client.by_name[name]['device_address']=client.by_name['Tank01_FilterRemote']['device_address']
        elif conflict=='opposed_door':
            first_id,name='tank01-door-open','Tank01_DoorCloseRemote'
        async with waiting(service, runner, first_id):
            with pytest.raises(ValidationError,match='conflicts with active feedback test'):
                async with service.command_lock:
                    if batch:
                        await service.write_batch([{'tag_name':'Tank01_TempSV','value':25},{'tag_name':name,'value':1}])
                    else: await service.write(name,1)
            assert client.values['Tank01_TempSV']==0
            assert len([e for e in logs.get() if e['event']=='WRITE'])==1
    asyncio.run(run())


@pytest.mark.parametrize('batch',[False,True])
def test_clear_interrupts_a_hung_feedback_read_without_awarding_late_pass(tmp_path,batch):
    async def run():
        client, service, runner, logs = setup_parallel(tmp_path)
        entered,release=asyncio.Event(),asyncio.Event()
        original=client.read_signals
        async def gated_observer_read():
            if asyncio.current_task().get_coro().__qualname__=='SignalService.read':
                entered.set()
                await release.wait()
                client.values['Tank01_FilterStatus']=1
            return await original()
        client.read_signals=gated_observer_read
        async with waiting(service, runner, 'tank01-filterremote') as first:
            await asyncio.wait_for(entered.wait(), .2)
            async with service.command_lock:
                if batch: await service.write_batch([{'tag_name':'Tank01_FilterRemote','value':0}])
                else: await service.write('Tank01_FilterRemote',0)
            result=await asyncio.wait_for(first,.2)
            assert result['result']=='INTERRUPTED' and result['write_response']['written'] is True
            assert result['write_dispatched'] is True and 'manually cleared' in result['error']
            assert client.values['Tank01_FilterRemote']==0
            assert not release.is_set() and not service.active_tests
            assert not any(e.get('result') in ('PASS','OBSERVED') for e in logs.get('tests'))
    asyncio.run(run())


def test_blocked_clear_does_not_interrupt_the_existing_observer(tmp_path):
    async def run():
        client, service, runner, _ = setup_parallel(tmp_path)
        def rejected(): raise ValueError('Clear authority revoked before dispatch')
        async with waiting(service, runner, 'tank01-filterremote') as first:
            with pytest.raises(ValueError) as blocked:
                async with service.command_lock:
                    await service.write('Tank01_FilterRemote',0,authorize=rejected)
            assert blocked.value.write_dispatched is False
            assert all(not active['interrupted'].is_set() for active in service.active_tests.values())
            assert client.values['Tank01_FilterRemote']==1
            client.values['Tank01_FilterStatus']=1
            assert (await first)['result']=='OBSERVED'
    asyncio.run(run())


def test_uncertain_clear_still_interrupts_at_the_transport_boundary(tmp_path):
    async def run():
        client, service, runner, _ = setup_parallel(tmp_path)
        original=client.write_signal
        async def bad_clear(name,value):
            result=await original(name,value)
            return None if value==0 else result
        client.write_signal=bad_clear
        async with waiting(service, runner, 'tank01-filterremote') as first:
            with pytest.raises(PLCError) as failure:
                async with service.command_lock:
                    await service.write('Tank01_FilterRemote',0)
            assert failure.value.write_dispatched is True
            assert (await asyncio.wait_for(first,.2))['result']=='INTERRUPTED'
    asyncio.run(run())


@pytest.mark.parametrize('name',['Tank01_FilterRemote','Tank01_FilterStatus'])
def test_metadata_remap_during_observation_cannot_award_a_match(tmp_path,name):
    async def run():
        client, service, runner, _ = setup_parallel(tmp_path)
        async with waiting(service, runner, 'tank01-filterremote') as first:
            client.by_name[name]['device_address']='M999' if name.endswith('Remote') else 'D999.0'
            await service.load_tags()
            client.values['Tank01_FilterStatus']=1
            result=await first
            assert result['result']=='BLOCKED' and 'metadata changed' in result['error']
            assert result['write_response']['written'] is True
    asyncio.run(run())


def test_configured_reset_case_remains_exclusive_and_manual_clear_skips_reset(tmp_path):
    async def run():
        client, service, runner, logs = setup_parallel(tmp_path)
        runner.cases['tank01-door-open']['reset_command']={'tag_name':'Tank01_TempSV','value':25}
        async with waiting(service, runner, 'tank01-door-open') as first:
            with pytest.raises(ValidationError):
                async with service.command_lock: await service.write('Tank01_TempAdj',-5)
            result=await runner.run('tank03-door-open')
            assert result['result']=='BLOCKED' and result['write_dispatched'] is False
            async with service.command_lock: await service.write('Tank01_DoorOpenRemote',0)
            assert (await first)['result']=='INTERRUPTED'
            assert client.values['Tank01_TempSV']==0
            assert not any(e['event']=='WRITE' and e['tag_name']=='Tank01_TempSV' for e in logs.get())
    asyncio.run(run())


def test_cancelling_one_observer_releases_only_its_reservation_without_clearing(tmp_path):
    async def run():
        client, service, runner, _ = setup_parallel(tmp_path)
        async with waiting(service, runner, 'tank01-filterremote') as first:
            async with waiting(service, runner, 'tank01-heaterremote') as second:
                first.cancel()
                with pytest.raises(asyncio.CancelledError): await first
                assert [run['case_id'] for run in service.active_tests.values()]==['tank01-heaterremote']
                assert client.values['Tank01_FilterRemote']==1 and not second.done()
                client.values['Tank01_HeaterStatus']=1
                assert (await second)['result']=='OBSERVED'
        assert not service.active_tests and not service.command_lock.locked()
    asyncio.run(run())


from test_app_safety import console


@pytest.mark.parametrize('action',['unrelated_single','unrelated_batch','same_nonzero','opposed_door','clear_single','clear_batch'])
def test_http_write_routes_share_observation_guards_without_holding_dispatch_lock(console,action):
    async def run():
        import httpx
        console.client.feedback_delay_s=3600
        console.client.values['Tank01_DoorClosed']=0
        console.runner.cases['tank01-door-open']={**console.runner.cases['tank01-door-open'],'timeout_ms':300}
        transport=httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token=(await browser.post('/api/mode/enable')).json()['write_token']
            headers={'X-Write-Token':token}
            first=asyncio.create_task(browser.post('/api/test/run',headers=headers,json={'id':'tank01-door-open'}))
            try:
                for _ in range(1000):
                    await asyncio.sleep(.001)
                    if console.service.active_tests and not console.service.command_lock.locked(): break
                    assert not first.done()
                else: raise AssertionError('HTTP test did not reach observation')
                paths={
                    'unrelated_single':('/api/write',{'tag_name':'Tank01_TempSV','value':25}),
                    'unrelated_batch':('/api/write/batch',{'writes':[{'tag_name':'Tank01_TempSV','value':25}],'confirmation':'CONFIRM BATCH WRITE'}),
                    'same_nonzero':('/api/write',{'tag_name':'Tank01_DoorOpenRemote','value':1}),
                    'opposed_door':('/api/write',{'tag_name':'Tank01_DoorCloseRemote','value':1}),
                    'clear_single':('/api/write',{'tag_name':'Tank01_DoorOpenRemote','value':0}),
                    'clear_batch':('/api/write/batch',{'writes':[{'tag_name':'Tank01_DoorOpenRemote','value':0}],'confirmation':'CONFIRM BATCH WRITE'}),
                }
                path,body=paths[action]
                reply=await browser.post(path,headers=headers,json=body)
                if action in ('same_nonzero','opposed_door'):
                    assert reply.status_code==400 and reply.json()['write_dispatched'] is False
                    assert not first.done()
                else: assert reply.status_code==200
                if action.startswith('clear'):
                    result=(await asyncio.wait_for(first,.2)).json()
                    assert result['result']=='INTERRUPTED' and result['write_response']['written'] is True
                else:
                    if action.startswith('unrelated'): assert console.client.values['Tank01_TempSV']==25
                    assert not first.done()
                    console.client.values['Tank01_DoorOpened']=1
                    result=(await first).json()
                    assert result['result']=='PASS'
                assert result['run_id'] and not console.service.active_tests
            finally:
                if not first.done(): first.cancel()
                await asyncio.gather(first,return_exceptions=True)
    asyncio.run(run())


@pytest.mark.parametrize('own_snapshot',['failed_tags','missing_tag','local','stale'])
def test_observer_validates_its_own_snapshot_when_another_read_replaced_latest(tmp_path,own_snapshot):
    async def run():
        from datetime import datetime,timedelta,timezone
        client, service, runner, _ = setup_parallel(tmp_path)
        original=service.read
        async def own_poll_with_healthy_shared_latest():
            poll=await original()
            if asyncio.current_task().get_coro().__qualname__==own_poll_with_healthy_shared_latest.__qualname__:
                poll={**poll,'Tank01_FilterStatus':1}
                # Another monitor may update shared latest state before this observer resumes.
                service.last_poll={**poll,'Remote':1,'tags_failed':0}
                if own_snapshot=='failed_tags': poll['tags_failed']=1
                elif own_snapshot=='missing_tag': poll.pop('Tank01_TempPV')
                elif own_snapshot=='local': poll['Remote']=0
                else: poll['timestamp']=(datetime.now(timezone.utc)-timedelta(seconds=10)).isoformat()
            return poll
        service.read=own_poll_with_healthy_shared_latest
        result=await runner.run('tank01-filterremote',mapping_under_test=True)
        assert result['result']=='BLOCKED'
        assert ('left Remote' if own_snapshot=='local' else 'stale or incomplete') in result['error']
        assert service.fresh() and service.remote()
        assert not service.active_tests and not service.command_lock.locked()
    asyncio.run(run())


@pytest.mark.parametrize('snapshot',[{}, {'Remote':1}])
def test_explicit_missing_snapshot_never_uses_healthy_global_fallback(tmp_path,snapshot):
    async def run():
        _, service, _, _ = setup_parallel(tmp_path)
        await service.load_tags()
        await service.read()
        assert service.fresh() and service.remote()
        assert service.age_ms(snapshot) is None and not service.fresh(snapshot)
        assert service.remote(snapshot) is bool(snapshot.get('Remote')==1)
    asyncio.run(run())
