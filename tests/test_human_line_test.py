"""The direct supplier queue is tested exclusively with an in-memory PLC."""
import asyncio
from dataclasses import replace
import json
from pathlib import Path

import pytest

from server.config import ROOT
from server.log_service import LogService
from server.plc_client import MockPLCClient, PLCError
from server.signal_service import SignalService
from tools.human_line_test import APPROVED, HumanLineTest, load_plan, main


class FakeLine(MockPLCClient):
    def __init__(self):
        super().__init__(ROOT/'config/mock-tags.json')
        self.writes=[];self.unknown_one=False;self.feedback_missing=False;self.clear_missing=False

    async def write_signal(self,name,value):
        self.writes.append((name,value))
        receipt=await super().write_signal(name,value)
        feedback=name.removesuffix('Remote')+'Status'
        if name.endswith('On'):feedback=name[:-2]+'Status'
        if feedback in self.values and not self.feedback_missing and not (value==0 and self.clear_missing):
            self.values[feedback]=value
        if value==1 and self.unknown_one:raise PLCError(502,'private-canary acknowledgement lost')
        return receipt


def fixture(tmp_path,verdict='p',cleanup='ZERO'):
    client=FakeLine();logs=LogService(tmp_path/'events.jsonl','private-canary')
    service=SignalService(client,logs,3000)
    runner=HumanLineTest(service,logs,tmp_path,verdict=lambda _:verdict,cleanup=lambda _:cleanup,emit=lambda _:None)
    plan=load_plan(ROOT/'config/human-line-test-plan.json')
    return client,service,runner,plan


def case_for(plan,name):
    return next(case for case in plan['cases'] if case['tag_name']==name)


def test_dry_run_is_offline_and_plan_contains_only_approved_distinct_commands(monkeypatch,capsys):
    def no_network(*args,**kwargs):raise AssertionError('Dry run opened an HTTP client')
    monkeypatch.setattr('tools.human_line_test.PLCClient',no_network)
    assert main([])==0
    assert 'DRY RUN' in capsys.readouterr().out
    plan=load_plan(ROOT/'config/human-line-test-plan.json')
    assert len(plan['cases'])==len(APPROVED)==63
    assert sum(case['feedback_tag'] is None for case in plan['cases'])==23
    assert all('Door' not in case['tag_name'] and not case['tag_name'].endswith('RemoteStart') for case in plan['cases'])


def test_full_cycle_records_api_pass_and_start_only_human_judgment(tmp_path):
    async def run():
        client,_,runner,plan=fixture(tmp_path)
        row=await runner.run_case(case_for(plan,'Tank01_FilterRemote'))
        assert client.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
        assert row['api_status']=='checked' and row['restored_zero'] and row['continue_queue']
        assert row['human_observation']=='pass' and row['human_result']=='unchecked'
        assert 'physical stop' in row['human_observation_scope']
        assert 'private-canary' not in (tmp_path/'events.jsonl').read_text()
        assert (tmp_path/'report.json').exists() and 'api_result' in (tmp_path/'results.csv').read_text()
    asyncio.run(run())


def test_human_no_response_is_independent_of_api_pass(tmp_path):
    async def run():
        _,_,runner,plan=fixture(tmp_path,verdict='n')
        row=await runner.run_case(case_for(plan,'Tank01_FilterRemote'))
        assert row['api_status']=='checked' and row['human_observation']=='no_response'
    asyncio.run(run())


@pytest.mark.parametrize('condition',['local','remote','stale','baseline','shared','identity'])
def test_unsafe_baseline_blocks_all_writes(tmp_path,condition):
    async def run():
        client,service,runner,plan=fixture(tmp_path)
        case=case_for(plan,'Tank01_FilterRemote')
        if condition=='local':client.values['Local']=1
        elif condition=='remote':client.values['Remote']=0
        elif condition=='stale':service.stale_ms=-1
        elif condition=='baseline':client.values[case['tag_name']]=1
        elif condition=='shared':
            alias={**client.by_name[case['tag_name']],'tag_name':'UnexpectedAlias'}
            client.tags.append(alias);client.values['UnexpectedAlias']=0
        elif condition=='identity':case={**case,'identity':[case['tag_name'],'M999','Bool','W',1]}
        row=await runner.run_case(case)
        assert client.writes==[] and row['api_status']=='unchecked' and not row['continue_queue']
    asyncio.run(run())


def test_metadata_refresh_before_dispatch_blocks_changed_identity(tmp_path):
    async def run():
        client,_,runner,plan=fixture(tmp_path)
        original=client.list_tags;reads=0
        async def changed():
            nonlocal reads
            reads+=1
            if reads==2:client.by_name['Tank01_FilterRemote']['device_address']='M999'
            return await original()
        client.list_tags=changed
        row=await runner.run_case(case_for(plan,'Tank01_FilterRemote'))
        assert not client.writes and row['api_status']=='unchecked'
    asyncio.run(run())


