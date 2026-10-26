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
