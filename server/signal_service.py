import asyncio
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .models import Tag, ValidationError
from .plc_client import PLCError
from .catalog_diagnostics import catalog_warnings

class SignalService:
    def __init__(self, client, logs, stale_ms, baseline=None, timestamp_timezone=None, timestamp_offset_seconds=0):
        self.client, self.logs, self.stale_ms = client, logs, stale_ms
        self.baseline = baseline
        self.command_lock = asyncio.Lock()
        self.active_tests = {}
        self.timestamp_timezone = ZoneInfo(timestamp_timezone) if timestamp_timezone else None
        self.timestamp_offset_seconds = timestamp_offset_seconds
        self.catalog_warnings = []
        self.tags = {}
        self.last_poll = None
        self.last_success = None
        self.last_error = None

    async def load_tags(self):
        try:
            raw = await self.client.list_tags()
            tags = [Tag.parse(item) for item in raw['tags']]
            if len({tag.tag_name for tag in tags}) != len(tags):
                raise ValidationError('Supplier returned duplicate tag names')
            self.tags = {tag.tag_name: tag for tag in tags}
            warnings = catalog_warnings(tags, self.baseline)
            if warnings != self.catalog_warnings:
                self.logs.add('CATALOG_DIAGNOSTICS', result='WARNING' if warnings else 'OK', warnings=warnings)
            self.catalog_warnings = warnings
            self.success('TAGS', count=len(tags))
            return tags
        except Exception as exc:
            self.failure('TAGS', exc)
            raise

    async def read(self):
        try:
            poll = await self.client.read_signals()
            if not isinstance(poll, dict) or 'timestamp' not in poll:
                raise ValidationError('Supplier poll response lacks timestamp')
            self.last_poll = poll
            missing = [name for name in self.tags if poll.get(name) is None]
            self.success('READ', supplier_timestamp=poll.get('timestamp'), poll_count=poll.get('poll_count'),
                         tags_ok=poll.get('tags_ok'), tags_failed=poll.get('tags_failed'), failed_tags=missing)
            return poll
        except Exception as exc:
            self.failure('READ', exc)
            raise

    def success(self, event, **data):
        self.last_success = datetime.now(timezone.utc).isoformat()
        self.last_error = None
        self.logs.add(event, result='OK', **data)

    def failure(self, event, exc, **data):
        self.last_error = str(exc)
        self.logs.add(event, result='ERROR', http_status=getattr(exc, 'status', None), error=str(exc), detail=getattr(exc, 'detail', ''), **data)

    def poll_time(self, poll=None):
        poll = self.last_poll if poll is None else poll
        if not poll: return None
        try:
            stamp = datetime.fromisoformat(str(poll['timestamp']).replace('Z', '+00:00'))
            if stamp.tzinfo is None:
                if self.timestamp_timezone is None: return None
                stamp = stamp.replace(tzinfo=self.timestamp_timezone)
            return stamp.astimezone(timezone.utc) + timedelta(seconds=self.timestamp_offset_seconds)
        except (KeyError, TypeError, ValueError, OverflowError): return None

    def age_ms(self, poll=None):
        stamp = self.poll_time(poll)
        if stamp is None: return None
        age = round((datetime.now(timezone.utc) - stamp).total_seconds() * 1000)
        return None if age < -self.stale_ms else max(0, age)

    def fresh(self, poll=None):
        poll = self.last_poll if poll is None else poll
        age = self.age_ms(poll)
        return (age is not None and age <= self.stale_ms and poll.get('tags_failed', 0) == 0
                and all(poll.get(name) is not None for name in self.tags))

    def remote(self, poll=None):
        poll = self.last_poll if poll is None else poll
        return bool(poll and poll.get('Remote') == 1)

    @staticmethod
    def door_resource(tag_name):
        match = re.fullmatch(r'(Tank\d+)_Door(?:Open|Close)Remote', tag_name)
        return match.group(1) if match else None

    def reserve_test(self, run):
        names = {run['command_tag'], run['feedback_tag']}
        addresses = {run['command_address'], run['feedback_address']}
        door = self.door_resource(run['command_tag'])
        for active in self.active_tests.values():
            if (run['reset_command'] or active['reset_command'] or
                    names.intersection((active['command_tag'], active['feedback_tag'])) or
                    addresses.intersection((active['command_address'], active['feedback_address'])) or
                    door and door == self.door_resource(active['command_tag'])):
                raise ValidationError(f"Command conflicts with active feedback test {active['case_id']}")
        self.active_tests[run['run_id']] = run

    def check_test_writes(self, writes, owner=None):
        interrupted = []
        for tag, value in writes:
            door = self.door_resource(tag.tag_name)
            for active in self.active_tests.values():
                if active['run_id'] == owner: continue
                same_command = tag.tag_name == active['command_tag'] or tag.device_address == active['command_address']
                if (active['reset_command'] or same_command or tag.tag_name == active['feedback_tag'] or
                        tag.device_address == active['feedback_address'] or
                        door and door == self.door_resource(active['command_tag'])):
                    if value == 0 and same_command:
                        if active not in interrupted: interrupted.append(active)
                    else:
                        raise ValidationError(f"Command conflicts with active feedback test {active['case_id']}")
        return interrupted

    @staticmethod
    def interrupt_tests(tests):
        for active in tests:
            active['interrupt_reason'] = 'The command was manually cleared during feedback observation'
            active['interrupted'].set()

    async def validate_write(self, tag_name, value):
        try:
            await self.load_tags()  # refresh supplier permission and limits before each write
            tag = self.tags.get(tag_name)
            if not tag: raise ValidationError(f'Unknown tag: {tag_name}')
            value = tag.validate_write(value)
            await self.read()  # a recent HTTP response can still contain stale PLC data
            if not self.fresh(): raise ValidationError('PLC data is stale, incomplete, or has no timezone; write blocked')
            if not self.remote(): raise ValidationError('PLC is not in Remote/API mode; write blocked')
        except PLCError as exc:
            exc.write_dispatched = False
            raise
        return tag, value

    async def write(self, tag_name, value, authorize=None, before_write=None, on_dispatch=None, test_run=None):
        try:
            tag, value = await self.validate_write(tag_name, value)
            if self.tags.get(tag_name) != tag:
                raise ValidationError('Command metadata changed during write validation')
            if before_write: before_write(self.last_poll)
            if authorize: authorize()
            interrupted = self.check_test_writes([(tag, value)], owner=test_run)
        except Exception as exc:
            exc.write_dispatched = False
            raise
        try:
            if on_dispatch: on_dispatch()
            self.interrupt_tests(interrupted)
            response = await self.client.write_signal(tag_name, value)
            if not isinstance(response, dict):
                raise PLCError(502, 'Supplier write response is not an object. Inspect the command before retrying.')
            response = {**response, 'console_command_address': tag.device_address}
            self.logs.add('WRITE', tag_name=tag_name, value=value, address=tag.device_address, result='ACCEPTED' if response.get('written') is True else 'REJECTED', http_status=200)
            return response
        except Exception as exc:
            exc.write_dispatched = True
            self.failure('WRITE', exc, tag_name=tag_name, value=value)
            raise

    async def write_batch(self, writes, authorize=None, before_write=None):
        if not 1 <= len(writes) <= 100: raise ValidationError('Batch requires 1 to 100 writes')
        if any(not isinstance(item, dict) or not isinstance(item.get('tag_name'), str) or not item['tag_name'] for item in writes):
            raise ValidationError('Each batch item requires a non-empty tag_name string')
        names = [item.get('tag_name') for item in writes]
        if len(set(names)) != len(names): raise ValidationError('Duplicate tag names in batch')
        try:
            await self.load_tags()
            validated = []
            metadata = []
            for item in writes:
                tag = self.tags.get(item.get('tag_name'))
                if not tag: raise ValidationError(f"Unknown tag: {item.get('tag_name')}")
                validated.append({'tag_name': tag.tag_name, 'value': tag.validate_write(item.get('value'))})
                metadata.append(tag)
            await self.read()
            if not self.fresh() or not self.remote(): raise ValidationError('Fresh Remote/API mode data required for batch write')
            if any(self.tags.get(tag.tag_name) != tag for tag in metadata):
                raise ValidationError('Command metadata changed during batch validation')
            if before_write: before_write(self.last_poll)
            if authorize: authorize()
            interrupted = self.check_test_writes([(tag, item['value']) for tag, item in zip(metadata, validated)])
        except PLCError as exc:
            exc.write_dispatched = False
            raise
        try:
            self.interrupt_tests(interrupted)
            response = await self.client.write_batch(validated)
            self.logs.add('WRITE_BATCH', writes=validated, result='ACCEPTED', http_status=200)
            return response
        except Exception as exc:
            exc.write_dispatched = True
            self.failure('WRITE_BATCH', exc)
            raise