@pytest.mark.parametrize('cleanup,expected',[('ZERO',[1,0]),('NO',[1])])
def test_unknown_one_is_never_retried_and_cleanup_requires_explicit_choice(tmp_path,cleanup,expected):
    async def run():
        client,_,runner,plan=fixture(tmp_path,cleanup=cleanup)
        client.unknown_one=True
        row=await runner.run_case(case_for(plan,'Tank01_FilterRemote'))
        assert [value for _,value in client.writes]==expected
        assert row['api_status']=='failed' and not row['continue_queue']
        assert 'private-canary' not in (tmp_path/'report.json').read_text()
    asyncio.run(run())


def test_failed_restoration_stops_before_next_case(tmp_path):
    async def run():
        client,_,runner,plan=fixture(tmp_path);client.clear_missing=True
        first={**case_for(plan,'Tank01_FilterRemote'),'wait_seconds':1}
        rows=await runner.run([first,case_for(plan,'Tank01_HeaterRemote')])
        assert len(rows)==1 and not rows[0]['restored_zero']
        assert client.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
    asyncio.run(run())


def test_q_restores_before_stopping_and_auto_uses_own_readback(tmp_path):
    async def run():
        client,_,runner,plan=fixture(tmp_path,verdict='q')
        rows=await runner.run([case_for(plan,'Tank07_CoolerAuto'),case_for(plan,'Tank01_FilterRemote')])
        assert len(rows)==1 and rows[0]['api_status']=='checked' and rows[0]['restored_zero']
        assert client.writes==[('Tank07_CoolerAuto',1),('Tank07_CoolerAuto',0)]
        assert client.values['Tank07_CoolerStatus']==0
    asyncio.run(run())


def test_plan_rejects_unapproved_or_changed_feedback_before_network(tmp_path):
    plan=json.loads((ROOT/'config/human-line-test-plan.json').read_text())
    file=tmp_path/'plan.json'
    for change in [{'tag_name':'Tank01_DoorOpenRemote'},{'feedback_tag':'Tank01_DoorOpened'}]:
        copy={**plan,'cases':[{**plan['cases'][0],**change}]};file.write_text(json.dumps(copy))
        with pytest.raises(ValueError):load_plan(file)


def test_auto_watchers_can_be_aliased_but_the_written_bit_stays_independent(tmp_path):
    async def run():
        client,_,runner,plan=fixture(tmp_path)
        row=await runner.run_case(case_for(plan,'Tank02_AirAgitationAuto'))
        assert row['api_status']=='checked' and row['restored_zero']
        assert client.writes==[('Tank02_AirAgitationAuto',1),('Tank02_AirAgitationAuto',0)]
    asyncio.run(run())


def test_queue_auto_advances_and_incorrect_action_remains_a_distinct_observation(tmp_path):
    async def run():
        client,_,runner,plan=fixture(tmp_path,verdict='i')
        rows=await runner.run([case_for(plan,'Tank01_FilterRemote'),case_for(plan,'Tank01_HeaterRemote')])
        assert len(rows)==2 and all(row['human_observation']=='incorrect' and row['api_status']=='checked' for row in rows)
        assert [value for _,value in client.writes]==[1,0,1,0]
    asyncio.run(run())


def test_console_and_exports_redact_secrets_and_csv_escapes_formula_text(tmp_path):
    import csv
    async def run():
        _,_,runner,plan=fixture(tmp_path)
        printed=[];runner.emit=lambda message:printed.append(runner.logs.scrub(message))
        async def invalid(_):raise ValueError('=UNTRUSTED("private-canary")')
        runner.prepare=invalid
        await runner.run_case(case_for(plan,'Tank01_FilterRemote'))
        assert all('private-canary' not in message for message in printed)
        with (tmp_path/'results.csv').open() as stream:row=next(csv.DictReader(stream))
        assert row['error'].startswith("'=") and 'private-canary' not in row['error']
    asyncio.run(run())


@pytest.mark.parametrize('cleanup,expected_values',[('ZERO',[1,0]),('NO',[1])])
def test_cancelled_inflight_one_is_unknown_and_requires_cleanup_choice(tmp_path,cleanup,expected_values):
    async def run():
        client,_,runner,plan=fixture(tmp_path,cleanup=cleanup)
        original=client.write_signal;entered=asyncio.Event();prompts=[]
        async def inflight(name,value):
            result=await original(name,value)
            if value==1:
                entered.set()
                await asyncio.Future()
            return result
        client.write_signal=inflight
        runner.cleanup=lambda prompt:prompts.append(prompt) or cleanup
        task=asyncio.create_task(runner.run_case(case_for(plan,'Tank01_FilterRemote')))
        await asyncio.wait_for(entered.wait(),1)
        task.cancel()
        row=await asyncio.wait_for(task,1)
        assert len(prompts)==1 and 'ZERO' in prompts[0]
        assert [value for _,value in client.writes]==expected_values
        assert row['error']=='CancelledError' and not row['continue_queue']
    asyncio.run(run())


