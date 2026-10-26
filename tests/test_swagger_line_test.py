"""All-tag runner checks use fake PLCs and HTTP transports, never the line."""
import asyncio
from dataclasses import replace
from datetime import datetime,timezone
import json
from pathlib import Path

import httpx
import pytest

from server.config import ROOT
from server.log_service import LogService
from server.plc_client import MockPLCClient, PLCError
from server.signal_service import SignalService
from tools.swagger_line_test import AppClient, SwaggerLineTest, inventory, local_origin, main, validate_number


class FakeLine(MockPLCClient):
    def __init__(self):
        super().__init__(ROOT/'config/mock-tags.json');self.writes=[];self.unknown=False;self.feedback_missing=False
        self.feedback_delay_s=0
    async def write_signal(self,name,value):
        self.writes.append((name,value))
        response=await super().write_signal(name,value)
        address=self.by_name[name]['device_address']
        for tag in self.tags:
            if tag['device_address']==address:self.values[tag['tag_name']]=value
        feedback=name[:-6]+'Status' if name.endswith('Remote') else name[:-2]+'Status' if name.endswith('On') else 'MainInletStatus' if name=='MainInlet' else None
        if feedback in self.by_name and not self.feedback_missing:
            address=self.by_name[feedback]['device_address']
            for tag in self.tags:
                if tag['device_address']==address:self.values[tag['tag_name']]=value
        if value==1 and self.unknown:raise PLCError(502,'lost acknowledgement test-secret')
        return response


def fixture(tmp_path,keys='p',answer='HOLD'):
    logs=LogService(tmp_path/'events.jsonl','test-secret');client=FakeLine();service=SignalService(client,logs,3000)
    runner=SwaggerLineTest({'direct':service},logs,tmp_path,verdict=lambda _:keys,ready=lambda _:'r',prompt=lambda _:answer,wait_seconds=.03,emit=lambda _:None)
    return client,service,runner,{case['tag_name']:case for case in inventory()['cases']}


def test_offline_full_inventory_and_physical_order(monkeypatch,capsys):
    monkeypatch.setattr('tools.swagger_line_test.PLCClient',lambda *a,**k:pytest.fail('Offline preview opened a PLC client'))
    assert main([])==0
    assert '141 writable tags' in capsys.readouterr().out
    plan=inventory();assert len(plan['cases'])==141
    assert sum(c['kind']=='numeric' for c in plan['cases'])==39
    assert sum(c['kind']=='door' for c in plan['cases'])==14
    assert plan['cases'][0]['tag_name']=='MainInlet'
    assert [c['tank'] for c in plan['cases']]==sorted(c['tank'] for c in plan['cases'])
    cases={c['tag_name']:c for c in plan['cases']}
    assert cases['Tank12_DoorOpenRemote']['tank']==13
    assert cases['Tank12_FillWaterOn']['tank']==12


def test_binary_case_separates_ack_readback_output_human_and_cleanup(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path,keys='n')
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert client.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
        assert row['request']=='acknowledged' and row['readback']=='verified'
        assert row['output']=='confirmed' and row['human_result']=='unchecked' and row['restored']
        assert row['continue_queue'] and row['physical_stop_verified'] is False
    asyncio.run(run())


def test_auto_no_movement_is_mode_only_not_a_human_pass(tmp_path):
    async def run():
        _,_,runner,cases=fixture(tmp_path,keys='n')
        row=await runner.run_path(cases['Tank07_CoolerAuto'],'direct',1,0,None)
        assert row['output']=='mode_only' and row['readback']=='verified'
        assert row['human_result']=='unchecked' and row['restored']
    asyncio.run(run())


