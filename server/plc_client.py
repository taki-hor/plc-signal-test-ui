import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
import httpx

ERRORS = {
    400: 'PLC API rejected the value. Check type and configured limits.',
    401: 'PLC API authentication failed.',
    403: 'This tag is read-only and cannot be written.',
    404: 'PLC tag or poll data was not found.',
    502: 'PLC write or PLC communication failed.',
    503: 'PLC API or PLC is temporarily unavailable/busy.',
}

class PLCError(Exception):
    def __init__(self, status: int, detail: str = ''):
        self.status = status
        self.message = ERRORS.get(status, 'PLC API request failed.')
        self.detail = detail[:500]
        super().__init__(self.message)

class PLCClient:
    def __init__(self, base_url: str, api_key: str, timeout: float, transport=None):
        self.base_url = base_url
        self.api_key = api_key
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport, headers={'X-API-Key': api_key})

    async def _request(self, method, path, body=None):
        try:
            response = await self.client.request(method, path, json=body)
            if response.status_code >= 400:
                raise PLCError(response.status_code, response.text)
            return response.json()
        except PLCError:
            raise
        except (httpx.HTTPError, ValueError) as exc:
            raise PLCError(502, str(exc)) from exc

    async def list_tags(self): return await self._request('GET', '/api/v1/tags/list')
    async def read_signals(self): return await self._request('GET', '/api/v1/tags/read')
    async def read_signal(self, tag_name): return (await self.read_signals()).get(tag_name)
    async def write_signal(self, tag_name, value): return await self._request('POST', '/api/v1/tags/write', {'tag_name': tag_name, 'value': value})
    async def write_batch(self, writes): return await self._request('POST', '/api/v1/tags/write/batch', {'writes': writes})
    async def wait_for_signal(self, tag_name, expected, timeout_ms, poll_interval_ms):
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while True:
            poll = await self.read_signals()
            if poll.get(tag_name) == expected:
                return poll
            if asyncio.get_running_loop().time() >= deadline:
                return None
            await asyncio.sleep(min(poll_interval_ms / 1000, max(0, deadline - asyncio.get_running_loop().time())))

class MockPLCClient:
    def __init__(self, catalog_path: Path):
        self.tags = json.loads(catalog_path.read_text())['tags']
        self.by_name = {tag['tag_name']: tag for tag in self.tags}
        self.values = {tag['tag_name']: 0 for tag in self.tags}
        self.values['Remote'] = 1
        self.values['Local'] = 0
        for tank in (1, 3, 5, 7, 10, 12, 14):
            tag = f'Tank{tank:02d}_DoorClosed'
            if tag in self.values: self.values[tag] = 1
        self.pending = []
        self.feedback_delay_s = 0.5
        self.fail_next_read = False
        self.poll_count = 0

    async def list_tags(self): return {'tags': self.tags}

    async def read_signals(self):
        if self.fail_next_read:
            self.fail_next_read = False
            raise PLCError(502, 'Mock communication failure')
        now = asyncio.get_running_loop().time()
        for due, tag, value in list(self.pending):
            if now >= due:
                self.values[tag] = value
                self.pending.remove((due, tag, value))
        self.poll_count += 1
        return {'id': self.poll_count, 'timestamp': datetime.now(timezone.utc).isoformat(),
                'poll_count': self.poll_count, 'tags_ok': len(self.tags), 'tags_failed': 0, **self.values}

    async def read_signal(self, tag_name): return (await self.read_signals()).get(tag_name)

    async def write_signal(self, tag_name, value):
        tag = self.by_name.get(tag_name)
        if not tag: raise PLCError(404, 'Unknown mock tag')
        if tag['read_write'] != 'W': raise PLCError(403, 'Read-only mock tag')
        self.values[tag_name] = value
        for action, feedback, opposite in [('Open', 'Opened', 'Closed'), ('Close', 'Closed', 'Opened')]:
            if tag_name.endswith(f'Door{action}Remote') and value == 1:
                prefix = tag_name.split('Door')[0]
                if prefix + 'Door' + feedback in self.values:
                    self.pending.append((asyncio.get_running_loop().time() + self.feedback_delay_s, prefix + 'Door' + feedback, 1))
                    self.pending.append((asyncio.get_running_loop().time() + self.feedback_delay_s, prefix + 'Door' + opposite, 0))
        return {'tag_name': tag_name, 'device_address': tag['device_address'], 'data_type': tag['data_type'], 'read_write': 'W', 'multiplier': tag['multiplier'], 'value': value, 'written': True}

    async def write_batch(self, writes):
        results = []
        for item in writes:
            results.append(await self.write_signal(item['tag_name'], item['value']))
        return {'writes': results}

    async def wait_for_signal(self, tag_name, expected, timeout_ms, poll_interval_ms):
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while True:
            poll = await self.read_signals()
            if poll.get(tag_name) == expected: return poll
            if asyncio.get_running_loop().time() >= deadline: return None
            await asyncio.sleep(min(poll_interval_ms / 1000, max(0, deadline - asyncio.get_running_loop().time())))
