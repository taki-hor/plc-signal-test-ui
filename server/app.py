import json
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from .config import ROOT, Settings
from .log_service import LogService
from .models import Tag, ValidationError
from .plc_client import MockPLCClient, PLCClient, PLCError
from .signal_service import SignalService
from .test_runner import TestRunner

settings = Settings()
logs = LogService(ROOT / 'logs' / 'events.jsonl', settings.api_key)
client = MockPLCClient(ROOT / 'config' / 'mock-tags.json') if settings.mock_mode else PLCClient(settings.base_url, settings.api_key, settings.timeout)
baseline = [Tag.parse(tag) for tag in json.loads((ROOT / 'config' / 'mock-tags.json').read_text())['tags']]
service = SignalService(client, logs, settings.stale_ms, baseline=None if settings.mock_mode else baseline,
                        timestamp_timezone=settings.timestamp_timezone, timestamp_offset_seconds=settings.timestamp_offset_seconds)
cases = json.loads((ROOT / 'config' / 'test-cases.json').read_text())['tests']
safety = json.loads((ROOT / 'config' / 'safety-config.json').read_text())
runner = TestRunner(service, logs, cases)
write_tokens: dict[str, float] = {}
app = FastAPI(title='Anodizing PLC Signal Test Console')
app.mount('/css', StaticFiles(directory=ROOT / 'frontend' / 'css'), name='css')
app.mount('/js', StaticFiles(directory=ROOT / 'frontend' / 'js'), name='js')

@app.middleware('http')
async def no_cache(request: Request, call_next):
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.exception_handler(PLCError)
async def plc_error(request: Request, exc: PLCError):
    from fastapi.responses import JSONResponse
    body = {'error': exc.message, 'detail': logs.scrub(exc.detail), 'http_status': exc.status}
    if type(getattr(exc, 'write_dispatched', None)) is bool: body['write_dispatched'] = exc.write_dispatched
    return JSONResponse(status_code=exc.status, content=body)

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    from fastapi.responses import JSONResponse
    body = {'detail': logs.scrub(exc.detail)}
    if request.url.path in ('/api/write', '/api/write/batch', '/api/test/run') and exc.status_code == 403 and getattr(exc, 'write_dispatched', None) is not True:
        body['write_dispatched'] = False
    return JSONResponse(status_code=exc.status_code, content=body, headers=exc.headers)

@app.exception_handler(ValidationError)
async def validation_error(request: Request, exc: ValidationError):
    from fastapi.responses import JSONResponse
    logs.add('VALIDATION', result='BLOCKED', error=str(exc))
    body = {'error': str(exc), 'http_status': 400}
    if request.url.path in ('/api/write', '/api/write/batch', '/api/test/run') and getattr(exc, 'write_dispatched', None) is not True: body['write_dispatched'] = False
    return JSONResponse(status_code=400, content=body)

def require_local(request: Request):
    if not request.client or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(403, 'Write operations require a browser on the backend host or a local SSH tunnel')
    origin = request.headers.get('origin')
    if origin and origin.rstrip('/') != str(request.base_url).rstrip('/'):
        raise HTTPException(403, 'Cross-origin write request blocked')

def require_mode(request: Request):
    require_local(request)
    token = request.headers.get('X-Write-Token', '')
    expiry = write_tokens.get(token, 0)
    if not token or expiry < time.monotonic():
        raise HTTPException(403, 'WRITE TEST MODE is disabled or expired')

@app.get('/')
async def index(): return FileResponse(ROOT / 'frontend' / 'index.html')

@app.get('/api/status')
async def status(request: Request):
    try:
        require_mode(request)
        write_enabled = True
    except HTTPException:
        write_enabled = False
    age = service.age_ms()
    stamp = service.poll_time()
    return {'backend_status': 'RUNNING', 'supplier_api_connected': service.last_success is not None and service.last_error is None,
            'mode': 'MOCK' if settings.mock_mode else 'REAL', 'plc_mode': 'REMOTE' if service.remote() else ('LOCAL' if service.last_poll and service.last_poll.get('Local') == 1 else 'UNKNOWN'),
            'api_address': 'MOCK' if settings.mock_mode else settings.base_url, 'last_successful_request': service.last_success,
            'supplier_timestamp': service.last_poll.get('timestamp') if service.last_poll else None, 'data_age_ms': age,
            'supplier_timestamp_utc': stamp.isoformat() if stamp is not None else None,
            'data_fresh': service.fresh(), 'tags_ok': service.last_poll.get('tags_ok') if service.last_poll else None,
            'tags_failed': service.last_poll.get('tags_failed') if service.last_poll else None,
            'last_error': logs.scrub(service.last_error), 'poll_interval_ms': settings.poll_ms, 'stale_after_ms': settings.stale_ms,
            'timestamp_offset_seconds': service.timestamp_offset_seconds,
            'write_mode_default': 'OFF', 'write_mode_enabled': write_enabled, 'catalog_warnings': logs.scrub(service.catalog_warnings)}

@app.get('/api/tags')
async def tags(): return logs.scrub({'tags': [tag.__dict__ for tag in await service.load_tags()]})

@app.get('/api/signals')
async def signals(): return logs.scrub(await service.read())

@app.post('/api/mode/enable')
async def enable_mode(request: Request):
    require_local(request)
    token = secrets.token_urlsafe(32)
    write_tokens[token] = time.monotonic() + safety['write_mode_ttl_seconds']
    logs.add('WRITE_MODE', result='ENABLED', duration_seconds=safety['write_mode_ttl_seconds'])
    return {'write_token': token, 'expires_seconds': safety['write_mode_ttl_seconds']}

