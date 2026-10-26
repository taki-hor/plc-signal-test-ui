#!/usr/bin/env python3
"""Preview every writable Swagger/catalog tag; execute only with operator input."""
import argparse
import asyncio
import csv
from datetime import datetime
import inspect
import json
import math
from pathlib import Path
import re
import sys
import time
from urllib.parse import urlsplit
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.config import Settings
from server.log_service import LogService
from server.models import Tag, ValidationError
from server.plc_client import PLCClient, PLCError
from server.signal_service import SignalService
from tools.human_line_test import CleanupLogs, now, read_ready, read_verdict, signature


async def ask(callback, prompt):
    answer = callback(prompt)
    return await answer if inspect.isawaitable(answer) else answer


def physical_tank(name):
    match = re.match(r'Tank(\d+)', name)
    if not match: return 0
    return 13 if re.match(r'Tank12_Door(?:Open|Close)Remote$', name) else int(match[1])


def inventory(catalog=None, schema=None, pdf=None):
    catalog = catalog or json.loads((ROOT/'docs/source/supplier-tags-2026-10-23.json').read_text())
    schema = schema or json.loads((ROOT/'docs/source/supplier-openapi-2026-10-23.json').read_text())
    for path, method in [('/api/v1/tags/list','get'),('/api/v1/tags/read','get'),('/api/v1/tags/write','post')]:
        if method not in schema.get('paths',{}).get(path,{}): raise ValueError('Saved Swagger does not define '+method+' '+path)
    tags = {tag.tag_name:tag for tag in (Tag.parse(row) for row in catalog['tags'])}
    pdf = pdf or json.loads((ROOT/'config/mock-tags.json').read_text())
    pdf_tags = {tag.tag_name:tag for tag in (Tag.parse(row) for row in pdf['tags'])}
    local = json.loads((ROOT/'config/test-cases.json').read_text())['tests']
    cases = []
    for tag in tags.values():
        if tag.read_write != 'W': continue
        name = tag.tag_name
        feedback = next((c['feedback_tag'] for c in local if c['command_tag']==name and c['command_value']==1), None)
        if name=='MainInlet': feedback='MainInletStatus'
        if name.endswith(('_AirAgitationOn','_CoolerOn')): feedback=name[:-2]+'Status'
        feedback_tag = tags.get(feedback)
        aliases = {other.tag_name for other in tags.values() if other.device_address==tag.device_address}
        feedback_aliases = {other.tag_name for other in tags.values() if feedback_tag and other.device_address==feedback_tag.device_address}
        source_pdf = pdf_tags.get(name)
        prefixes={alias.split('_',1)[0]+'_' for alias in aliases|feedback_aliases}
        kind = 'numeric' if tag.data_type!='Bool' else 'door' if '_Door' in name else 'auto' if name.endswith('Auto') else 'command'
        cases.append({'tag_name':name,'identity':signature(tag),'description':tag.description,'tank':physical_tank(name),
                      'kind':kind,'feedback_tag':feedback if feedback_tag else None,
                      'feedback_identity':signature(feedback_tag) if feedback_tag else None,
                      'aliases':sorted(aliases),'feedback_aliases':sorted(feedback_aliases),
                      'pdf_limits':[source_pdf.low_limit,source_pdf.high_limit] if source_pdf else [None,None],
                      'pdf_identity':signature(source_pdf) if source_pdf else None,
                      'watched_identities':{other.tag_name:signature(other) for other in tags.values() if any(other.tag_name.startswith(prefix) for prefix in prefixes) and other.data_type=='Bool' and (other.read_write=='W' or other.tag_name.endswith('Status'))}})
    cases.sort(key=lambda c:(c['tank'],re.sub(r'(?:Auto|On|Remote)$','',c['tag_name'].split('_',1)[-1]).lower(),c['tag_name'].endswith('Auto'),c['tag_name']))
    return {'format':'swagger-line-plan-v1','cases':cases,'catalog_count':len(tags)}


def local_origin(origin):
    parsed=urlsplit(origin)
    if (parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','::1') or parsed.username or parsed.password
            or parsed.path not in ('','/') or parsed.query or parsed.fragment):
        raise ValueError('App origin must be literal HTTP loopback, for example http://127.0.0.1:8080')
    return origin.rstrip('/')


