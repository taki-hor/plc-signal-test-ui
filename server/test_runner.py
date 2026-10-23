import asyncio
import time
from datetime import datetime, timezone
from .models import ValidationError

class TestRunner:
    __test__ = False
    def __init__(self, service, logs, cases):
        self.service, self.logs = service, logs
        self.cases = {case['id']: case for case in cases}
        self.lock = service.command_lock

    async def run(self, case_id, authorize=None, mapping_under_test=False, end_mode='manual0'):
        if type(mapping_under_test) is not bool: raise ValidationError('mapping_under_test must be a boolean')
        if end_mode not in ('manual0', 'hold'): raise ValidationError('end_mode must be manual0 or hold')
        if not isinstance(case_id, str): raise ValidationError('Test id must be a string')
        case = self.cases.get(case_id)
        if not case: raise ValidationError('Unknown test case')
        if case.get('requires_confirmation') and not mapping_under_test:
            raise ValidationError('This command/feedback mapping requires supplier confirmation')
        if end_mode == 'hold' and 'door' in case['command_tag'].lower():
            raise ValidationError('Door commands require manual0 mode')
        if (mapping_under_test or end_mode == 'hold') and case.get('reset_command'):
            raise ValidationError('Mapping-under-test and Hold runs do not support automatic reset commands')
        if self.lock.locked(): raise ValidationError('Another write or command test is running')
        async with self.lock:
            started = time.monotonic()
            command_at = None
            baseline_time = None
            result = dict(test_name=case['name'], command=f"{case['command_tag']}={case['command_value']}",
                          expected_feedback=f"{case['feedback_tag']}={case['expected_feedback']}",
                          actual_feedback=None, result='BLOCKED', elapsed_ms=0, http_status=None, error=None,
                          mapping_under_test=mapping_under_test, end_mode=end_mode, command_address=None, write_dispatched=False)
            self.logs.add('TEST_START', **result)
            try:
                def check_baseline(poll):
                    nonlocal baseline_time
                    feedback_tag = self.service.tags.get(case['feedback_tag'])
                    if not feedback_tag or feedback_tag.read_write != 'R':
                        raise ValidationError('Feedback tag is missing or is not read-only')
                    if poll.get(case['feedback_tag']) == case['expected_feedback']:
                        raise ValidationError('Feedback already has expected value; command cannot prove a transition')
                    baseline_time = self.service.poll_time(poll)
                    if baseline_time is None: raise ValidationError('Feedback baseline timestamp is invalid')
                    command_tag = self.service.tags.get(case['command_tag'])
                    result['command_address'] = command_tag.device_address if command_tag else None
                    self.logs.add('TEST_BASELINE', test_name=case['name'], mapping_under_test=mapping_under_test, end_mode=end_mode, supplier_timestamp=poll.get('timestamp'),
                                  poll_id=poll.get('id'), actual_feedback=poll.get(case['feedback_tag']))

                await self.service.load_tags()
                check_baseline(await self.service.read())
                def mark_dispatched():
                    result['write_dispatched'] = True
                write_response = await self.service.write(case['command_tag'], case['command_value'],
                                                          authorize=authorize, before_write=check_baseline, on_dispatch=mark_dispatched)
                command_at = time.monotonic()
                accepted_at = datetime.now(timezone.utc)
                result['http_status'] = 200
                if write_response.get('written') is not True:
                    result['result'] = 'FAIL'
                    result['error'] = 'Supplier did not confirm written=true'
                    result['elapsed_ms'] = round((time.monotonic() - command_at) * 1000)
                    self.logs.add('TEST_FINISH', **result)
                    return result
                result['write_response'] = {**write_response, 'console_accepted_at':accepted_at.isoformat(),
                                            'console_command_baseline_utc':baseline_time.isoformat()}
                deadline = command_at + case['timeout_ms'] / 1000
                while True:
                    if authorize: authorize()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        result['result'] = 'TIMEOUT'
                        break
                    try:
                        poll = await asyncio.wait_for(self.service.read(), timeout=remaining)
                    except TimeoutError:
                        result['result'] = 'TIMEOUT'
                        break
                    if time.monotonic() >= deadline:
                        result['result'] = 'TIMEOUT'
                        break
                    if authorize: authorize()
                    result['actual_feedback'] = poll.get(case['feedback_tag'])
                    self.logs.add('TEST_FEEDBACK', test_name=case['name'], mapping_under_test=mapping_under_test, end_mode=end_mode, tag_name=case['feedback_tag'],
                                  value=result['actual_feedback'], supplier_timestamp=poll.get('timestamp'), poll_id=poll.get('id'))
                    if not self.service.fresh():
                        raise ValidationError('Feedback poll data is stale or incomplete')
                    if not self.service.remote():
                        raise ValidationError('PLC left Remote/API mode during feedback verification')
                    poll_time = self.service.poll_time(poll)
                    if (poll_time is not None and poll_time > baseline_time and poll_time >= accepted_at
                            and result['actual_feedback'] == case['expected_feedback']):
                        result['result'] = 'OBSERVED' if mapping_under_test else 'PASS'
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        result['result'] = 'TIMEOUT'
                        break
                    await asyncio.sleep(min(case['poll_interval_ms'] / 1000, remaining))
                if case.get('reset_command'):
                    reset = case['reset_command']
                    response = await self.service.write(reset['tag_name'], reset['value'], authorize=authorize)
                    if response.get('written') is not True:
                        raise ValidationError('Supplier did not confirm configured reset write')
            except Exception as exc:
                result['result'] = 'COMMUNICATION ERROR' if hasattr(exc, 'status') or (result['write_dispatched'] and 'write_response' not in result) else 'BLOCKED'
                result['http_status'] = getattr(exc, 'status', result['http_status'])
                result['error'] = str(exc)
            result['elapsed_ms'] = round((time.monotonic() - (command_at or started)) * 1000)
            self.logs.add('TEST_FINISH', **result)
            return result
