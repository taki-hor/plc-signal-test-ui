"""Operator-confirmed imports are metadata-bound human evidence, never writes."""
from dataclasses import replace
import json

import pytest

from server.config import ROOT
from server.models import Tag
from server.operator_results import load_operator_results


CONTEXT = {'mode':'REAL', 'api_address':'http://test-line:8000'}
TAG = next(Tag.parse(row) for row in json.loads((ROOT/'config/mock-tags.json').read_text())['tags'] if row['tag_name']=='Tank07_AirAgitationOn')


def document():
    return {'format':'operator-results-v1','context':CONTEXT,'records':[
        {'kind':'human','identity':[TAG.tag_name,TAG.device_address,TAG.data_type,TAG.read_write,TAG.multiplier],
         'value':'pass','at':'2026-10-26T06:30:00+00:00','source':'Operator-confirmed CLI run',
         'observed_at':'2026-10-26T06:00:00+00:00','physical_stop_verified':False,'write_sent':False}]}


def test_load_explicit_operator_pass_keeps_scope_and_stop_limit(tmp_path):
    path=tmp_path/'operator.json';path.write_text(json.dumps(document()))
    rows,error=load_operator_results(path,CONTEXT,{TAG.tag_name:TAG})
    assert error is None and len(rows)==1 and rows[0]['value']=='pass'
    assert rows[0]['physical_stop_verified'] is False and rows[0]['write_sent'] is False


@pytest.mark.parametrize('change',[{'mode':'MOCK'},{'api_address':'http://another-line:8000'}])
def test_different_context_never_inherits_operator_pass(tmp_path,change):
    path=tmp_path/'operator.json';path.write_text(json.dumps(document()))
    assert load_operator_results(path,{**CONTEXT,**change},{TAG.tag_name:TAG})==(None,None)


@pytest.mark.parametrize('field,value',[('device_address','M999'),('data_type','Word'),('multiplier',.1),('read_write','R')])
def test_changed_metadata_never_inherits_operator_pass(tmp_path,field,value):
    path=tmp_path/'operator.json';path.write_text(json.dumps(document()))
    assert load_operator_results(path,CONTEXT,{TAG.tag_name:replace(TAG,**{field:value})})==([],None)


@pytest.mark.parametrize('mutation',[
    lambda d:d['records'][0].update(at='2026-10-26T06:30:00'),
    lambda d:d['records'][0].update(value='complete'),
    lambda d:d['records'][0].update(kind='api'),
    lambda d:d['records'][0].update(write_sent=True),
    lambda d:d.update(records='invalid')])
def test_invalid_import_reports_error_without_promoting_results(tmp_path,mutation):
    data=document();mutation(data)
    path=tmp_path/'operator.json';path.write_text(json.dumps(data))
    rows,error=load_operator_results(path,CONTEXT,{TAG.tag_name:TAG})
    assert rows==[] and error


def test_missing_file_has_no_imported_judgments(tmp_path):
    assert load_operator_results(tmp_path/'missing.json',CONTEXT,{TAG.tag_name:TAG})==(None,None)


def test_checks_endpoint_exposes_explicit_human_import_without_sending_writes(tmp_path,monkeypatch):
    import asyncio
    import httpx
    from server import app as module
    from server.api_checks import APIChecks
    from server.log_service import LogService
    from server.plc_client import MockPLCClient
    from server.signal_service import SignalService
    async def run():
        client=MockPLCClient(ROOT/'config/mock-tags.json')
        async def no_write(*args,**kwargs):
            raise AssertionError('Reading imported human results sent a PLC write')
        client.write_signal=no_write
        logs=LogService(tmp_path/'events.jsonl')
        service=SignalService(client,logs,3000)
        service.api_checks=APIChecks(tmp_path/'api-checks.json',logs,CONTEXT['mode'],CONTEXT['api_address'],[])
        (tmp_path/'logs').mkdir()
        (tmp_path/'logs'/'operator-results.json').write_text(json.dumps(document()))
        monkeypatch.setattr(module,'ROOT',tmp_path)
        monkeypatch.setattr(module,'service',service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=module.app),base_url='http://test') as browser:
            response=await browser.get('/api/checks')
        assert response.status_code==200
        data=response.json()
        assert data['context']==CONTEXT and data['records']==[]
        assert data['operator_results_error'] is None
        assert len(data['operator_results'])==1 and data['operator_results'][0]['value']=='pass'
        assert data['operator_results'][0]['physical_stop_verified'] is False
        assert all(value==0 for name,value in client.values.items() if name==TAG.tag_name)
    asyncio.run(run())


def test_operator_declaration_keeps_explicit_api_backfill_limit(tmp_path):
    data=document();data['records'][0]['api_backfill_allowed']=False
    path=tmp_path/'operator.json';path.write_text(json.dumps(data))
    rows,error=load_operator_results(path,CONTEXT,{TAG.tag_name:TAG})
    assert error is None and rows[0]['value']=='pass' and rows[0]['api_backfill_allowed'] is False
    data['records'][0]['api_backfill_allowed']='false';path.write_text(json.dumps(data))
    rows,error=load_operator_results(path,CONTEXT,{TAG.tag_name:TAG})
    assert rows==[] and error