@app.post('/api/mode/disable')
async def disable_mode(request: Request):
    require_local(request)
    write_tokens.pop(request.headers.get('X-Write-Token', ''), None)
    logs.add('WRITE_MODE', result='DISABLED')
    return {'write_mode': 'OFF'}

def read_baseline(poll, writes):
    """Read-only evidence from the final validated snapshot; no inferred mappings."""
    values = {name: poll.get(name) for name, tag in service.tags.items() if tag.read_write == 'R'}
    mappings = [{key: case[key] for key in ('command_tag', 'command_value', 'feedback_tag', 'expected_feedback', 'requires_confirmation')}
                for case in cases if case['feedback_tag'] in values and
                any(item['tag_name'] == case['command_tag'] and item['value'] == case['command_value'] for item in writes)]
    return {'supplier_timestamp': poll['timestamp'], 'supplier_timestamp_utc': service.poll_time(poll).isoformat(),
            'values': values, 'mappings': mappings}

@app.post('/api/write')
async def write(request: Request, body: dict):
    require_mode(request)
    tag_name = body.get('tag_name')
    if not isinstance(tag_name, str): raise ValidationError('tag_name is required')
    if service.command_lock.locked(): raise ValidationError('Another write or command test is running')
    async with service.command_lock:
        case = next((c for c in cases if c['command_tag'] == tag_name and c['command_value'] == body.get('value') and not c.get('requires_confirmation')), None)
        feedback = {}
        command_baseline_utc = None
        reads = None
        def capture_baseline(poll):
            nonlocal command_baseline_utc, reads
            command_baseline_utc = service.poll_time(poll).isoformat()
            reads = read_baseline(poll, [{'tag_name': tag_name, 'value': body.get('value')}])
            if not case: return
            tag = service.tags.get(case['feedback_tag'])
            if tag and tag.read_write == 'R':
                feedback.update(feedback_tag=tag.tag_name, expected_feedback=case['expected_feedback'],
                                value_before=poll.get(tag.tag_name), supplier_timestamp_utc=command_baseline_utc)
        response = await service.write(tag_name, body.get('value'), authorize=lambda: require_mode(request), before_write=capture_baseline)
        return logs.scrub({**response, 'console_accepted_at': datetime.now(timezone.utc).isoformat() if response.get('written') is True else None,
                           'console_command_baseline_utc': command_baseline_utc, 'console_feedback_baseline': feedback or None,
                           'console_read_baseline': reads})

@app.post('/api/write/batch')
async def write_batch(request: Request, body: dict):
    require_mode(request)
    if body.get('confirmation') != safety['batch_confirmation_phrase']:
        raise ValidationError('Batch write requires exact confirmation')
    writes = body.get('writes')
    if not isinstance(writes, list) or any(not isinstance(item, dict) for item in writes):
        raise ValidationError('writes must be a list of objects')
    if len(writes) > safety['max_batch_items']: raise ValidationError('Batch exceeds configured maximum')
    if service.command_lock.locked(): raise ValidationError('Another write or command test is running')
    async with service.command_lock:
        reads = None
        def capture_baseline(poll):
            nonlocal reads
            reads = read_baseline(poll, writes)
        response = await service.write_batch(writes, authorize=lambda: require_mode(request), before_write=capture_baseline)
        results = response.get('writes', [])
        accepted = isinstance(results, list) and len(results) == len(writes) and all(
            any(isinstance(result, dict) and result.get('tag_name') == item['tag_name'] and
                result.get('value') == item['value'] and result.get('written') is True for result in results) for item in writes)
        return logs.scrub({**response, 'console_batch_accepted': accepted,
                           'console_accepted_at': datetime.now(timezone.utc).isoformat() if accepted else None,
                           'console_read_baseline': reads})

@app.get('/api/test/cases')
async def test_cases(): return {'tests': cases}

@app.post('/api/test/run')
async def test_run(request: Request, body: dict):
    require_mode(request)
    result = await runner.run(body.get('id'), authorize=lambda: require_mode(request),
                              mapping_under_test=body.get('mapping_under_test', False), end_mode=body.get('end_mode', 'manual0'))
    result['write_response'] = logs.scrub(result.get('write_response'))
    return result

@app.get('/api/logs')
async def get_logs(kind: str = 'all'):
    if kind not in ('all', 'communication', 'tests'): raise ValidationError('Invalid log kind')
    return {'logs': logs.get(kind)}

@app.get('/api/logs/export')
async def export_logs(kind: str = 'all', format: str = 'json'):
    if kind not in ('all', 'communication', 'tests') or format not in ('json', 'csv'):
        raise ValidationError('Invalid export selection')
    content, media_type = logs.export(kind, format)
    return Response(content, media_type=media_type, headers={'Content-Disposition': f'attachment; filename="plc-{kind}-log.{format}"'})

@app.post('/api/mock/fault')
async def mock_fault(request: Request):
    require_local(request)
    if not settings.mock_mode: raise HTTPException(404, 'Mock mode is disabled')
    client.fail_next_read = True
    return {'injected': 'next read will fail'}

@app.post('/api/mock/feedback-delay')
async def mock_feedback_delay(request: Request, body: dict):
    require_local(request)
    if not settings.mock_mode: raise HTTPException(404, 'Mock mode is disabled')
    delay_ms = body.get('delay_ms')
    if not isinstance(delay_ms, (int, float)) or not 0 <= delay_ms <= 30000: raise ValidationError('delay_ms must be 0 to 30000')
    client.feedback_delay_s = delay_ms / 1000
    return {'feedback_delay_ms': delay_ms}
