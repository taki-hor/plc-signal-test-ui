import asyncio
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

def test_engineering_value_sent_without_multiplier_conversion():
    async def run():
        seen = {}
        def reply(request):
            seen['header'] = request.headers['X-API-Key']
            seen['body'] = request.content.decode()
            return httpx.Response(200, json={'written': True})
        client = PLCClient('http://example.test', 'secret-key', 5, httpx.MockTransport(reply))
        await client.write_signal('Tank01_TempSV', 25.0)
        assert '25.0' in seen['body'] and '250' not in seen['body']
        assert seen['header'] == 'secret-key'
        await client.client.aclose()
    asyncio.run(run())
