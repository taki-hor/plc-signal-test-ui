import asyncio
import time
import uuid
from datetime import datetime, timezone
from .models import ValidationError

_CASE_TIMEOUT = object()

class TestRunner:
    __test__ = False
    def __init__(self, service, logs, cases):
        self.service, self.logs = service, logs
        self.cases = {case['id']: case for case in cases}
        self.lock = service.command_lock

    async def run(self, case_id, authorize=None, mapping_under_test=False, end_mode='manual0', timeout_ms=_CASE_TIMEOUT):
        if type(mapping_under_test) is not bool: raise ValidationError('mapping_under_test must be a boolean')
        if end_mode not in ('manual0', 'hold'): raise ValidationError('end_mode must be manual0 or hold')
        if not isinstance(case_id, str): raise ValidationError('Test id must be a string')
        case = self.cases.get(case_id)
        if not case: raise ValidationError('Unknown test case')
        if timeout_ms is _CASE_TIMEOUT:
            timeout_ms = case['timeout_ms']
        elif type(timeout_ms) is not int or not 1000 <= timeout_ms <= 300000:
            raise ValidationError('timeout_ms must be an integer from 1000 to 300000')
        if case.get('requires_confirmation') and not mapping_under_test:
            raise ValidationError('This command/feedback mapping requires supplier confirmation')
        if end_mode == 'hold' and 'door' in case['command_tag'].lower():
            raise ValidationError('Door commands require manual0 mode')
        if (mapping_under_test or end_mode == 'hold') and case.get('reset_command'):
            raise ValidationError('Mapping-under-test and Hold runs do not support automatic reset commands')
        if self.lock.locked(): raise ValidationError('Another write or command dispatch is running')
        started = time.monotonic()
        command_at = None
        baseline_time = None
        run = {'run_id':uuid.uuid4().hex, 'case_id':case_id, 'command_tag':case['command_tag'],
               'feedback_tag':case['feedback_tag'], 'reset_command':case.get('reset_command'),
               'interrupted':asyncio.Event(), 'interrupt_reason':None}
        result = dict(test_name=case['name'], command=f"{case['command_tag']}={case['command_value']}",
                      expected_feedback=f"{case['feedback_tag']}={case['expected_feedback']}",
                      actual_feedback=None, command_readback=None, Remote=None, Local=None,
                      result='BLOCKED', elapsed_ms=0, http_status=None, error=None,
                      mapping_under_test=mapping_under_test, end_mode=end_mode, timeout_ms=timeout_ms,
                      command_address=None, write_dispatched=False, run_id=run['run_id'])
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
                self.logs.add('TEST_BASELINE', run_id=run['run_id'], test_name=case['name'], mapping_under_test=mapping_under_test,
                              end_mode=end_mode, supplier_timestamp=poll.get('timestamp'), poll_id=poll.get('id'),
                              actual_feedback=poll.get(case['feedback_tag']))

            def reserve(poll):
                check_baseline(poll)
                command = self.service.tags[case['command_tag']]
                feedback = self.service.tags[case['feedback_tag']]
                run.update(command_address=result['command_address'], feedback_address=feedback.device_address,
                           command_interpretation=(command.data_type, command.multiplier),
                           feedback_interpretation=(feedback.data_type, feedback.multiplier))
                self.service.reserve_test(run)

            def check_identity():
                command = self.service.tags.get(case['command_tag'])
                feedback = self.service.tags.get(case['feedback_tag'])
                if (not command or command.read_write != 'W' or command.device_address != run['command_address'] or
                        (command.data_type, command.multiplier) != run['command_interpretation'] or
                        not feedback or feedback.read_write != 'R' or feedback.device_address != run['feedback_address'] or
                        (feedback.data_type, feedback.multiplier) != run['feedback_interpretation']):
                    raise ValidationError('Command or feedback metadata changed during observation')

            async with self.lock:
                await self.service.load_tags()
                check_baseline(await self.service.read())
                def mark_dispatched():
                    result['write_dispatched'] = True
                write_response = await self.service.write(case['command_tag'], case['command_value'],
                                                          authorize=authorize, before_write=reserve,
                                                          on_dispatch=mark_dispatched, test_run=run['run_id'])
                command_at = time.monotonic()
                accepted_at = datetime.now(timezone.utc)
                result['http_status'] = 200
                if write_response.get('written') is not True:
                    result['result'] = 'FAIL'
                    result['error'] = 'Supplier did not confirm written=true'
                else:
                    result['write_response'] = {**write_response, 'console_accepted_at':accepted_at.isoformat(),
                                                'console_command_baseline_utc':baseline_time.isoformat()}
            if write_response.get('written') is True:
                deadline = command_at + timeout_ms / 1000
                while True:
                    if run['interrupted'].is_set():
                        result['result'] = 'INTERRUPTED'
                        result['error'] = run['interrupt_reason']
                        break
                    if authorize: authorize()
                    check_identity()
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        result['result'] = 'TIMEOUT'
                        break
                    reading = asyncio.create_task(self.service.read())
                    cleared = asyncio.create_task(run['interrupted'].wait())
                    try:
                        done, _ = await asyncio.wait((reading, cleared), timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
                        if cleared in done:
                            result['result'] = 'INTERRUPTED'
                            result['error'] = run['interrupt_reason']
                            break
                        if reading not in done:
                            result['result'] = 'TIMEOUT'
                            break
                        poll = reading.result()
                    finally:
                        for task in (reading, cleared):
                            if not task.done(): task.cancel()
                        await asyncio.gather(reading, cleared, return_exceptions=True)
                    if run['interrupted'].is_set():
                        result['result'] = 'INTERRUPTED'
                        result['error'] = run['interrupt_reason']
                        break
                    if time.monotonic() >= deadline:
                        result['result'] = 'TIMEOUT'
                        break
                    if authorize: authorize()
                    check_identity()
                    result.update(actual_feedback=poll.get(case['feedback_tag']),
                                  command_readback=poll.get(case['command_tag']), Remote=poll.get('Remote'), Local=poll.get('Local'))
                    self.logs.add('TEST_FEEDBACK', run_id=run['run_id'], test_name=case['name'], mapping_under_test=mapping_under_test,
                                  end_mode=end_mode, tag_name=case['feedback_tag'], value=result['actual_feedback'],
                                  supplier_timestamp=poll.get('timestamp'), poll_id=poll.get('id'),
                                  command_readback=result['command_readback'], Remote=result['Remote'], Local=result['Local'])
                    if not self.service.fresh(poll):
                        raise ValidationError('Feedback poll data is stale or incomplete')
                    if not self.service.remote(poll):
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
                    try:
                        await asyncio.wait_for(run['interrupted'].wait(), timeout=min(case['poll_interval_ms'] / 1000, remaining))
                    except TimeoutError:
                        pass
                if case.get('reset_command') and not run['interrupted'].is_set():
                    async with self.lock:
                        if not run['interrupted'].is_set():
                            check_identity()
                            reset = case['reset_command']
                            response = await self.service.write(reset['tag_name'], reset['value'], authorize=authorize,
                                                                test_run=run['run_id'])
                            if response.get('written') is not True:
                                raise ValidationError('Supplier did not confirm configured reset write')
                if run['interrupted'].is_set():
                    result['result'] = 'INTERRUPTED'
                    result['error'] = run['interrupt_reason']
        except asyncio.CancelledError:
            result['result'] = 'INTERRUPTED'
            result['error'] = 'Feedback observation was cancelled'
            raise
        except Exception as exc:
            if run['interrupted'].is_set():
                result['result'] = 'INTERRUPTED'
                result['error'] = run['interrupt_reason']
            else:
                result['result'] = 'COMMUNICATION ERROR' if hasattr(exc, 'status') or (result['write_dispatched'] and 'write_response' not in result) else 'BLOCKED'
                result['http_status'] = getattr(exc, 'status', result['http_status'])
                result['error'] = str(exc)
        finally:
            self.service.active_tests.pop(run['run_id'], None)
            result['elapsed_ms'] = round((time.monotonic() - (command_at or started)) * 1000)
            self.logs.add('TEST_FINISH', **result)
        return result