def test_numeric_restores_original_value_instead_of_zero(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        client.values['Tank01_TempSV']=20.0
        row=await runner.run_path(cases['Tank01_TempSV'],'direct',25.2,20.0,None)
        assert client.writes==[('Tank01_TempSV',25.2),('Tank01_TempSV',20.0)]
        assert row['readback']=='verified' and row['restored'] and row['human_result']=='pass'
    asyncio.run(run())


def test_door_latched_position_can_remain_one_after_command_zero(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        row=await runner.run_path(cases['Tank01_DoorOpenRemote'],'direct',1,0,None)
        assert row['restored'] and client.values['Tank01_DoorOpenRemote']==0
        assert client.values['Tank01_DoorOpened']==1
        assert row['physical_stop_verified'] is False
    asyncio.run(run())


def test_already_set_feedback_is_not_a_new_transition(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        client.values['Tank01_DoorOpened']=1;client.values['Tank01_DoorClosed']=0
        row=await runner.run_path(cases['Tank01_DoorOpenRemote'],'direct',1,0,None)
        assert row['output']=='already_set' and row['restored']
    asyncio.run(run())


def test_missing_status_does_not_mislabel_successful_http_or_readback(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path);client.feedback_missing=True
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert row['request']=='acknowledged' and row['readback']=='verified'
        assert row['output']=='unconfirmed' and row['restored']
    asyncio.run(run())


@pytest.mark.parametrize('answer,values',[('RESTORE',[1,0]),('NO',[1])])
def test_unknown_request_never_retries_one_and_requires_cleanup_choice(tmp_path,answer,values):
    async def run():
        client,_,runner,cases=fixture(tmp_path,answer=answer);client.unknown=True
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert [value for _,value in client.writes]==values
        assert row['request']=='unknown' and not row['continue_queue']
        assert 'test-secret' not in (tmp_path/'report.json').read_text()
    asyncio.run(run())


def test_shared_addresses_require_acknowledgment_and_watch_aliases(tmp_path):
    async def run():
        client,service,runner,cases=fixture(tmp_path,answer='S')
        case=cases['Tank03_FillWaterAuto'];poll=await runner.prepare(service,case)
        value,reason=await runner.inputs(case,service,poll[case['tag_name']])
        assert value is None and reason and not client.writes
        runner.prompt=lambda _:'ALIASES'
        value,reason=await runner.inputs(case,service,poll[case['tag_name']])
        assert value==1 and reason is None
        row=await runner.run_path(case,'direct',value,0,None)
        assert row['restored'] and client.values['Tank05_FillWaterAuto']==0
        assert set(row['test_sample']['values'])=={'Tank03_FillWaterAuto','Tank05_FillWaterAuto'}
    asyncio.run(run())


def test_unexpected_alias_or_metadata_change_blocks_write(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        alias={**client.by_name['Tank01_FilterRemote'],'tag_name':'UnexpectedAlias'}
        client.tags.append(alias);client.values['UnexpectedAlias']=0
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert row['request']=='blocked' and not client.writes
    asyncio.run(run())


@pytest.mark.parametrize('condition',['local','stale','active'])
def test_bad_preflight_preserves_state_and_sends_no_write(tmp_path,condition):
    async def run():
        client,service,runner,cases=fixture(tmp_path)
        if condition=='local':client.values['Local']=1
        if condition=='stale':service.stale_ms=-1
        if condition=='active':client.values['Tank01_FilterRemote']=1
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert not client.writes and row['request']=='blocked'
    asyncio.run(run())


@pytest.mark.parametrize('value',[float('nan'),float('inf'),-1,1000,25.15])
def test_numeric_values_must_fit_pdf_envelope_and_register_representation(tmp_path,value):
    _,service,_,cases=fixture(tmp_path)
    from server.models import Tag
    case=cases['Tank01_TempSV']
    tag=Tag.parse(next(t for t in json.loads((ROOT/'config/mock-tags.json').read_text())['tags'] if t['tag_name']==case['tag_name']))
    with pytest.raises(ValueError):validate_number(tag,value,case['pdf_limits'])


def test_numeric_blank_skip_and_same_value_never_dispatch(tmp_path):
    async def run():
        client,service,runner,cases=fixture(tmp_path,answer='S')
        case=cases['Tank01_TempSV'];await runner.prepare(service,case)
        assert (await runner.inputs(case,service,0))[0] is None
        runner.prompt=lambda _:'0'
        assert 'equals baseline' in (await runner.inputs(case,service,0))[1]
        assert not client.writes
    asyncio.run(run())


@pytest.mark.parametrize('origin',['https://127.0.0.1:8080','http://localhost:8080','http://example.com','http://127.0.0.1:8080/path','http://user@127.0.0.1'])
def test_app_origin_is_literal_loopback_only(origin):
    with pytest.raises(ValueError):local_origin(origin)


def test_app_uses_only_own_token_and_same_real_target():
    async def run():
        calls=[]
        def handler(request):
            calls.append((request.url.path,request.headers.get('X-Write-Token'),request.content))
            if request.url.path=='/api/status':return httpx.Response(200,json={'mode':'REAL','api_address':'http://test-line:8000'})
            if request.url.path=='/api/mode/enable':return httpx.Response(200,json={'write_token':'own-secret-token','expires_seconds':1800})
            if request.url.path=='/api/write':return httpx.Response(200,json={'written':True})
            return httpx.Response(200,json={})
        client=AppClient('http://127.0.0.1:8080','http://test-line:8000',1,httpx.MockTransport(handler))
        await client.write_signal('Tank01_FilterRemote',1)
        await client.close()
        assert [(path,token) for path,token,_ in calls if path in ('/api/write','/api/mode/disable')]==[('/api/write','own-secret-token'),('/api/mode/disable','own-secret-token')]
    asyncio.run(run())


@pytest.mark.parametrize('mode,target',[('MOCK','http://test-line:8000'),('REAL','http://other-line:8000')])
def test_app_mock_or_other_supplier_cannot_send_write(mode,target):
    async def run():
        posts=[]
        def handler(request):
            if request.method=='POST':posts.append(request.url.path)
            return httpx.Response(200,json={'mode':mode,'api_address':target})
        client=AppClient('http://127.0.0.1:8080','http://test-line:8000',1,httpx.MockTransport(handler))
        try:
            with pytest.raises(ValueError):await client.write_signal('Tank01_FilterRemote',1)
            assert posts==[] and not client.last_dispatch
        finally:await client.close()
    asyncio.run(run())


def test_app_explicit_pre_dispatch_failure_is_not_an_unknown_write():
    async def run():
        def handler(request):
            if request.url.path=='/api/status':return httpx.Response(200,json={'mode':'REAL','api_address':'http://test-line:8000'})
            if request.url.path=='/api/mode/enable':return httpx.Response(200,json={'write_token':'owned','expires_seconds':1800})
            return httpx.Response(403,json={'write_dispatched':False})
        client=AppClient('http://127.0.0.1:8080','http://test-line:8000',1,httpx.MockTransport(handler))
        try:
            with pytest.raises(PLCError):await client.write_signal('Tank01_FilterRemote',1)
            assert client.last_dispatch is False
        finally:
            client.token=None;await client.close()
    asyncio.run(run())


def test_disk_failure_does_not_block_authorized_restoration(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        original=runner.logs.source.add
        def fail(event,**fields):
            if event=='TEST_SWAGGER_RESTORE_INTENT':raise OSError('disk full')
            return original(event,**fields)
        runner.logs.source.add=fail
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert client.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
        assert row['restored'] and not row['continue_queue'] and row['audit_error']
    asyncio.run(run())


def test_cancelled_inflight_write_requires_explicit_restore(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path,answer='RESTORE')
        original=client.write_signal;entered=asyncio.Event()
        async def inflight(name,value):
            response=await original(name,value)
            if value==1:entered.set();await asyncio.Future()
            return response
        client.write_signal=inflight
        task=asyncio.create_task(runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None))
        await asyncio.wait_for(entered.wait(),1);task.cancel()
        row=await asyncio.wait_for(task,1)
        assert client.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
        assert row['request']=='unknown' and not row['continue_queue']
    asyncio.run(run())


def test_next_tank_and_app_path_wait_until_ready_after_restoration(tmp_path):
    async def run():
        client,service,runner,cases=fixture(tmp_path)
        app=FakeLine();runner.services['app']=SignalService(app,runner.logs,3000)
        pauses=[]
        def ready(prompt):
            pauses.append(prompt)
            assert client.values['Tank01_FilterRemote']==0
            return 'q'
        runner.ready=ready
        rows=await runner.run([cases['Tank01_FilterRemote'],cases['Tank02_FillWaterOn']])
        assert len(rows)==1 and rows[0]['restored'] and pauses and app.writes==[]
        assert not any(name=='Tank02_FillWaterOn' for name,_ in client.writes)
    asyncio.run(run())


def test_door_opposite_active_blocks_before_any_write(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        client.values['Tank01_DoorCloseRemote']=1
        row=await runner.run_path(cases['Tank01_DoorOpenRemote'],'direct',1,0,None)
        assert client.writes==[] and row['request']=='blocked' and not row['continue_queue']
    asyncio.run(run())


def test_door_opposite_activated_during_test_cannot_block_own_clear_but_stops_queue(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        def verdict(_):
            client.values['Tank01_DoorCloseRemote']=1
            return 'p'
        runner.verdict=verdict
        row=await runner.run_path(cases['Tank01_DoorOpenRemote'],'direct',1,0,None)
        assert client.writes==[('Tank01_DoorOpenRemote',1),('Tank01_DoorOpenRemote',0)]
        assert row['restore_readback_verified'] and not row['restored'] and not row['continue_queue']
    asyncio.run(run())


def test_main_inlet_status_must_restore_as_well_as_command(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        original=client.write_signal
        async def sticky(name,value):
            receipt=await original(name,value)
            if name=='MainInlet' and value==0:client.values['MainInletStatus']=1
            return receipt
        client.write_signal=sticky
        row=await runner.run_path(cases['MainInlet'],'direct',1,0,None)
        assert client.writes==[('MainInlet',1),('MainInlet',0)]
        assert row['restore_readback_verified'] and not row['restored'] and not row['continue_queue']
    asyncio.run(run())


def test_related_status_identity_change_blocks_before_write(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        client.by_name['Tank01_USStatus']['device_address']='Y999'
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert not client.writes and row['request']=='blocked'
    asyncio.run(run())


def test_comparison_report_keeps_path_results_separate_and_does_not_prove_cause(tmp_path):
    async def run():
        _,_,runner,cases=fixture(tmp_path)
        direct=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        app=FakeLine();app.feedback_missing=True
        runner.services['app']=SignalService(app,runner.logs,3000)
        await runner.run_path(cases['Tank01_FilterRemote'],'app',1,0,direct['baseline'])
        report=json.loads((tmp_path/'report.json').read_text())
        comparison=report['comparisons'][0]
        assert comparison['direct_request']==comparison['app_request']=='acknowledged'
        assert comparison['direct_output']=='confirmed' and comparison['app_output']=='unconfirmed'
        assert comparison['path_difference_observed'] and not comparison['path_cause_proven']
        assert (tmp_path/'comparison.csv').exists()
    asyncio.run(run())


def test_shared_auto_checks_and_restores_both_affected_tanks(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        def verdict(_):
            client.values['Tank05_FilterStatus']=1
            return 'p'
        runner.verdict=verdict
        row=await runner.run_path(cases['Tank03_FillWaterAuto'],'direct',1,0,None)
        assert row['restore_readback_verified'] and not row['restored'] and not row['continue_queue']
        assert client.values['Tank03_FillWaterAuto']==client.values['Tank05_FillWaterAuto']==0
    asyncio.run(run())


def test_shared_auto_active_related_alias_output_blocks_test(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        client.values['Tank05_FillWaterStatus']=1
        row=await runner.run_path(cases['Tank03_FillWaterAuto'],'direct',1,0,None)
        assert row['request']=='blocked' and not client.writes
    asyncio.run(run())


def test_readonly_metadata_drift_cannot_block_stable_target_cleanup(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        def verdict(_):
            client.by_name['Tank01_FilterStatus']['device_address']='D999.0'
            return 'p'
        runner.verdict=verdict
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert client.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
        assert row['restore_readback_verified'] and not row['restored'] and not row['continue_queue']
        assert 'metadata change' in row['restoration_error']
    asyncio.run(run())


def test_write_target_metadata_drift_still_blocks_cleanup_to_changed_address(tmp_path):
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        def verdict(_):
            client.by_name['Tank01_FilterRemote']['device_address']='M999'
            return 'p'
        runner.verdict=verdict
        row=await runner.run_path(cases['Tank01_FilterRemote'],'direct',1,0,None)
        assert client.writes==[('Tank01_FilterRemote',1)]
        assert not row['restored'] and not row['continue_queue']
    asyncio.run(run())


def test_app_error_retains_reason_but_redacts_echoed_own_token():
    async def run():
        token='private-own-write-token'
        def handler(request):
            if request.url.path=='/api/status':return httpx.Response(200,json={'mode':'REAL','api_address':'http://test-line:8000'})
            if request.url.path=='/api/mode/enable':return httpx.Response(200,json={'write_token':token,'expires_seconds':1800})
            return httpx.Response(403,json={'error':'Write mode expired for '+token,'write_dispatched':False})
        client=AppClient('http://127.0.0.1:8080','http://test-line:8000',1,httpx.MockTransport(handler))
        try:
            with pytest.raises(PLCError) as error:await client.write_signal('Tank01_FilterRemote',1)
            assert error.value.status==403 and error.value.write_dispatched is False
            assert 'Write mode expired' in error.value.detail
            assert token not in error.value.detail and '[REDACTED]' in error.value.detail
        finally:client.token=None;await client.close()
    asyncio.run(run())


@pytest.mark.parametrize('future_bound',[False,True])
def test_real_app_adapter_roundtrip_uses_final_app_timestamp_bounds(tmp_path,future_bound):
    from datetime import timedelta
    async def run():
        backing=FakeLine();logs=LogService(tmp_path/'events.jsonl','test-secret')
        async def handler(request):
            path=request.url.path
            if path=='/api/status':return httpx.Response(200,json={'mode':'REAL','api_address':'http://test-line:8000'})
            if path=='/api/tags':return httpx.Response(200,json={'tags':backing.tags})
            if path=='/api/signals':return httpx.Response(200,json=await backing.read_signals())
            if path=='/api/mode/enable':return httpx.Response(200,json={'write_token':'own-token','expires_seconds':1800})
            if path=='/api/write':
                body=json.loads(request.content);baseline=await backing.read_signals()
                receipt=await backing.write_signal(body['tag_name'],body['value'])
                stamp=(datetime.now(timezone.utc)+timedelta(seconds=2)).isoformat() if future_bound else baseline['timestamp']
                return httpx.Response(200,json={**receipt,'console_command_baseline_utc':stamp,'console_accepted_at':datetime.now(timezone.utc).isoformat()})
            return httpx.Response(200,json={})
        client=AppClient('http://127.0.0.1:8080','http://test-line:8000',1,httpx.MockTransport(handler))
        service=SignalService(client,logs,3000)
        runner=SwaggerLineTest({'app':service},logs,tmp_path,verdict=lambda _:'n',ready=lambda _:'r',prompt=lambda _:'RESTORE',wait_seconds=.03,emit=lambda _:None)
        case=next(c for c in inventory()['cases'] if c['tag_name']=='Tank01_FilterRemote')
        try:
            row=await runner.run_path(case,'app',1,0,None)
            assert row['request']=='acknowledged' and backing.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
            if future_bound:
                assert row['readback']=='not_observed' and not row['restored'] and not row['continue_queue']
            else:
                assert row['readback']=='verified' and row['output']=='confirmed' and row['restored']
            assert row['human_result']=='unchecked'
        finally:await client.close()
    asyncio.run(run())


def test_restore_ack_then_temporary_stale_sample_waits_for_fresh_zero_without_rewrite(tmp_path):
    from datetime import timedelta
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        runner.wait_seconds=.5
        original_write,original_read=client.write_signal,client.read_signals
        restoring=False;restore_reads=0
        async def write(name,value):
            nonlocal restoring
            response=await original_write(name,value)
            if name=='Tank14_TempAdj' and value==0:restoring=True
            return response
        async def read():
            nonlocal restore_reads
            poll=await original_read()
            if restoring:
                restore_reads+=1
                if restore_reads==1:
                    poll['timestamp']=(datetime.now(timezone.utc)-timedelta(milliseconds=3244)).isoformat()
            return poll
        client.write_signal,client.read_signals=write,read
        row=await runner.run_path(cases['Tank14_TempAdj'],'direct',900,0,None)
        assert client.writes==[('Tank14_TempAdj',900),('Tank14_TempAdj',0)]
        assert row['restore_acknowledged'] and row['restored'] and row['continue_queue']
        assert row['restore_rejected_samples']==1 and row['restore_sample']['fresh'] is True
        assert datetime.fromisoformat(row['restore_sample']['supplier_utc'])>datetime.fromisoformat(row['restore_received_at'])
        rejected=[entry for entry in runner.logs.source.get() if entry['event']=='TEST_SWAGGER_SAMPLE_REJECTED']
        assert len(rejected)==1 and rejected[0]['fresh'] is False and rejected[0]['age_ms']>=3244
    asyncio.run(run())


def test_persistent_stale_restoration_expires_without_next_command_or_rewrite(tmp_path):
    from datetime import timedelta
    async def run():
        client,_,runner,cases=fixture(tmp_path,answer='900')
        original_write,original_read=client.write_signal,client.read_signals
        restoring=False
        async def write(name,value):
            nonlocal restoring
            response=await original_write(name,value)
            if name=='Tank14_TempAdj' and value==0:restoring=True
            return response
        async def read():
            poll=await original_read()
            if restoring:poll['timestamp']=(datetime.now(timezone.utc)-timedelta(milliseconds=3244)).isoformat()
            return poll
        client.write_signal,client.read_signals=write,read
        rows=await runner.run([cases['Tank14_TempAdj'],cases['Tank14_TempSV']])
        assert len(rows)==1 and rows[0]['restore_acknowledged']
        assert not rows[0]['restored'] and not rows[0]['continue_queue']
        assert client.writes==[('Tank14_TempAdj',900),('Tank14_TempAdj',0)]
        assert 'restore_sample' not in rows[0] and rows[0]['restore_rejected_samples']>=1
    asyncio.run(run())


def test_local_mode_during_observation_aborts_even_when_sample_is_stale(tmp_path):
    from datetime import timedelta
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        original_read=client.read_signals
        async def read():
            poll=await original_read();poll['Local']=1
            poll['timestamp']=(datetime.now(timezone.utc)-timedelta(milliseconds=3244)).isoformat()
            return poll
        client.read_signals=read
        await runner.services['direct'].load_tags()
        with pytest.raises(ValueError,match='Remote/Local mode changed'):
            await runner.observe(runner.services['direct'],cases['Tank14_TempAdj'],0,[datetime.now(timezone.utc).isoformat()],
                                 {'path':'direct'},'restore',{'Tank14_TempAdj':0})
        assert not client.writes
    asyncio.run(run())


def test_stale_final_write_preflight_still_blocks_all_test_writes(tmp_path):
    from datetime import timedelta
    async def run():
        client,_,runner,cases=fixture(tmp_path)
        original_read=client.read_signals;reads=0
        async def read():
            nonlocal reads
            reads+=1;poll=await original_read()
            if reads>=2:poll['timestamp']=(datetime.now(timezone.utc)-timedelta(milliseconds=3244)).isoformat()
            return poll
        client.read_signals=read
        row=await runner.run_path(cases['Tank14_TempAdj'],'direct',900,0,None)
        assert not client.writes and row['request']=='blocked' and not row['continue_queue']
        assert 'test_rejected_samples' not in row
    asyncio.run(run())


RESUME_CONTEXT={'mode':'REAL','api_address':'http://test-line:8000'}


def resume_fixture(tmp_path):
    plan=inventory();cases=plan['cases'];byname={c['tag_name']:c for c in cases}
    autos=[c for c in cases if c['kind']=='auto'][:19]
    nonauto=[c for c in cases if c['kind']!='auto' and c['tag_name']!='Tank14_TempAdj']
    humans=autos[:2]+nonauto[:55]+[byname['Tank14_TempAdj']]
    human_names={c['tag_name'] for c in humans}
    mode_only=[c for c in autos if c['tag_name'] not in human_names]
    failures=[c for c in nonauto if c['tag_name'] not in human_names and c['feedback_tag']][:7]
    sent=humans+mode_only+failures
    sent_names={c['tag_name'] for c in sent}
    skipped=[c for c in cases if c['tag_name'] not in sent_names][:41]
    rows=[]
    for case in sent:
        passed=case['tag_name'] in human_names
        rows.append({'tag_name':case['tag_name'],'tank':case['tank'],'kind':case['kind'],'path':'direct',
                     'reviewed_identity':list(case['identity']),'request':'acknowledged','readback':'verified',
                     'output':'mode_only' if case['kind']=='auto' else 'confirmed' if passed else 'unconfirmed',
                     'human_result':'pass' if passed else 'unchecked','original_value':0,'restored':True})
    for row in rows:
        if row['tag_name']=='Tank14_TempAdj':row.update(restored=False,restoration_error='Prior stale read; restoration not verified',restore_acknowledged=True,
                restore_bounds=['2026-10-25T00:00:00+00:00'],restore_received_at='2026-10-25T00:00:01+00:00')
    for case in skipped:
        rows.append({'tag_name':case['tag_name'],'tank':case['tank'],'kind':case['kind'],'path':'not_run',
                     'request':'not_sent','skip_reason':'Value/rule skipped','human_result':'unchecked'})
    report={'format':'swagger-line-test-v1','context':dict(RESUME_CONTEXT),'contract_sha256':plan['contract_sha256'],'inventory':{c['tag_name']:c['identity'] for c in cases},'results':rows}
    path=tmp_path/'source-report.json';path.write_text(json.dumps(report))
    return plan,report,path,sent_names,{c['tag_name'] for c in skipped}


def test_resume_selects_59_skipped_unvisited_and_preserves75_pass7_timeout_fail(tmp_path):
    from tools.swagger_line_test import resume_plan
    plan,report,path,sent_names,skipped=resume_fixture(tmp_path)
    selected=resume_plan(plan,path,['direct'],RESUME_CONTEXT);resume=selected['resume']
    assert len(report['results'])==123
    assert len(selected['cases'])==59 and resume['pending_path_tests']==59
    assert resume['settled_pass_paths']==75 and resume['settled_timeout_fail_paths']==7
    assert resume['skipped_tags']==41 and resume['unvisited_tags']==18
    names={case['tag_name'] for case in selected['cases']}
    assert not names & sent_names and skipped<=names
    assert [case['tank'] for case in selected['cases']]==sorted(case['tank'] for case in selected['cases'])
    assert [row['tag_name'] for row in resume['recovery_required']]==['Tank14_TempAdj']
    assert json.loads(path.read_text())==report


def test_compare_resume_never_skips_untested_app_paths(tmp_path):
    from tools.swagger_line_test import resume_plan
    plan,_,path,sent_names,_=resume_fixture(tmp_path)
    selected=resume_plan(plan,path,['direct','app'],RESUME_CONTEXT)
    assert len(selected['cases'])==141 and selected['resume']['pending_path_tests']==200
    assert sum('app' in case['paths'] for case in selected['cases'])==141
    assert sum('direct' in case['paths'] for case in selected['cases'])==59
    assert all(case['paths']==['app'] for case in selected['cases'] if case['tag_name'] in sent_names)


@pytest.mark.parametrize('mutation',[
    lambda report:report.update(format='other-report'),
    lambda report:report.update(contract_sha256='different-swagger-contract'),
    lambda report:report['context'].update(mode='MOCK'),
    lambda report:report['context'].update(api_address='http://different-line:8000'),
    lambda report:report['inventory'].pop(next(iter(report['inventory']))),
    lambda report:report['results'][0]['reviewed_identity'].__setitem__(1,'M999'),
    lambda report:report['results'].append(dict(report['results'][0])),
    lambda report:report['results'][0].update(path='supplier'),
    lambda report:report['results'][0].update(request='unknown',human_result='unchecked'),
    lambda report:report['results'][0].update(error='Unresolved write error'),
])
def test_malformed_or_unresolved_resume_is_rejected_before_network(tmp_path,mutation):
    from tools.swagger_line_test import resume_plan
    plan,report,path,_,_=resume_fixture(tmp_path);mutation(report);path.write_text(json.dumps(report))
    with pytest.raises(ValueError):resume_plan(plan,path,['direct'],RESUME_CONTEXT)


def test_legacy_resume_warns_context_is_unknown_instead_of_inventing_origin(tmp_path):
    from tools.swagger_line_test import resume_plan
    plan,report,path,_,_=resume_fixture(tmp_path)
    report.pop('context');report.pop('inventory');path.write_text(json.dumps(report))
    selected=resume_plan(plan,path,['direct'],RESUME_CONTEXT)
    assert selected['resume']['legacy_context_unverified'] and len(selected['cases'])==59
    assert 'context' not in json.loads(path.read_text())


def test_resume_recovery_reads_only_target_not_delayed_unrelated_tank_states(tmp_path):
    from tools.swagger_line_test import resume_plan,verify_resume_recovery
    async def run():
        plan,report,path,_,_=resume_fixture(tmp_path)
        selected=resume_plan(plan,path,['direct'],RESUME_CONTEXT)
        client,service,runner,_=fixture(tmp_path)
        client.values['Tank14_FillWaterAuto']=1
        client.values['Tank14_FillWaterOn']=1
        client.values['Tank14_FillWaterStatus']=1
        proof=await verify_resume_recovery(service,selected['resume'],runner.logs)
        assert len(proof)==1 and proof[0]['values']=={'Tank14_TempAdj':0}
        assert proof[0]['fresh'] and proof[0]['write_sent'] is False and client.writes==[]
        assert selected['resume']['settled_paths'][57]['tag_name']=='Tank14_TempAdj'
        assert not any(row['recovery_required'] for row in selected['resume']['settled_paths'])
        assert json.loads(path.read_text())==report
    asyncio.run(run())


@pytest.mark.parametrize('condition',['not_restored','stale','local','metadata','alias'])
def test_resume_recovery_blocks_unsafe_current_state_without_corrective_write(tmp_path,condition):
    from tools.swagger_line_test import resume_plan,verify_resume_recovery
    async def run():
        plan,_,path,_,_=resume_fixture(tmp_path)
        selected=resume_plan(plan,path,['direct'],RESUME_CONTEXT)
        client,service,runner,_=fixture(tmp_path)
        if condition=='not_restored':client.values['Tank14_TempAdj']=900
        elif condition=='stale':service.stale_ms=-1
        elif condition=='local':client.values['Local']=1
        elif condition=='metadata':client.by_name['Tank14_TempAdj']['device_address']='D999'
        else:
            client.tags.append({**client.by_name['Tank14_TempAdj'],'tag_name':'ExtraAlias'});client.values['ExtraAlias']=0
        with pytest.raises(ValueError,match='Resume blocked'):
            await verify_resume_recovery(service,selected['resume'],runner.logs)
        assert client.writes==[]
    asyncio.run(run())


def test_resume_runner_respects_app_only_pending_path_and_writes_no_settled_direct_tag(tmp_path):
    async def run():
        direct,_,runner,cases=fixture(tmp_path)
        app=FakeLine();runner.services['app']=SignalService(app,runner.logs,3000)
        case={**cases['Tank01_FilterRemote'],'paths':['app']}
        rows=await runner.run([case])
        assert len(rows)==1 and rows[0]['path']=='app' and rows[0]['restored']
        assert direct.writes==[] and app.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
    asyncio.run(run())


def test_new_resume_report_carries_context_provenance_and_prior_settled_paths(tmp_path):
    from tools.swagger_line_test import resume_plan,verify_resume_recovery
    async def run():
        plan,source,path,_,_=resume_fixture(tmp_path)
        selected=resume_plan(plan,path,['direct'],RESUME_CONTEXT)
        client,service,runner,_=fixture(tmp_path)
        runner.context=RESUME_CONTEXT;runner.resume=selected['resume']
        runner.recovery_checks=await verify_resume_recovery(service,runner.resume,runner.logs)
        runner.save()
        report=json.loads((tmp_path/'report.json').read_text())
        assert report['context']==RESUME_CONTEXT and len(report['settled_paths'])==82
        assert report['resume']['source_sha256']==selected['resume']['source_sha256']
        assert len(report['inventory'])==141 and report['recovery_checks'][0]['write_sent'] is False
        again=resume_plan(plan,tmp_path/'report.json',['direct'],RESUME_CONTEXT)
        assert len(again['cases'])==59 and again['resume']['recovery_required']==[]
        assert source==json.loads(path.read_text()) and client.writes==[]
    asyncio.run(run())


def test_failed_startup_resume_report_save_is_reported_before_any_new_write(tmp_path,monkeypatch):
    client,_,runner,_=fixture(tmp_path)
    original=Path.open
    def failed_csv(path,*args,**kwargs):
        if path==tmp_path/'results.csv':raise OSError('Read-only CSV storage')
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',failed_csv)
    assert runner.save() is False and runner.results==[] and client.writes==[]


@pytest.mark.parametrize('position',['before','equal'])
def test_fresh_cached_recovery_zero_must_be_strictly_after_source_restore_bound(tmp_path,position):
    from datetime import timedelta
    from tools.swagger_line_test import resume_plan,verify_resume_recovery
    async def run():
        plan,report,path,_,_=resume_fixture(tmp_path)
        source=next(row for row in report['results'] if row['tag_name']=='Tank14_TempAdj')
        stamp=datetime.now(timezone.utc)
        latest=stamp+timedelta(seconds=.5)
        source.update(restore_bounds=[(stamp-timedelta(seconds=1)).isoformat(),latest.isoformat()],
                      restore_received_at=(stamp+timedelta(seconds=.25)).isoformat())
        path.write_text(json.dumps(report));selected=resume_plan(plan,path,['direct'],RESUME_CONTEXT)
        item=selected['resume']['recovery_required'][0]
        assert item['recovery_after']==latest.isoformat()
        client,service,runner,_=fixture(tmp_path);original=client.read_signals
        async def cached():
            poll=await original();poll['timestamp']=(latest if position=='equal' else stamp).isoformat()
            return poll
        client.read_signals=cached
        with pytest.raises(ValueError,match='Resume blocked'):
            await verify_resume_recovery(service,selected['resume'],runner.logs)
        assert client.writes==[] and item['recovery_required'] is True
    asyncio.run(run())


@pytest.mark.parametrize('field',['restore_bounds','restore_received_at','restore_acknowledged'])
def test_unresolved_legacy_restore_without_source_ack_bound_requires_review(tmp_path,field):
    from tools.swagger_line_test import resume_plan
    plan,report,path,_,_=resume_fixture(tmp_path)
    report.pop('context');source=next(row for row in report['results'] if row['tag_name']=='Tank14_TempAdj')
    source.pop(field);path.write_text(json.dumps(report))
    with pytest.raises(ValueError,match='source timing bounds'):
        resume_plan(plan,path,['direct'],RESUME_CONTEXT)


def test_legacy_origin_uncertainty_and_restore_bound_survive_resume_chain(tmp_path):
    from tools.swagger_line_test import resume_plan,verify_resume_recovery
    async def run():
        plan,report,path,_,_=resume_fixture(tmp_path);report.pop('context');path.write_text(json.dumps(report))
        selected=resume_plan(plan,path,['direct'],RESUME_CONTEXT)
        assert selected['resume']['legacy_context_unverified'] is True
        client,service,runner,_=fixture(tmp_path)
        runner.context=dict(RESUME_CONTEXT);runner.resume=selected['resume']
        runner.recovery_checks=await verify_resume_recovery(service,runner.resume,runner.logs)
        bound=runner.recovery_checks[0]['after_source_restore']
        assert runner.save()
        again=resume_plan(plan,tmp_path/'report.json',['direct'],RESUME_CONTEXT)
        assert again['resume']['legacy_context_unverified'] is True
        prior=next(row for row in again['resume']['settled_paths'] if row['tag_name']=='Tank14_TempAdj')
        assert prior['recovery_after']==bound and prior['recovery_required'] is False
        assert client.writes==[]
    asyncio.run(run())
