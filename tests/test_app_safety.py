import asyncio
from dataclasses import replace

import httpx
import pytest

from server.config import ROOT
from server.log_service import LogService
from server.plc_client import MockPLCClient
from server.signal_service import SignalService
from server.test_runner import TestRunner


@pytest.fixture
def console(monkeypatch, tmp_path):
    from server import app as console
    logs = LogService(tmp_path / 'events.jsonl', 'mock-secret-canary')
    client = MockPLCClient(ROOT / 'config/mock-tags.json')
    service = SignalService(client, logs, 3000)
    monkeypatch.setattr(console, 'client', client)
    monkeypatch.setattr(console, 'service', service)
    monkeypatch.setattr(console, 'logs', logs)
    monkeypatch.setattr(console, 'runner', TestRunner(service, logs, console.cases))
    monkeypatch.setattr(console, 'write_tokens', {})
    monkeypatch.setattr(console, 'settings', replace(console.settings, mock_mode=True, api_key='mock-secret-canary'))
    return console


def test_startup_and_reads_do_not_write_or_expose_api_key(console):
    async def run():
        transport = httpx.ASGITransport(app=console.app, client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            for path in ['/', '/api/tags', '/api/signals', '/api/status', '/api/test/cases', '/api/logs/export']:
                response = await browser.get(path)
                assert response.status_code == 200
                assert 'mock-secret-canary' not in response.text
            status = (await browser.get('/api/status')).json()
            assert status['write_mode_default']=='OFF' and status['data_fresh']
            assert all(console.client.values[t['tag_name']]==0 for t in console.client.tags if t['read_write']=='W')
            assert not console.write_tokens
            assert not any(e['event'].startswith('WRITE') for e in console.logs.get())
            assert any(w['device_address']=='D1036' for w in status['catalog_warnings'])
    asyncio.run(run())


@pytest.mark.parametrize('guard',['mode_off','non_loopback','cross_origin','expired','remote_off','stale','read_only'])
def test_write_guards_remain_enforced(console,guard):
    async def run():
        host = '192.0.2.1' if guard=='non_loopback' else '127.0.0.1'
        transport = httpx.ASGITransport(app=console.app,client=(host,1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = 'unauthorized'
            if guard not in ('mode_off','non_loopback'):
                mode = await browser.post('/api/mode/enable')
                assert mode.status_code == 200
                token = mode.json()['write_token']
            headers = {'X-Write-Token':token}
            if guard=='cross_origin': headers['Origin']='http://untrusted.test'
            if guard=='expired': console.write_tokens[token]=0
            if guard=='remote_off': console.client.values['Remote']=0
            if guard=='stale': console.service.stale_ms=-1
            name = 'Tank01_DoorOpened' if guard=='read_only' else 'Tank01_TempAdj'
            before = console.client.values[name]
            response = await browser.post('/api/write',headers=headers,json={'tag_name':name,'value':-5.0})
            assert response.status_code == (400 if guard in ('remote_off','stale','read_only') else 403)
            assert console.client.values[name]==before
    asyncio.run(run())


def test_confirmed_mode_write_negative_value_and_disable(console):
    async def run():
        transport = httpx.ASGITransport(app=console.app,client=('127.0.0.1',1234))
        async with httpx.AsyncClient(transport=transport,base_url='http://console.test') as browser:
            token = (await browser.post('/api/mode/enable')).json()['write_token']
            headers = {'X-Write-Token':token}
            body = {'tag_name':'Tank01_TempAdj','value':-5.0}
            response = await browser.post('/api/write',headers=headers,json=body)
            assert response.status_code==200 and response.json()['value']==-5.0
            assert (await browser.get('/api/signals')).json()['Tank01_TempAdj']==-5.0
            response = await browser.post('/api/write/batch',headers=headers,json={'writes':[body]})
            assert response.status_code==400
            assert (await browser.post('/api/mode/disable',headers=headers)).status_code==200
            assert (await browser.post('/api/write',headers=headers,json=body)).status_code==403
    asyncio.run(run())
