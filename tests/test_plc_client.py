import asyncio
import json
import httpx
import pytest
from server.plc_client import PLCClient, PLCError, ERRORS

@pytest.mark.parametrize('code', [400,401,403,404,502,503])
def test_supplier_error_mapping(code):
    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(code, json={'detail':'supplier detail'}))
        client = PLCClient('http://example.test', 'secret-key', 5, transport)
        with pytest.raises(PLCError) as caught: await client.list_tags()
        assert caught.value.message == ERRORS[code]
        await client.client.aclose()
    asyncio.run(run())

@pytest.mark.parametrize('tag_name,value', [('Tank01_TempSV',25.0), ('Tank01_TempAdj',-5.0)])
def test_engineering_value_sent_without_multiplier_conversion(tag_name, value):
    async def run():
        seen = {}
        def reply(request):
            seen['header'] = request.headers['X-API-Key']
            seen['body'] = request.content.decode()
            return httpx.Response(200, json={'written': True})
        client = PLCClient('http://example.test', 'secret-key', 5, httpx.MockTransport(reply))
        await client.write_signal(tag_name, value)
        assert json.loads(seen['body']) == {'tag_name': tag_name, 'value': value}
        assert seen['header'] == 'secret-key'
        await client.client.aclose()
    asyncio.run(run())

def test_signed_word_batch_engineering_value_unchanged():
    async def run():
        writes = [{'tag_name':'Tank01_TempAdj','value':-5.0}]
        def reply(request):
            assert request.url.path == '/api/v1/tags/write/batch'
            assert request.headers['X-API-Key'] == 'secret-key'
            assert json.loads(request.content) == {'writes': writes}
            return httpx.Response(200, json={'writes': writes})
        client = PLCClient('http://example.test', 'secret-key', 5, httpx.MockTransport(reply))
        await client.write_batch(writes)
        await client.client.aclose()
    asyncio.run(run())