class AppClient:
    """The local HTTP write path used by the UI, without browser automation."""
    def __init__(self, origin, supplier, timeout, transport=None):
        self.origin=local_origin(origin);self.supplier=supplier;self.token=None;self.expiry=0;self.last_dispatch=False
        self.client=httpx.AsyncClient(base_url=self.origin,timeout=max(20,timeout*3),trust_env=False,
                                      follow_redirects=False,transport=transport)

    async def request(self, method, path, body=None):
        headers={'X-Write-Token':self.token} if self.token else {}
        try:
            response=await self.client.request(method,path,json=body,headers=headers)
            try: data=response.json()
            except ValueError: data={}
            if not response.is_success:
                detail='Local app request failed'
                if isinstance(data,dict):detail=data.get('error') or data.get('detail') or detail
                if not isinstance(detail,str):detail=json.dumps(detail)
                if self.token:detail=detail.replace(self.token,'[REDACTED]')
                error=PLCError(response.status_code,detail)
                if isinstance(data,dict) and data.get('write_dispatched') is False:
                    error.write_dispatched=False;self.last_dispatch=False
                raise error
            if not isinstance(data,dict): raise PLCError(502,'Invalid local app response')
            return data
        except httpx.HTTPError as exc:
            raise PLCError(502,'Local app communication failed') from exc

    async def context(self):
        status=await self.request('GET','/api/status')
        if status.get('mode')!='REAL' or status.get('api_address')!=self.supplier:
            error=ValidationError('Local app must use REAL mode and the same supplier origin')
            error.write_dispatched=False;self.last_dispatch=False
            raise error
        return status

    async def list_tags(self):
        await self.context()
        return await self.request('GET','/api/tags')

    async def read_signals(self):
        poll=await self.request('GET','/api/signals')
        await self.context()
        return poll

    async def write_signal(self,name,value):
        self.last_dispatch=False
        await self.context()
        if not self.token or time.monotonic()>=self.expiry-30:
            previous=self.token
            enabled=await self.request('POST','/api/mode/enable')
            token=enabled.get('write_token');seconds=enabled.get('expires_seconds')
            if not isinstance(token,str) or not token or type(seconds) not in (int,float) or not math.isfinite(seconds) or seconds<=30:
                raise ValidationError('Local app did not supply a valid own write token')
            self.token=token;self.expiry=time.monotonic()+seconds
            if previous:
                current=self.token;self.token=previous
                try: await self.request('POST','/api/mode/disable')
                finally:self.token=current
        self.last_dispatch=True
        return await self.request('POST','/api/write',{'tag_name':name,'value':value})

    async def close(self):
        try:
            if self.token: await self.request('POST','/api/mode/disable')
        finally:
            self.token=None
            await self.client.aclose()


def validate_number(tag,value,limits):
    value=tag.validate_write(value)
    low,high=limits
    if low is not None and value<low or high is not None and value>high:
        raise ValidationError('Numeric test is outside the published PDF safety envelope')
    scaled=value/tag.multiplier
    bounds={'Word':(0,65535),'SignedWord':(-32768,32767)}.get(tag.data_type)
    if bounds and (not math.isclose(scaled,round(scaled),abs_tol=1e-7) or not bounds[0]<=round(scaled)<=bounds[1]):
        raise ValidationError('Value cannot be represented by the tag type and multiplier')
    return value


