import asyncio
import json
from dataclasses import replace
from pathlib import Path
import pytest
from server.config import ROOT
from server.log_service import LogService
from server.plc_client import MockPLCClient
from server.signal_service import SignalService
from server.models import Tag, ValidationError
from server.catalog_diagnostics import catalog_warnings

def make_service(tmp_path):
    client = MockPLCClient(ROOT / 'config/mock-tags.json')
    logs = LogService(tmp_path / 'events.jsonl', 'private-secret')
    return client, SignalService(client, logs, 3000), logs

def test_mock_catalog_and_read(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        tags = await service.load_tags()
        poll = await service.read()
        assert len(tags) == 362
        assert sum(t.read_write == 'W' for t in tags) == 141
        assert sum(t.read_write == 'R' for t in tags) == 221
        assert poll['tags_ok'] == len(tags) and poll['tags_failed'] == 0
        assert service.fresh() and service.remote()
        assert next(t for t in tags if t.tag_name == 'Tank01_TempSV').device_address == 'D4020'
    asyncio.run(run())

def test_latest_catalog_mappings(tmp_path):
    client, _, _ = make_service(tmp_path)
    tags = {raw['tag_name']: Tag.parse(raw) for raw in client.tags}
    for offset, tank in enumerate((1,3,5,7,10,13,14,16)):
        t = tags[f'Tank{tank:02d}_TempAdj']
        assert (t.device_address,t.data_type,t.read_write,t.multiplier,t.low_limit,t.high_limit) == (
            f'D{4010+offset}', 'SignedWord', 'W', 0.1, -999.0, 999.9)
        assert t.description == f'Tank{tank:02d} Temperature +- Adjust (Degree Celsius)'
    for tank,address in ((3,'D1008'),(5,'D1018'),(10,'D1100'),(14,'D1124')):
        t = tags[f'Tank{tank:02d}_SwingSV']
        assert (t.device_address,t.data_type,t.read_write,t.multiplier,t.low_limit,t.high_limit) == (
            address, 'Word', 'W', 1.0, 5.0, 120.0)
    expected = {
        'Tank07_AmpereSV': ('D1362','Word','W',0.1,0.0,200.0),
        'Tank07_AmperePV': ('D1055','Word','R',0.1,None,None),
        'Tank07_VoltagePV': ('D1054','Word','R',0.1,None,None),
        'Tank16_Conductivity': ('D1142','Float','R',1.0,None,None),
        'Tank09_WaterFlow': ('D1036','Word','R',0.1,None,None),
    }
    for name,fields in expected.items():
        t = tags[name]
        assert (t.device_address,t.data_type,t.read_write,t.multiplier,t.low_limit,t.high_limit) == fields
    assert 'Tank16_PH' not in tags
    assert tags['Tank07_AmpereSV'].description == 'Tank07 Ampere Set Value (A)'
    assert tags['Tank07_AmperePV'].description == 'Tank07 Ampere Present Value (A)'
    assert tags['Tank07_VoltagePV'].description == 'Tank07 Rectifier Voltage Present Value (V)'
    assert tags['Tank16_Conductivity'].description == 'Conductivity Meter Reading (MOhmCM)'
    assert tags['Tank09_WaterFlow'].description == 'Tank09 Water Flow Meter Value (LPM)'

@pytest.mark.parametrize('batch',[False,True])
def test_signed_word_mock_write_store_read_unchanged(tmp_path, batch):
    async def run():
        client, service, _ = make_service(tmp_path)
        if batch:
            await service.write_batch([{'tag_name':'Tank01_TempAdj','value':-5.0}])
        else:
            result = await service.write('Tank01_TempAdj',-5.0)
            assert result['value'] == -5.0
        assert client.values['Tank01_TempAdj'] == -5.0
        assert await client.read_signal('Tank01_TempAdj') == -5.0
        assert (await service.read())['Tank01_TempAdj'] == -5.0
    asyncio.run(run())

def test_duplicate_address_warns_without_rejecting_startup(tmp_path):
    async def run():
        _, service, logs = make_service(tmp_path)
        tags = await service.load_tags()
        await service.read()
        assert len(tags) == 362 and service.fresh()
        warning = next(w for w in service.catalog_warnings if w['device_address'] == 'D1036')
        assert warning['code'] == 'DUPLICATE_ADDRESS'
        assert warning['tag_names'] == ['Tank08_WaterFlow','Tank09_WaterFlow']
        assert 'SUPPLIER CONFIRMATION REQUIRED' in warning['message']
        assert any(e['event']=='CATALOG_DIAGNOSTICS' and e['result']=='WARNING' for e in logs.get())
        await service.load_tags()
        assert sum(e['event']=='CATALOG_DIAGNOSTICS' for e in logs.get()) == 1
    asyncio.run(run())

def test_duplicate_tag_names_still_rejected(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        client.tags.append(dict(client.tags[0]))
        with pytest.raises(ValidationError,match='duplicate tag names'): await service.load_tags()
    asyncio.run(run())

@pytest.mark.parametrize('field,value', [('device_address','D9999'), ('data_type','Float'),
    ('read_write','R'), ('multiplier',0.2), ('description','Supplier revised description'),
    ('low_limit',-500.0), ('high_limit',500.0)])
def test_every_live_metadata_difference_is_advisory(tmp_path, field, value):
    async def run():
        client, service, logs = make_service(tmp_path)
        baseline = [Tag.parse(raw) for raw in client.tags]
        service.baseline = baseline
        client.by_name['Tank01_TempAdj'][field] = value
        await service.load_tags()
        assert getattr(service.tags['Tank01_TempAdj'],field) == value
        warning = next(w for w in service.catalog_warnings if w.get('tag_name')=='Tank01_TempAdj')
        assert warning['changed_fields'] == [field]
        assert warning['live'][field] == value and warning['expected'][field] != value
        assert any(warning in e.get('warnings',[]) for e in logs.get())
        await service.read()
        assert service.fresh()
        if field == 'read_write':
            with pytest.raises(ValidationError,match='read-only'): await service.write('Tank01_TempAdj',-5.0)
        else:
            assert (await service.write('Tank01_TempAdj',-5.0))['value'] == -5.0
    asyncio.run(run())

def test_live_added_missing_tags_and_count_are_advisory(tmp_path):
    client, _, _ = make_service(tmp_path)
    baseline = [Tag.parse(raw) for raw in client.tags]
    extra = replace(baseline[0],tag_name='NewSupplierTag',device_address='D9000')
    warnings = catalog_warnings(baseline+[extra],baseline)
    count = next(w for w in warnings if w['code']=='CATALOG_COUNT')
    assert (count['live_count'],count['baseline_count']) == (363,362)
    assert any(w.get('tag_name')=='NewSupplierTag' and w['expected'] is None for w in warnings)
    warnings = catalog_warnings(baseline[1:],baseline)
    assert any(w.get('tag_name')==baseline[0].tag_name and w['live'] is None for w in warnings)

def test_all_configured_cases_validate_against_catalog(tmp_path):
    client, _, _ = make_service(tmp_path)
    tags = {raw['tag_name']:Tag.parse(raw) for raw in client.tags}
    cases = json.loads((ROOT / 'config/test-cases.json').read_text())['tests']
    assert len({c['id'] for c in cases}) == len(cases)
    for case in cases:
        command = tags[case['command_tag']]
        feedback = tags[case['feedback_tag']]
        assert command.read_write == 'W', case['id']
        assert feedback.read_write == 'R', case['id']
        command.validate_write(case['command_value'])
        replace(feedback,read_write='W').validate_write(case['expected_feedback'])
        assert case['timeout_ms'] > 0 and case['poll_interval_ms'] > 0
        assert case['reset_command'] is None
        if 'Door' not in case['command_tag']:
            assert case['requires_confirmation'] is True, case['id']

def test_service_blocks_read_only_and_bad_values(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        with pytest.raises(ValidationError, match='read-only'):
            await service.write('Tank01_DoorOpened', 1)
        with pytest.raises(ValidationError, match='above'):
            await service.write('Tank01_TempSV', 1000)
        with pytest.raises(ValidationError, match='Bool'):
            await service.write('Tank01_DoorOpenRemote', 2)
        assert client.values['Tank01_DoorOpenRemote'] == 0
    asyncio.run(run())

def test_mock_write_and_delayed_feedback(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        result = await service.write('Tank01_DoorOpenRemote', 1)
        assert result['written'] is True
        assert client.values['Tank01_DoorOpened'] == 0
        await asyncio.sleep(.55)
        assert (await service.read())['Tank01_DoorOpened'] == 1
        assert (await service.write('Tank01_TempSV', 25.0))['value'] == 25.0
    asyncio.run(run())

def test_remote_and_stale_fail_closed(tmp_path):
    async def run():
        client, service, _ = make_service(tmp_path)
        client.values['Remote'] = 0
        with pytest.raises(ValidationError, match='Remote'):
            await service.write('Tank01_TempSV', 25)
        client.values['Remote'] = 1
        service.stale_ms = -1
        with pytest.raises(ValidationError, match='stale'):
            await service.write('Tank01_TempSV', 25)
    asyncio.run(run())

def test_api_key_redacted_from_log(tmp_path):
    logs = LogService(tmp_path / 'events.jsonl', 'private-secret')
    logs.add('ERROR', error='request failed private-secret', api_key='private-secret')
    assert 'private-secret' not in (tmp_path / 'events.jsonl').read_text()
    assert 'private-secret' not in logs.export('all','json')[0]

def test_null_tag_is_not_fresh_even_if_supplier_count_claims_success(tmp_path):
    async def run():
        client, service, logs = make_service(tmp_path)
        await service.load_tags()
        client.values['Tank01_DoorOpened'] = None
        await service.read()
        assert not service.fresh()
        assert 'Tank01_DoorOpened' in logs.get()[-1]['failed_tags']
        with pytest.raises(ValidationError, match='stale'):
            await service.write('Tank01_TempSV', 25)
    asyncio.run(run())