@pytest.mark.parametrize('failure_event',['TEST_ZERO_INTENT','WRITE','TEST_CASE_RESULT'])
def test_audit_failure_after_one_never_blocks_authorized_zero_and_stops_queue(tmp_path,failure_event):
    async def run():
        client,_,runner,plan=fixture(tmp_path)
        original=runner.logs.source.add
        def disk_full(event,**fields):
            if event==failure_event:raise OSError('disk full private-canary')
            return original(event,**fields)
        runner.logs.source.add=disk_full
        rows=await runner.run([case_for(plan,'Tank01_FilterRemote'),case_for(plan,'Tank01_HeaterRemote')])
        assert client.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
        assert len(rows)==1 and rows[0]['restored_zero'] and not rows[0]['continue_queue']
        assert rows[0]['api_status']=='unchecked' and 'Audit storage' in rows[0]['audit_error']
        report=json.loads((tmp_path/'report.json').read_text())
        assert report['audit_fallback_events'] and 'private-canary' not in json.dumps(report)
    asyncio.run(run())


def test_audit_failure_before_one_blocks_start(tmp_path):
    async def run():
        client,_,runner,plan=fixture(tmp_path)
        runner.logs.source.add=lambda *args,**fields:(_ for _ in ()).throw(OSError('disk full'))
        row=await runner.run_case(case_for(plan,'Tank01_FilterRemote'))
        assert not client.writes and not row['continue_queue']
    asyncio.run(run())


@pytest.mark.parametrize('cancel',[False,True])
def test_async_terminal_verdict_returns_or_cancels_and_restores_terminal(tmp_path,monkeypatch,cancel):
    import os
    import pty
    import termios
    from tools.human_line_test import read_verdict
    async def run():
        master,slave=pty.openpty()
        stream=os.fdopen(slave,'r',closefd=False)
        previous=termios.tcgetattr(slave)
        monkeypatch.setattr('sys.stdin',stream)
        try:
            task=asyncio.create_task(read_verdict('test verdict: '))
            await asyncio.sleep(.01)
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):await task
            else:
                os.write(master,b'i')
                assert await asyncio.wait_for(task,1)=='i'
            assert termios.tcgetattr(slave)==previous
        finally:
            stream.close();os.close(master);os.close(slave)
    asyncio.run(run())


def test_human_queue_includes_previously_api_verified_non_door_commands(tmp_path):
    names=['Tank07_AirAgitationOn','Tank07_CoolerOn','Tank08_AirAgitationOn','Tank09_AirAgitationOn',
           'Tank12_AirAgitationOn','Tank15_AirAgitationOn','Tank16_AirAgitationOn']
    plan=load_plan(ROOT/'config/human-line-test-plan.json',names)
    assert {case['tag_name'] for case in plan['cases']}==set(names)
    saved={tag['tag_name']:tag for tag in json.loads((ROOT/'docs/source/supplier-tags-2026-10-23.json').read_text())['tags']}
    for case in plan['cases']:
        assert case['feedback_tag']==case['tag_name'][:-2]+'Status'
        for field,name in [('identity',case['tag_name']),('feedback_identity',case['feedback_tag'])]:
            assert case[field]==[saved[name][key] for key in ['tag_name','device_address','data_type','read_write','multiplier']]


def test_csv_only_export_failure_updates_primary_json_after_verified_cleanup(tmp_path,monkeypatch):
    async def run():
        client,_,runner,plan=fixture(tmp_path)
        original=Path.open
        def blocked_csv(path,*args,**kwargs):
            if path==tmp_path/'results.csv':raise OSError('CSV storage unavailable')
            return original(path,*args,**kwargs)
        monkeypatch.setattr(Path,'open',blocked_csv)
        row=await runner.run_case(case_for(plan,'Tank01_FilterRemote'))
        report=json.loads((tmp_path/'report.json').read_text())['results'][0]
        assert client.writes==[('Tank01_FilterRemote',1),('Tank01_FilterRemote',0)]
        for result in (row,report):
            assert result['restored_zero'] and result['api_status']=='unchecked' and not result['continue_queue']
            assert 'CSV storage unavailable' in result['audit_error']
    asyncio.run(run())