class SwaggerLineTest:
    def __init__(self, services, logs, output, *, verdict=read_verdict, ready=read_ready, prompt=input, wait_seconds=15, emit=print):
        self.services=services;self.logs=CleanupLogs(logs);self.output=Path(output)
        for service in services.values():service.logs=self.logs
        self.verdict,self.ready,self.prompt=verdict,ready,prompt
        self.wait_seconds=wait_seconds;self.results=[]
        self.emit=lambda message:emit(logs.scrub(str(message)))

    def check(self,service,poll):
        if not service.fresh(poll) or poll.get('Remote')!=1 or poll.get('Local')!=0:
            raise ValidationError('Fresh complete Remote=1 Local=0 data is required')

    @staticmethod
    def opposite(case):
        return case['tag_name'].replace('DoorOpenRemote','DoorCloseRemote') if 'DoorOpenRemote' in case['tag_name'] else case['tag_name'].replace('DoorCloseRemote','DoorOpenRemote')

    def guard(self,service,case,baseline=None,target_only=False):
        def before(poll):
            self.check(service,poll)
            for field,name in [('identity',case['tag_name'])]+([] if target_only else [('feedback_identity',case['feedback_tag'])]):
                if name and (name not in service.tags or signature(service.tags[name])!=case[field]):
                    raise ValidationError('Reviewed metadata changed: '+name)
            for field,name in [('aliases',case['tag_name'])]+([] if target_only else [('feedback_aliases',case['feedback_tag'])]):
                if name:
                    current=sorted(t.tag_name for t in service.tags.values() if t.device_address==service.tags[name].device_address)
                    if current!=case[field]:raise ValidationError('Alias mapping changed: '+name)
            for name,identity in ([] if target_only else case['watched_identities'].items()):
                if name not in service.tags or signature(service.tags[name])!=identity:
                    raise ValidationError('Related command/status metadata changed: '+name)
            if baseline is not None and case['kind']=='door' and poll.get(self.opposite(case))!=0:
                raise ValidationError('Opposite door command is active; test blocked')
            if baseline is not None and not self.equal(service.tags[case['tag_name']],poll.get(case['tag_name']),baseline):
                raise ValidationError('Command baseline changed; existing state is preserved')
        return before

    @staticmethod
    def equal(tag,a,b):
        return type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a) and math.isfinite(b) and math.isclose(a,b,rel_tol=0,abs_tol=max(1e-9,tag.multiplier*1e-6))

    async def prepare(self,service,case):
        await service.load_tags();poll=await service.read();self.guard(service,case)(poll)
        baseline=poll.get(case['tag_name'])
        if type(baseline) not in (int,float) or not math.isfinite(baseline):raise ValidationError('Missing finite baseline')
        if case['kind']!='numeric' and baseline!=0:raise ValidationError('Existing command is not0; leave it unchanged')
        if case['kind']=='door' and poll.get(self.opposite(case))!=0:raise ValidationError('Opposite door command is active; test blocked')
        if case['kind']=='auto':
            for alias in case['aliases']:
                for suffix in ('On','Status'):
                    name=re.sub('Auto$',suffix,alias)
                    if name in service.tags and poll.get(name)!=0:raise ValidationError('Related Auto output is already active: '+name)
        return poll

    def receipt(self,response,tag,value):
        return (isinstance(response,dict) and response.get('written') is True and response.get('tag_name')==tag.tag_name
                and self.equal(tag,response.get('value'),value)
                and [response.get(k,1 if k=='multiplier' else None) for k in ('tag_name','device_address','data_type','read_write','multiplier')]==signature(tag))

    async def observe(self,service,case,value,bounds,row,phase,expected):
        deadline=asyncio.get_running_loop().time()+self.wait_seconds
        readback=False;last=None
        while asyncio.get_running_loop().time()<deadline:
            remaining=deadline-asyncio.get_running_loop().time()
            try:poll=await asyncio.wait_for(service.read(),remaining)
            except TimeoutError:break
            metadata_error=None
            if phase=='restore':
                self.guard(service,case,target_only=True)(poll)
                try:self.guard(service,case)(poll)
                except ValidationError as exc:metadata_error=str(exc)
            else:self.guard(service,case)(poll)
            stamp=service.poll_time(poll)
            later=all(stamp>datetime.fromisoformat(bound) for bound in bounds)
            sample={'supplier_utc':stamp.isoformat(),'values':{name:poll.get(name) for name in expected},'fresh':True,'Remote':poll.get('Remote'),'Local':poll.get('Local')}
            self.logs.add('TEST_SWAGGER_SAMPLE',tag_name=case['tag_name'],path=row['path'],phase=phase,sample=sample,poll=poll)
            last=sample
            if phase=='test' and self.logs.error:raise OSError(self.logs.error)
            if later and self.equal(service.tags[case['tag_name']],poll.get(case['tag_name']),value):
                readback=True;row.setdefault(phase+'_readback_sample',sample)
            if metadata_error:
                row['restoration_error']='Status proof invalid after metadata change: '+metadata_error
                if later and readback:return True,False
                await asyncio.sleep(min(.25,max(0,deadline-asyncio.get_running_loop().time())))
                continue
            if later and all(self.equal(service.tags[name],poll.get(name),wanted) for name,wanted in expected.items()):
                row[phase+'_sample']=sample
                return True,True
            await asyncio.sleep(min(.25,max(0,deadline-asyncio.get_running_loop().time())))
        row[phase+'_last_sample']=last
        return readback,False

    async def inputs(self,case,service,baseline):
        if len(case['aliases'])>1 or len(case['feedback_aliases'])>1:
            self.emit('Shared addresses: '+', '.join(case['aliases']+case['feedback_aliases']))
            if (await ask(self.prompt,'Confirm ALL affected equipment/aliases are understood; type ALIASES or S to skip: ')).strip()!='ALIASES':
                return None,'Shared-address operation was not confirmed'
        if case['kind']=='numeric':
            self.emit(f'{case["tag_name"]}: original={baseline}; PDF safety bounds={case["pdf_limits"]}')
            raw=(await ask(self.prompt,'Enter an approved engineering test value, or S to skip: ')).strip()
            if raw.lower()=='s':return None,'No approved numeric value supplied'
            try:value=validate_number(service.tags[case['tag_name']],float(raw),case['pdf_limits'])
            except (ValueError,OverflowError) as exc:return None,str(exc)
            if self.equal(service.tags[case['tag_name']],value,baseline):return None,'Test value equals baseline; no changed-value test'
            validate_number(service.tags[case['tag_name']],baseline,case['pdf_limits'])
            return value,None
        if case['kind']=='door' or case['tag_name']=='MainInlet' or case['tag_name'].endswith('RemoteStart'):
            self.emit('Confirm the actual procedure: hold1 until the requested action finishes, then restore0. Unknown procedure must be skipped.')
            if (await ask(self.prompt,'Equipment clear, observer ready, reset rule confirmed: type HOLD or S to skip: ')).strip()!='HOLD':
                return None,'Hold/reset procedure not confirmed'
        return 1,None

    async def write(self,service,case,value,baseline,row,phase):
        captured={}
        def before(poll):
            if phase=='test' and self.logs.error:raise OSError(self.logs.error)
            self.guard(service,case,baseline if phase=='test' else None,target_only=phase=='restore')(poll)
            if phase=='restore' and case['kind']=='numeric' and not any(self.equal(service.tags[case['tag_name']],poll.get(case['tag_name']),candidate) for candidate in (row['test_value'],value)):
                raise ValidationError('Numeric value changed outside this test; do not overwrite it')
            captured['baseline']=service.poll_time(poll).isoformat()
        dispatched=False
        def on_dispatch():
            nonlocal dispatched
            dispatched=True
        try:
            receipt=await service.write(case['tag_name'],value,before_write=before,on_dispatch=on_dispatch)
        except asyncio.CancelledError:
            row[phase+'_dispatch_unknown']=True
            raise
        except Exception as exc:
            possible=dispatched and getattr(exc,'write_dispatched',None) is not False
            if isinstance(service.client,AppClient):possible=dispatched and service.client.last_dispatch
            row[phase+'_dispatch_unknown']=possible
            raise
        row[phase+'_receipt']=receipt;received=now();row[phase+'_received_at']=received
        if not self.receipt(receipt,service.tags[case['tag_name']],value):
            row[phase+'_dispatch_unknown']=True
            raise ValidationError('Write receipt does not confirm the reviewed tag/address/value')
        row[phase+'_acknowledged']=True
        bounds=[captured['baseline'],received]
        for field in ('console_command_baseline_utc','console_accepted_at'):
            if isinstance(service.client,AppClient):
                stamp=receipt.get(field)
                if not isinstance(stamp,str) or not datetime.fromisoformat(stamp).tzinfo:
                    row[phase+'_dispatch_unknown']=True
                    raise ValidationError('Local app receipt lacks final pre-write evidence')
                bounds.append(stamp)
        row[phase+'_bounds']=bounds
        return bounds

    async def run_path(self,case,path,value,original,reference):
        service=self.services[path];name=case['tag_name']
        row={'tag_name':name,'tank':case['tank'],'kind':case['kind'],'path':path,'started_at':now(),
             'reviewed_identity':case['identity'],'pdf_identity':case['pdf_identity'],'pdf_limits':case['pdf_limits'],
             'test_value':value,'original_value':original,'request':'not_sent','readback':'not_checked',
             'output':'not_checked','human_result':'unchecked','physical_stop_verified':False,
             'restored':False,'continue_queue':False}
        self.results.append(row)
        possible=False;uncertain=False;quit_requested=False
        try:
            baseline=await self.prepare(service,case)
            if not self.equal(service.tags[name],baseline[name],original):raise ValidationError('Paths do not have the same original command value')
            row['baseline']=baseline
            self.logs.add('TEST_SWAGGER_INTENT',tag_name=name,path=path,value=value,identity=case['identity'])
            if self.logs.error:raise OSError(self.logs.error)
            possible=True
            bounds=await self.write(service,case,value,original,row,'test')
            row['request']='acknowledged'
            expected={alias:value for alias in case['aliases']}
            feedback=case['feedback_tag']
            already_set=bool(feedback and baseline.get(feedback)==1)
            if feedback:expected.update({alias:1 for alias in case['feedback_aliases']})
            command,output=await self.observe(service,case,value,bounds,row,'test',expected)
            row['readback']='verified' if command else 'not_observed'
            row['output']=('mode_only' if case['kind']=='auto' else 'no_mapping' if not feedback else 'already_set' if already_set
                           else 'shared_mapping_unconfirmed' if len(case['feedback_aliases'])>1 else 'confirmed' if output else 'unconfirmed')
            row['preconditions_changed_between_paths']=reference is not None and self.conditions(case,baseline)!=self.conditions(case,reference)
            self.emit(f'{name} [{path}]: request={row["request"]}; readback={row["readback"]}; output={row["output"]}')
            if case['kind']=='auto':self.emit('Mode-bit test only. Automatic operation/trigger is unspecified; no movement is not an API failure or a physical Pass.')
            if case['kind']=='door':self.emit('Wait for movement to finish before choosing a result and clearing the command. Position feedback may stay latched.')
            self.emit('P=confirmed physical/mode result; I=incorrect action; N=unconfirmed/no response; Q=restore then stop.')
            key=await ask(self.verdict,'Press P / I / N / Q (requests restoration): ')
            if key not in ('p','i','n','q'):raise ValueError('Invalid human verdict')
            row['human_result']={'p':'pass','i':'fail','n':'unchecked','q':'unchecked'}[key]
            row['human_observation']={'p':'confirmed','i':'incorrect','n':'unconfirmed','q':'not_checked'}[key]
            row['human_at']=now();quit_requested=key=='q'
        except (Exception,KeyboardInterrupt,EOFError,asyncio.CancelledError) as exc:
            possible=possible and (row.get('test_acknowledged') or row.get('test_dispatch_unknown',True))
            uncertain=possible and not row.get('test_acknowledged')
            row['request']='unknown' if uncertain else 'blocked' if not possible else 'acknowledged' if row.get('test_acknowledged') else row['request']
            row['error']=self.logs.scrub(str(exc) or type(exc).__name__);row['http_error_status']=getattr(exc,'status',None)
            row['error_detail']=self.logs.scrub(getattr(exc,'detail',''));quit_requested=True
            self.emit(name+': '+row['error'])
        finally:
            if possible:
                allowed=not uncertain
                if uncertain:
                    try:allowed=(await ask(self.prompt,f'{name} write outcome unknown. Never retry test. Type RESTORE for original={original} and stop: ')).strip()=='RESTORE'
                    except (KeyboardInterrupt,EOFError,asyncio.CancelledError):allowed=False
                if allowed:
                    try:
                        self.logs.add('TEST_SWAGGER_RESTORE_INTENT',tag_name=name,path=path,value=original)
                        bounds=await self.write(service,case,original,None,row,'restore')
                        expected={alias:original for alias in case['aliases']}
                        if case['kind']=='door':expected[self.opposite(case)]=0
                        if case['kind']!='door':
                            for related in case['feedback_aliases']:
                                if related in baseline:expected[related]=baseline[related]
                            for related in self.watched(case,service):
                                if related!=name and related not in expected and related in baseline:expected[related]=baseline[related]
                        row['restore_readback_verified'],row['restored']=await self.observe(service,case,original,bounds,row,'restore',expected)
                    except (Exception,KeyboardInterrupt,EOFError,asyncio.CancelledError) as exc:
                        row['restoration_error']=self.logs.scrub(str(exc) or type(exc).__name__)
                else:row['restoration_error']='Operator declined unknown-outcome restoration'
            row['continue_queue']=bool(possible and row['restored'] and not quit_requested and not uncertain and not self.logs.error)
            if self.logs.error:row['audit_error']=self.logs.error
            row['finished_at']=now()
            self.logs.add('TEST_SWAGGER_RESULT',**row)
            if self.logs.error:row.update(audit_error=self.logs.error,continue_queue=False)
            self.save()
            if possible and not row['restored']:self.emit('STOP: restoration is not verified. Inspect '+name+'; no next command will be sent.')
        return row

    @staticmethod
    def watched(case,service):
        return list(case['watched_identities'])

    @staticmethod
    def conditions(case,poll):
        prefixes={alias.split('_',1)[0]+'_' for alias in case['aliases']+case['feedback_aliases']}
        return {name:value for name,value in poll.items() if name in ('Remote','Local','MainInletStatus') or name.startswith('Alarm') or any(name.startswith(prefix) for prefix in prefixes)}

    def comparisons(self):
        groups={}
        for row in self.results:groups.setdefault(row['tag_name'],{})[row['path']]=row
        summaries=[]
        for name,paths in groups.items():
            direct,app=paths.get('direct',{}),paths.get('app',{})
            item={'tag_name':name,'both_paths_tested':bool(direct and app),
                  'conditions_changed':app.get('preconditions_changed_between_paths')}
            for field in ('request','readback','output','human_result','restored'):
                item['direct_'+field]=direct.get(field);item['app_'+field]=app.get(field)
            item['path_difference_observed']=bool(direct and app and any(direct.get(field)!=app.get(field) for field in ('request','readback','output')))
            item['path_cause_proven']=False
            summaries.append(item)
        return summaries

    def save(self):
        try:
            data=self.logs.scrub({'format':'swagger-line-test-v1','exported_at':now(),'results':self.results,'comparisons':self.comparisons(),'audit_fallback_events':self.logs.fallback})
            temporary=self.output/'report.tmp';temporary.write_text(json.dumps(data,indent=2)+'\n');temporary.replace(self.output/'report.json')
            fields=['tag_name','tank','kind','path','request','readback','output','human_result','physical_stop_verified','restored','continue_queue','preconditions_changed_between_paths','skip_reason','error','http_error_status','error_detail','restoration_error','audit_error']
            with (self.output/'results.csv').open('w',newline='') as handle:
                writer=csv.DictWriter(handle,fieldnames=fields,extrasaction='ignore');writer.writeheader()
                for row in data['results']:
                    writer.writerow({k:("'"+v if isinstance(v,str) and re.match(r'^[=+@\-\t\r]',v) else v) for k,v in row.items()})
            comparisons=data['comparisons']
            if comparisons:
                with (self.output/'comparison.csv').open('w',newline='') as handle:
                    writer=csv.DictWriter(handle,fieldnames=list(comparisons[0]));writer.writeheader();writer.writerows(comparisons)
        except OSError as exc:
            if self.results:self.results[-1].update(audit_error=self.logs.scrub(str(exc)),continue_queue=False)
            self.emit('STOP: evidence export failed. Cleanup status above remains applicable; no next command will be sent.')
            try:
                tmp=self.output/'report.tmp';tmp.write_text(json.dumps(self.logs.scrub({'format':'swagger-line-test-v1','results':self.results}),indent=2)+'\n');tmp.replace(self.output/'report.json')
            except OSError:pass

    async def run(self,cases):
        previous=None
        for case in cases:
            tank=case['tank'];label=f'Tank{tank:02d}' if tank else 'Global / MainInlet'
            if tank!=previous:
                self.emit('\n'+label)
                if previous is not None:
                    answer=await ask(self.ready,'Move to '+label+'; press Enter/R when ready or Q to stop: ')
                    if answer.strip().lower() not in ('','r'):break
                previous=tank
            first_service=self.services['direct']
            try:
                baseline=await self.prepare(first_service,case)
                value,reason=await self.inputs(case,first_service,baseline[case['tag_name']])
            except (KeyboardInterrupt,EOFError,asyncio.CancelledError):break
            except Exception as exc:
                self.results.append({'tag_name':case['tag_name'],'tank':tank,'kind':case['kind'],'path':'not_run','request':'blocked','human_result':'unchecked','error':self.logs.scrub(str(exc)),'continue_queue':False,'finished_at':now()})
                self.save();return self.results
            if reason:
                self.results.append({'tag_name':case['tag_name'],'tank':tank,'kind':case['kind'],'path':'not_run','request':'not_sent',
                                     'human_result':'unchecked','skip_reason':reason,'finished_at':now()})
                self.save();continue
            original=baseline[case['tag_name']];reference=None
            for path in self.services:
                if path!='direct':
                    answer=await ask(self.ready,f'{case["tag_name"]}: direct is restored. Ready to repeat through app? Enter/R or Q: ')
                    if answer.strip().lower() not in ('','r'):return self.results
                row=await self.run_path(case,path,value,original,reference)
                if reference is None:reference=row.get('baseline')
                if not row['continue_queue']:return self.results
        return self.results


