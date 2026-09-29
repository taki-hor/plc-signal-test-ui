import asyncio
import time
from .models import ValidationError

class TestRunner:
    __test__ = False
    def __init__(self, service, logs, cases):
        self.service, self.logs = service, logs
        self.cases = {case['id']: case for case in cases}
        self.lock = asyncio.Lock()

    async def run(self, case_id):
        case = self.cases.get(case_id)
        if not case: raise ValidationError('Unknown test case')
        if case.get('requires_confirmation'):
            raise ValidationError('This command/feedback mapping requires supplier confirmation')
        if self.lock.locked(): raise ValidationError('Another command test is running')
        async with self.lock:
            started = time.monotonic()
            command_at = None
            result = dict(test_name=case['name'], command=f"{case['command_tag']}={case['command_value']}",
                          expected_feedback=f"{case['feedback_tag']}={case['expected_feedback']}",
                          actual_feedback=None, result='BLOCKED', elapsed_ms=0, http_status=None, error=None)
            self.logs.add('TEST_START', **result)
            try:
                await self.service.load_tags()
                feedback_tag = self.service.tags.get(case['feedback_tag'])
                if not feedback_tag or feedback_tag.read_write != 'R':
                    raise ValidationError('Feedback tag is missing or is not read-only')
                baseline = await self.service.read()
                if baseline.get(case['feedback_tag']) == case['expected_feedback']:
                    raise ValidationError('Feedback already has expected value; command cannot prove a transition')
                write_response = await self.service.write(case['command_tag'], case['command_value'])
                command_at = time.monotonic()
                result['http_status'] = 200
                if write_response.get('written') is not True:
                    result['result'] = 'FAIL'
                    result['error'] = 'Supplier did not confirm written=true'
                    result['elapsed_ms'] = round((time.monotonic() - (command_at or started)) * 1000)
                    self.logs.add('TEST_FINISH', **result)
                    return result
                result['write_response'] = write_response
                deadline = command_at + case['timeout_ms'] / 1000
                while True:
                    poll = await self.service.read()
                    result['actual_feedback'] = poll.get(case['feedback_tag'])
                    self.logs.add('TEST_FEEDBACK', test_name=case['name'], tag_name=case['feedback_tag'], value=result['actual_feedback'])
                    if not self.service.fresh():
                        raise ValidationError('Feedback poll data is stale or incomplete')
                    if result['actual_feedback'] == case['expected_feedback']:
                        result['result'] = 'PASS'
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        result['result'] = 'TIMEOUT'
                        break
                    await asyncio.sleep(min(case['poll_interval_ms'] / 1000, remaining))
                if case.get('reset_command'):
                    reset = case['reset_command']
                    await self.service.write(reset['tag_name'], reset['value'])
            except Exception as exc:
                result['result'] = 'COMMUNICATION ERROR' if hasattr(exc, 'status') else 'BLOCKED'
                result['http_status'] = getattr(exc, 'status', result['http_status'])
                result['error'] = str(exc)
            result['elapsed_ms'] = round((time.monotonic() - (command_at or started)) * 1000)
            self.logs.add('TEST_FINISH', **result)
            return result
