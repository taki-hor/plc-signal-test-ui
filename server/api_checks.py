"""Persist binary API-cycle evidence. This observer never sends PLC commands."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import re
import uuid


def utcnow():
    return datetime.now(timezone.utc)


def signature(tag):
    return [tag.tag_name, tag.device_address, tag.data_type, tag.read_write, tag.multiplier]


class APIChecks:
    def __init__(self, path, logs, mode, api_address, cases):
        self.path, self.logs = path, logs
        self.context = {'mode':mode, 'api_address':api_address}
        self.cases = cases
        self.records = {}
        self.error = None
        try:
            saved = json.loads(path.read_text())['records'] if path.exists() else []
            for record in saved:
                key = (record['context']['mode'], record['context']['api_address'], record['tag_name'])
                if record.get('pending'):
                    record.update(api_status='failed', failure='Backend restarted before API verification finished.')
                self.records[key] = record
        except (OSError, ValueError, KeyError, TypeError):
            self.error = 'Saved API check evidence could not be read.'

    def key(self, name):
        return (self.context['mode'], self.context['api_address'], name)

    def save(self, record):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps({'records':list(self.records.values())}, indent=2)+'\n')
        temporary.replace(self.path)
        self.logs.add('TEST_API_CHECK', tag_name=record['tag_name'], result=record['api_status'],
                      error=record.get('failure'), phase=record['phase'], api_check=record)

    def feedback(self, name):
        case = next((case for case in self.cases if case['command_tag']==name and case['command_value']==1), None)
        if case:
            return case['feedback_tag']
        if name=='MainInlet':
            return 'MainInletStatus'
        if name.endswith(('_AirAgitationOn','_CoolerOn')):
            return re.sub(r'On$', 'Status', name)
        return None

    def prepare(self, service, tag, value):
        if tag.data_type!='Bool' or value not in (0,1):
            return None
        if value==0:
            record = self.records.get(self.key(tag.tag_name))
            if not record or not record.get('pending'):
                return None
            return {'record':record,'value':0,'baseline_utc':service.poll_time().isoformat()}
        feedback_name = self.feedback(tag.tag_name)
        feedback = service.tags.get(feedback_name) if feedback_name else None
        names = [item.device_address for item in service.tags.values()]
        eligible = service.last_poll.get(tag.tag_name)==0 and names.count(tag.device_address)==1
        if feedback_name:
            eligible = bool(eligible and feedback and feedback.read_write=='R' and feedback.data_type=='Bool'
                            and names.count(feedback.device_address)==1 and service.last_poll.get(feedback_name)==0)
        record = {'id':uuid.uuid4().hex,'tag_name':tag.tag_name,'context':dict(self.context),
                  'identity':signature(tag),'feedback_tag':feedback_name,
                  'feedback_identity':signature(feedback) if feedback else None,
                  'feedback_clear_required':bool(feedback_name and not re.search(r'Door(?:Opened|Closed)$',feedback_name)),
                  'started_at':utcnow().isoformat(),'api_status':'unchecked','phase':'one','pending':True,
                  'eligible':eligible,'basis':'Command and related status' if feedback_name else 'Command readback only',
                  'failure':None,'one':None,'zero':None}
        previous = self.records.get(self.key(tag.tag_name))
        if previous and previous['api_status']=='unchecked':
            previous = previous.get('previous_result')
        if (previous and previous['api_status'] in ('checked','failed') and previous['context']==self.context
                and self.identity_matches(service,previous) and previous.get('feedback_tag')==feedback_name
                and (previous['api_status']=='failed' or self.complete(previous))):
            record['previous_result'] = deepcopy({k:v for k,v in previous.items() if k!='previous_result'})
        return {'record':record,'value':1,'baseline_utc':service.poll_time().isoformat()}

    def accepted(self, draft, response):
        if not draft:
            return
        record, value = draft['record'], draft['value']
        valid = (isinstance(response,dict) and response.get('written') is True
                 and response.get('tag_name')==record['tag_name'] and type(response.get('value')) in (int,float)
                 and response['value']==value and response.get('device_address')==record['identity'][1]
                 and response.get('data_type')==record['identity'][2] and response.get('read_write')==record['identity'][3]
                 and response.get('multiplier',1)==record['identity'][4])
        step = {'accepted_at':utcnow().isoformat(),'baseline_utc':draft['baseline_utc'],
                'receipt_valid':valid,'observed':None}
        record['one' if value else 'zero'] = step
        record['phase'] = 'one' if value else 'zero'
        if not valid:
            record['failure'] = 'Write receipt did not confirm the reviewed tag, address and value.'
        elif value==0 and not record['failure'] and not (record.get('one') or {}).get('observed'):
            record['failure'] = ('Command 1 readback verified; required status '+str(record.get('feedback_tag'))+' was not observed at 1 before Send 0.' if record.get('command_one_seen_at') else 'Write acknowledged, but command 1 readback was not verified before Send 0.')
        if record['failure']:
            record['api_status'] = 'failed'
        self.records[self.key(record['tag_name'])] = record
        self.save(record)

    def failed_write(self, draft, error):
        if not draft:
            return
        record = draft['record']
        record.update(api_status='failed',failure='Write outcome requires review: '+str(error))
        self.records[self.key(record['tag_name'])] = record
        self.save(record)

    def blocked_clear(self, name, value):
        record = self.records.get(self.key(name)) if isinstance(name,str) else None
        if value==0 and record and record.get('pending'):
            record.update(api_status='failed',failure='Send 0 was blocked before dispatch; restoration is not verified.')
            self.save(record)

    def identity_matches(self, service, record):
        tag = service.tags.get(record['tag_name'])
        feedback = service.tags.get(record.get('feedback_tag'))
        return (tag is not None and signature(tag)==record['identity']
                and (not record.get('feedback_tag') or feedback is not None and signature(feedback)==record['feedback_identity']))

    def observe(self, service, poll):
        if not service.fresh(poll) or not service.remote(poll) or poll.get('Local')!=0:
            return
        stamp = service.poll_time(poll)
        for record in self.records.values():
            if record['context']!=self.context or not record.get('pending') or not self.identity_matches(service,record):
                continue
            phase = record['phase']
            step = record.get(phase)
            if phase not in ('one','zero') or not step or not step['receipt_valid'] or step.get('observed'):
                continue
            if not (stamp>datetime.fromisoformat(step['accepted_at']) and stamp>datetime.fromisoformat(step['baseline_utc'])):
                continue
            value = 1 if phase=='one' else 0
            feedback_value = poll.get(record['feedback_tag']) if record.get('feedback_tag') else None
            if poll.get(record['tag_name'])!=value:
                continue
            first_one = phase=='one' and not record.get('command_one_seen_at')
            if first_one:
                record['command_one_seen_at'] = stamp.isoformat()
            if record.get('feedback_tag') and (phase=='one' or record['feedback_clear_required']) and feedback_value!=value:
                if first_one: self.save(record)
                continue
            step['observed'] = {'supplier_utc':stamp.isoformat(),'command_value':value,'feedback_value':feedback_value,'fresh':True,'Remote':poll.get('Remote'),'Local':poll.get('Local')}
            if phase=='zero':
                record['pending'] = False
                complete = (record['eligible'] and not record['failure'] and bool((record.get('one') or {}).get('observed')))
                record['api_status'] = 'checked' if complete else 'failed' if record['failure'] else 'unchecked'
                record['checked_at'] = utcnow().isoformat()
                if not record['eligible'] and not record['failure']:
                    record['failure'] = 'A zero baseline or independent metadata mapping was not available.'
            self.save(record)

    def complete(self, record):
        try:
            for phase, value in [('one',1),('zero',0)]:
                step = record[phase]; sample = step['observed']
                stamp = datetime.fromisoformat(sample['supplier_utc'])
                accepted = datetime.fromisoformat(step['accepted_at']); baseline = datetime.fromisoformat(step['baseline_utc'])
                if not (stamp.tzinfo and accepted.tzinfo and baseline.tzinfo and step['receipt_valid'] is True
                        and sample['fresh'] is True and sample['command_value']==value and sample.get('Remote')==1 and sample.get('Local')==0
                        and stamp>accepted and stamp>baseline):
                    return False
                if record.get('feedback_tag') and (phase=='one' or record.get('feedback_clear_required')) and sample['feedback_value']!=value:
                    return False
            return record['eligible'] is True and not record.get('failure')
        except (KeyError, TypeError, ValueError):
            return False

    def public(self, service):
        rows = []
        for record in self.records.values():
            if record['context']!=self.context:
                continue
            tag = service.tags.get(record['tag_name'])
            if not tag or tag.read_write!='W':
                continue
            valid = self.identity_matches(service,record)
            if record.get('pending') and record['phase']=='zero' and record.get('zero'):
                if (utcnow()-datetime.fromisoformat(record['zero']['accepted_at'])).total_seconds()>15 and not record.get('failure'):
                    record.update(api_status='failed',failure='Restoration was not verified within 15 seconds.')
                    self.save(record)
            state = record['api_status'] if valid else 'unchecked'
            if state=='checked' and not self.complete(record):
                state='unchecked'
            waiting = 'Awaiting fresh command 1 and required status.' if record['phase']=='one' and not (record.get('one') or {}).get('observed') else 'Awaiting verified restoration to 0.'
            detail = record.get('failure') or (waiting if record.get('pending') else record['basis'])
            displayed = record
            previous = record.get('previous_result')
            if (valid and record['api_status']=='unchecked' and previous
                    and previous['context']==self.context and self.identity_matches(service,previous)
                    and previous.get('feedback_tag')==record.get('feedback_tag')
                    and (previous['api_status']=='failed' or previous['api_status']=='checked' and self.complete(previous))):
                displayed, state = previous, previous['api_status']
                label = 'API pass' if state=='checked' else 'API fail'
                detail = f"Previous {label} retained: {previous.get('failure') or previous['basis']}. Current attempt: {detail}"
            if valid and record['api_status']=='checked' and state=='unchecked': detail='Saved evidence does not prove a complete API cycle.'
            if not valid:
                detail = 'Metadata changed; previous API check no longer applies.'
            rows.append({'tag_name':record['tag_name'],'api_status':state,'checked_at':displayed.get('checked_at'),
                         'started_at':displayed['started_at'],'basis':displayed['basis'],'detail':detail,
                         'current_started_at':record['started_at'],'retained_result':displayed is not record,
                         'pending':record.get('pending',False),'identity':record['identity'],'identity_valid':valid,
                         'feedback_tag':record.get('feedback_tag'),
                         'command_one_seen':bool(record.get('command_one_seen_at') or (record.get('one') or {}).get('observed'))})
        return {'records':rows if not self.error else [],'error':self.error,'context':dict(self.context)}