async def execute(plan,args):
    settings=Settings()
    if settings.mock_mode:raise ValueError('Direct line test requires PLC_MOCK_MODE=false')
    if not settings.api_key:raise ValueError('Existing PLC_API_KEY is missing')
    if not sys.stdin.isatty():raise ValueError('--execute requires an interactive terminal')
    print('Supplier:',settings.base_url,'; comparison:',args.app_origin if args.compare_app else 'direct only')
    print('Keep other write clients inactive. Numeric values/reset rules are requested, not guessed.')
    if input('Review the exact list and stand at the first location; type RUN: ').strip()!='RUN':return
    args.output.mkdir(parents=True,exist_ok=False)
    logs=LogService(args.output/'events.jsonl',settings.api_key)
    logs.add('TEST_SWAGGER_SESSION',api_address=settings.base_url,app_origin=args.app_origin if args.compare_app else None,plan=plan,
             timestamp_timezone=settings.timestamp_timezone,timestamp_offset_seconds=settings.timestamp_offset_seconds,stale_ms=settings.stale_ms)
    clients={'direct':PLCClient(settings.base_url,settings.api_key,settings.timeout)}
    if args.compare_app:clients['app']=AppClient(args.app_origin,settings.base_url,settings.timeout)
    services={path:SignalService(client,logs,settings.stale_ms,timestamp_timezone=settings.timestamp_timezone,
                               timestamp_offset_seconds=settings.timestamp_offset_seconds) for path,client in clients.items()}
    try:
        for path,service in services.items():
            await service.load_tags()
            if {name for name,tag in service.tags.items() if tag.read_write=='W'}!={case['tag_name'] for case in inventory()['cases']}:
                raise ValueError(path+' writable catalog changed; review the full inventory before testing')
            for case in plan['cases']:
                if case['tag_name'] not in service.tags or signature(service.tags[case['tag_name']])!=case['identity']:
                    raise ValueError(path+' metadata differs from the reviewed inventory; no test started')
        live_schema=await clients['direct']._request('GET','/openapi.json')
        for endpoint,method in [('/api/v1/tags/list','get'),('/api/v1/tags/read','get'),('/api/v1/tags/write','post')]:
            if method not in live_schema.get('paths',{}).get(endpoint,{}):raise ValueError('Live Swagger write/read contract changed; no test started')
        await SwaggerLineTest(services,logs,args.output,wait_seconds=args.wait_seconds).run(plan['cases'])
    finally:
        for client in clients.values():
            if isinstance(client,AppClient):await client.close()
            else:await client.client.aclose()
    print('Evidence:',args.output)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--compare-app',action='store_true',help='Also test the local app backend path; does not click the browser')
    parser.add_argument('--app-origin',default='http://127.0.0.1:8080')
    parser.add_argument('--only',action='append',default=[])
    parser.add_argument('--wait-seconds',type=int,default=15)
    parser.add_argument('--output',type=Path,default=ROOT/'logs'/('swagger-line-test-'+uuid.uuid4().hex[:10]))
    args=parser.parse_args(argv)
    try:
        local_origin(args.app_origin)
        if not 1<=args.wait_seconds<=300:raise ValueError('Wait limit must be1–300 seconds')
        plan=inventory();names={c['tag_name'] for c in plan['cases']}
        if set(args.only)-names:raise ValueError('Unknown or read-only requested tag')
        if args.only:plan['cases']=[c for c in plan['cases'] if c['tag_name'] in args.only]
        print(f'{len(plan["cases"])} writable tags; physical tank order; direct'+(' then app' if args.compare_app else ' supplier path'))
        for index,case in enumerate(plan['cases'],1):
            location=f'Tank{case["tank"]:02d}' if case['tank'] else 'Global'
            print(f'{index:03d}. {location} {case["tag_name"]} [{case["kind"]}] {case["identity"][1]}'+(' - numeric value required' if case['kind']=='numeric' else ''))
        if args.execute:asyncio.run(execute(plan,args))
        else:print('DRY RUN: offline inventory only. No HTTP request or PLC write sent.')
        return 0
    except (ValueError,OSError,KeyboardInterrupt,EOFError) as exc:
        print('Stopped:',str(exc) or type(exc).__name__,file=sys.stderr);return 1


if __name__=='__main__':raise SystemExit(main())
