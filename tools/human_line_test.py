#!/usr/bin/env python3
"""Run the reviewed non-door 0/1 queue directly against the supplier API."""
import argparse
import asyncio
import csv
from datetime import datetime, timezone
import json
import inspect
import os
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from server.config import Settings
from server.log_service import LogService
from server.models import ValidationError
from server.plc_client import PLCClient
from server.signal_service import SignalService

# This is the operator-approved Oct26 scope, not a name-pattern authorization.
APPROVED = frozenset('''Tank01_FilterRemote
Tank01_HeaterRemote
Tank01_USRemote
Tank11_FillWaterOn
Tank11_SprayRemote
Tank14_FilterRemote
Tank14_HeaterRemote
Tank01_FillWaterAuto
Tank02_AirAgitationAuto
Tank02_FillWaterAuto
Tank04_AirAgitationAuto
Tank04_FillWaterAuto
Tank06_AirAgitationAuto
Tank06_FillWaterAuto
Tank07_AirAgitationAuto
Tank07_CoolerAuto
Tank07_FillWaterAuto
Tank08_AirAgitationAuto
Tank09_AirAgitationAuto
Tank09_FillWaterAuto
Tank10_FillWaterAuto
Tank11_FillWaterAuto
Tank12_AirAgitationAuto
Tank12_FillWaterAuto
Tank13_FillWaterAuto
Tank14_FillWaterAuto
Tank15_AirAgitationAuto
Tank15_FillWaterAuto
Tank16_AirAgitationAuto
Tank16_FillWaterAuto
Tank02_FillWaterOn
Tank03_FilterRemote
Tank03_HeaterRemote
Tank03_SwingRemote
Tank04_FillWaterOn
Tank05_FilterRemote
Tank05_HeaterRemote
Tank05_SwingRemote
Tank06_FillWaterOn
Tank07_FillWaterOn
Tank07_FilterRemote
Tank07_RectRemote
Tank09_FillWaterOn
Tank10_FillWaterOn
Tank10_FilterRemote
Tank10_HeaterRemote
Tank10_SwingRemote
Tank12_FillWaterOn
Tank13_FillWaterOn
Tank13_HeaterRemote
Tank14_FillWaterOn
Tank14_SwingRemote
Tank15_FillWaterOn
Tank16_FillWaterOn
Tank16_FilterRemote
Tank16_HeaterRemote
Tank07_AirAgitationOn
Tank07_CoolerOn
Tank08_AirAgitationOn
Tank09_AirAgitationOn
Tank12_AirAgitationOn
Tank15_AirAgitationOn
Tank16_AirAgitationOn'''.split())


def now():
    return datetime.now(timezone.utc).isoformat()


def signature(tag):
    return [tag.tag_name, tag.device_address, tag.data_type, tag.read_write, tag.multiplier]


def load_plan(path, only=()):
    plan = json.loads(Path(path).read_text())
    if not isinstance(plan, dict) or not isinstance(plan.get('cases'), list) or not plan['cases']:
        raise ValueError('Plan requires a non-empty cases list.')
    names = []
    for case in plan['cases']:
        name = case.get('tag_name')
        if name not in APPROVED or name in names:
            raise ValueError('Plan contains an unapproved or repeated command.')
        names.append(name)
        feedback = None if name.endswith('Auto') else re.sub(r'(?:Remote|On)$', 'Status', name)
        if 'operator_note' in case and not isinstance(case['operator_note'],str):
            raise ValueError(f'{name}: operator_note must be text.')
        if case.get('feedback_tag') != feedback:
            raise ValueError(f'{name}: completion mapping differs from the reviewed plan.')
        if type(case.get('wait_seconds')) is not int or not 1 <= case['wait_seconds'] <= 300:
            raise ValueError(f'{name}: wait_seconds must be an integer from1 to300.')
        for field, expected_name, permission in [('identity',name,'W'),('feedback_identity',feedback,'R')]:
            identity = case.get(field)
            if expected_name is None:
                if identity is not None: raise ValueError(f'{name}: unexpected feedback identity.')
            elif not isinstance(identity,list) or len(identity)!=5 or identity[0]!=expected_name or identity[2:4]!=['Bool',permission]:
                raise ValueError(f'{name}: invalid frozen {field}.')
    if not isinstance(plan.get('api_address'),str): raise ValueError('Plan requires api_address.')
    unknown = set(only)-set(names)
    if unknown: raise ValueError('Requested command is not in this plan: '+', '.join(sorted(unknown)))
    if only: plan['cases']=[case for case in plan['cases'] if case['tag_name'] in only]
    return plan


async def read_verdict(prompt):
    """Await one terminal key without blocking Ctrl+C or leaving terminal mode set."""
    import termios
    import tty
    print(prompt, end='', flush=True)
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    loop = asyncio.get_running_loop()
    answer = loop.create_future()
    def readable():
        if answer.done(): return
        try:
            key = os.read(fd,1).decode('ascii',errors='ignore').lower()
            if not key: answer.set_exception(EOFError())
            elif key in ('p','i','n','q'):
                print(key.upper(),flush=True)
                answer.set_result(key)
        except OSError as exc: answer.set_exception(exc)
    try:
        tty.setcbreak(fd)
        loop.add_reader(fd,readable)
        return await answer
    finally:
        loop.remove_reader(fd)
        termios.tcsetattr(fd,termios.TCSADRAIN,previous)


class CleanupLogs:
    """Audit failure stops new tests but cannot prevent an authorized cleanup0."""
    def __init__(self, source):
        self.source,self.error,self.fallback = source,None,[]

    def scrub(self, value):
        return self.source.scrub(value)

    def add(self, event, **fields):
        if self.error is None:
            try: return self.source.add(event,**fields)
            except Exception as exc:
                self.error=self.scrub('Audit storage failed: '+str(exc))
        entry=self.scrub({'timestamp':now(),'event':event,**fields})
        self.fallback.append(entry)
        return entry


class HumanLineTest:
    def __init__(self, service, logs, output, verdict=read_verdict, cleanup=input, emit=print):
        self.service,self.output = service,Path(output)
        self.logs=CleanupLogs(logs)
        self.service.logs=self.logs
        self.verdict,self.cleanup = verdict,cleanup
        self.emit = lambda message: emit(logs.scrub(message))
        self.results = []

    def record(self, event, **fields):
        return self.logs.add(event, **fields)

    def check_ready(self, poll):
        if not self.service.fresh(poll) or poll.get('Remote')!=1 or poll.get('Local')!=0:
            raise ValidationError('Fresh complete data with Remote=1 and Local=0 is required.')

    def identity_guard(self, frozen, zero_baseline=False, independent=None):
        def guard(poll):
            self.check_ready(poll)
            for name, expected in frozen.items():
                current = self.service.tags.get(name)
                if current!=expected:
                    raise ValidationError(f'{name}: metadata changed; write blocked.')
                if (independent is None or name in independent) and sum(t.device_address==expected.device_address for t in self.service.tags.values())!=1:
                    raise ValidationError(f'{name}: shared address; write blocked.')
                if zero_baseline and poll.get(name)!=0:
                    raise ValidationError(f'{name}: baseline is not0; existing state is preserved.')
        return guard

    async def prepare(self, case):
        await self.service.load_tags()
        frozen = {}
        for name, identity in [(case['tag_name'],case['identity']),(case['feedback_tag'],case['feedback_identity'])]:
            if name is None: continue
            tag = self.service.tags.get(name)
            if tag is None or signature(tag)!=identity:
                raise ValidationError(f'{name}: live identity differs from the reviewed plan.')
            frozen[name] = tag
        if case['tag_name'].endswith('Auto'):
            for suffix in ('On','Status'):
                name=re.sub('Auto$',suffix,case['tag_name'])
                if name in self.service.tags: frozen[name]=self.service.tags[name]
        poll=await self.service.read()
        self.identity_guard(frozen,zero_baseline=True,independent=(case['tag_name'],case['feedback_tag']))(poll)
        return frozen,poll

    def receipt_valid(self, receipt, tag, value):
        return (isinstance(receipt,dict) and receipt.get('written') is True
                and receipt.get('tag_name')==tag.tag_name and type(receipt.get('value')) in (int,float)
                and receipt['value']==value and receipt.get('device_address')==tag.device_address
                and receipt.get('data_type')==tag.data_type and receipt.get('read_write')==tag.read_write
                and receipt.get('multiplier',1)==tag.multiplier)

    async def observe(self, case, value, received_at, baseline_at, frozen):
        deadline=asyncio.get_running_loop().time()+case['wait_seconds']
        while True:
            remaining=deadline-asyncio.get_running_loop().time()
            if remaining<=0: return False
            try: poll=await asyncio.wait_for(self.service.read(),remaining)
            except TimeoutError: return False
            self.check_ready(poll)
            stamp=self.service.poll_time(poll)
            self.record('TEST_SAMPLE',tag_name=case['tag_name'],phase=f'after{value}',supplier_utc=stamp.isoformat(),poll=poll)
            if value==1 and self.logs.error: raise OSError(self.logs.error)
            later=stamp>datetime.fromisoformat(received_at) and stamp>datetime.fromisoformat(baseline_at)
            names=[case['tag_name']]+([case['feedback_tag']] if case['feedback_tag'] else [])
            if value==0: names=list(frozen)
            if later and all(poll.get(name)==value for name in names): return True
            await asyncio.sleep(min(.25,max(0,deadline-asyncio.get_running_loop().time())))

    async def run_case(self, case):
        name=case['tag_name']
        row={'tag_name':name,'started_at':now(),'api_status':'unchecked','human_result':'unchecked',
             'human_observation':'not_checked','human_observation_scope':'Operation while command=1; physical stop is not checked by the verdict key.',
             'restored_zero':False,'one_verified':False,'zero_verified':False,'continue_queue':False}
        possible=False; uncertain=False; quit_requested=False; frozen={}
        try:
            frozen,baseline=await self.prepare(case)
            row['baseline']=baseline
            self.emit(f'\n{name}: sending 1; wait up to {case["wait_seconds"]} s for '+(case['feedback_tag'] or 'command readback only')+'.')
            if case.get('operator_note'): self.emit('Operator note (not an automatic prerequisite): '+case['operator_note'])
            self.record('TEST_ONE_INTENT',tag_name=name,value=1,identity=case['identity'])
            if self.logs.error: raise OSError(self.logs.error)
            captured={}
            def before_one(poll):
                if self.logs.error: raise OSError(self.logs.error)
                self.identity_guard(frozen,zero_baseline=True,independent=(case['tag_name'],case['feedback_tag']))(poll)
                captured['baseline_at']=self.service.poll_time(poll).isoformat()
            possible=True
            try: receipt=await self.service.write(name,1,before_write=before_one)
            except asyncio.CancelledError:
                possible=True;uncertain=True
                raise
            except Exception as exc:
                possible=getattr(exc,'write_dispatched',None) is not False
                uncertain=possible
                raise
            received_at=now();row['one_receipt']=receipt;row['one_received_at']=received_at
            if not self.receipt_valid(receipt,frozen[name],1):
                uncertain=True
                raise ValidationError('Write1 receipt is incomplete or mismatched; outcome needs review.')
            row['one_verified']=await self.observe(case,1,received_at,captured['baseline_at'],frozen)
            if not row['one_verified']: row['api_detail']='Expected fresh command1 and mapped status, where configured, were not observed within the wait limit.'
            self.emit('API command/status 1 observed.' if row['one_verified'] else 'API wait limit reached; expected fresh1 was not observed.')
            self.emit('Command is still 1. P=operation observed, I=incorrect action, N=no physical response, Q=quit. Your key requests 0, verifies restoration, then advances.')
            key=self.verdict('Press P / I / N / Q: ')
            if inspect.isawaitable(key): key=await key
            if key not in ('p','i','n','q'): raise ValueError('Invalid human verdict.')
            row['human_observation']={'p':'pass','i':'incorrect','n':'no_response','q':'not_checked'}[key]
            row['human_observation_at']=now();quit_requested=key=='q'
            self.record('TEST_HUMAN_OBSERVATION',**row,write_sent=False)
        except (Exception,KeyboardInterrupt,EOFError,asyncio.CancelledError) as exc:
            row['error']=str(exc) or type(exc).__name__
            quit_requested=True
            self.emit(f'{name}: {row["error"]}')
        finally:
            if possible:
                clear_allowed=not uncertain
                if uncertain:
                    self.emit(f'{name}: write1 outcome is uncertain. It will never be retried.')
                    try: clear_allowed=self.cleanup(f'Type ZERO to request {name}=0 and stop this queue: ').strip()=='ZERO'
                    except (KeyboardInterrupt,EOFError): clear_allowed=False
                if clear_allowed:
                    try:
                        self.record('TEST_ZERO_INTENT',tag_name=name,value=0,after_unknown_one=uncertain)
                        captured={}
                        def before_zero(poll):
                            self.identity_guard(frozen,independent=(case['tag_name'],case['feedback_tag']))(poll)
                            captured['baseline_at']=self.service.poll_time(poll).isoformat()
                        receipt=await self.service.write(name,0,before_write=before_zero)
                        received_at=now();row['zero_receipt']=receipt;row['zero_received_at']=received_at
                        if not self.receipt_valid(receipt,frozen[name],0):
                            raise ValidationError('Write0 receipt is incomplete or mismatched. Inspect the equipment before any further command.')
                        row['zero_verified']=await self.observe(case,0,received_at,captured['baseline_at'],frozen)
                        row['restored_zero']=row['zero_verified']
                        if not row['restored_zero']: row['restoration_error']='Fresh command/status0 and related baseline restoration were not verified within the wait limit.'
                    except (Exception,KeyboardInterrupt,EOFError,asyncio.CancelledError) as exc:
                        row['restoration_error']=str(exc) or type(exc).__name__
                else: row['restoration_error']='Cleanup0 was not authorized after the uncertain write1.'
            row['api_status']='checked' if row['one_verified'] and row['zero_verified'] and not row.get('error') else 'failed' if possible else 'unchecked'
            row['continue_queue']=row['restored_zero'] and not quit_requested and not uncertain and not self.logs.error
            if self.logs.error:
                row['audit_error']=self.logs.error
                row['api_status']='unchecked'
            row['finished_at']=now()
            self.record('TEST_CASE_RESULT',**row)
            if self.logs.error:
                row.update(audit_error=self.logs.error,api_status='unchecked',continue_queue=False)
            self.results.append(row)
            try: self.export()
            except OSError as exc:
                row['audit_error']=self.logs.scrub('Evidence export failed: '+str(exc))
                row['continue_queue']=False;row['api_status']='unchecked'
                try: self.write_report()
                except OSError: pass  # Terminal warning is the fallback when report storage also fails.
            if row.get('audit_error'): self.emit('STOP: '+row['audit_error']+' Cleanup state is shown below; no next command will be sent.')
            self.emit(f'{name}: API '+{'checked':'pass','failed':'fail','unchecked':'unchecked'}[row['api_status']]+f'; operation observation={row["human_observation"]}; restored 0={row["restored_zero"]}.')
            if possible and not row['restored_zero']:
                self.emit(f'STOP: {name} needs inspection. A verified0 was not obtained. No next command will be sent.')
        return row

    def write_report(self):
        report=self.logs.scrub({'format':'human-line-test-v1','exported_at':now(),'results':self.results,'audit_fallback_events':self.logs.fallback})
        temporary=self.output/'report.tmp'
        temporary.write_text(json.dumps(report,indent=2)+'\n')
        temporary.replace(self.output/'report.json')
        return report

    def export(self):
        report=self.write_report()
        fields=['tag_name','api_result','human_observation','human_observation_scope','human_result','one_verified','zero_verified','restored_zero','started_at','finished_at','api_detail','error','restoration_error','audit_error']
        with (self.output/'results.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=fields,extrasaction='ignore');writer.writeheader()
            for row in report['results']:
                values={**row,'api_result':{'checked':'pass','failed':'fail','unchecked':'unchecked'}[row['api_status']]}
                writer.writerow({key:("'"+value if isinstance(value,str) and re.match(r'^[=+@\-\t\r]',value) else value) for key,value in values.items()})

    async def run(self, cases):
        for case in cases:
            row=await self.run_case(case)
            if not row['continue_queue']: break
        return self.results


async def execute(plan, output):
    settings=Settings()
    if settings.mock_mode: raise ValueError('This direct-line tool requires PLC_MOCK_MODE=false.')
    if settings.base_url!=plan['api_address']: raise ValueError('Configured supplier API differs from the reviewed plan.')
    if not settings.api_key: raise ValueError('PLC_API_KEY is missing from the existing environment/.env.')
    if not sys.stdin.isatty(): raise ValueError('--execute requires an interactive terminal for the human verdict keys.')
    print('The queue writes directly to',settings.base_url)
    print('Watch the equipment. Each P/I/N key records operation at 1, requests 0, then advances only after fresh restoration. Q restores 0 and stops.')
    if input('Confirm the exact printed plan and clear equipment; type RUN to begin: ').strip()!='RUN':
        print('Cancelled; no PLC request was sent.');return
    output.mkdir(parents=True,exist_ok=False)
    logs=LogService(output/'events.jsonl',settings.api_key)
    logs.add('TEST_SESSION_START',api_address=settings.base_url,plan=plan,
             stale_ms=settings.stale_ms,timestamp_timezone=settings.timestamp_timezone,timestamp_offset_seconds=settings.timestamp_offset_seconds)
    client=PLCClient(settings.base_url,settings.api_key,settings.timeout)
    service=SignalService(client,logs,settings.stale_ms,timestamp_timezone=settings.timestamp_timezone,timestamp_offset_seconds=settings.timestamp_offset_seconds)
    try: await HumanLineTest(service,logs,output).run(plan['cases'])
    finally: await client.client.aclose()
    print('Evidence:',output)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,default=ROOT/'config/human-line-test-plan.json')
    parser.add_argument('--only',action='append',default=[],metavar='TAG',help='Run only these reviewed plan commands; repeat as needed.')
    parser.add_argument('--execute',action='store_true',help='Write to the line after the initial readiness confirmation.')
    parser.add_argument('--output',type=Path,default=ROOT/'logs'/('human-line-test-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]))
    args=parser.parse_args(argv)
    try:
        plan=load_plan(args.plan,args.only)
        print(f'{len(plan["cases"])} sequential 0→1→0 cases; supplier {plan["api_address"]}')
        for index,case in enumerate(plan['cases'],1):
            print(f'{index:02d}. {case["tag_name"]} ({case["identity"][1]}) → {case["feedback_tag"] or "own command readback only"}; wait {case["wait_seconds"]}s')
        if args.execute: asyncio.run(execute(plan,args.output))
        else: print('DRY RUN: no network request or PLC write was sent. Review the plan before adding --execute.')
        return 0
    except (ValueError,OSError,KeyboardInterrupt,EOFError) as exc:
        print('Stopped:',str(exc) or type(exc).__name__,file=sys.stderr);return 1


if __name__=='__main__': raise SystemExit(main())
