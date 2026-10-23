"""Offline checks against saved supplier evidence; never call the line API."""
import asyncio
import csv
import hashlib
import io
import json
from pathlib import Path

from server.config import ROOT
from server.models import Tag
from server.plc_client import MockPLCClient

SOURCE = ROOT / 'docs/source'


def test_saved_supplier_sources_match_provenance_hashes():
    capture = json.loads((SOURCE / 'supplier-api-capture-2026-10-23.json').read_text())
    for source in capture['sources'].values():
        assert hashlib.sha256((SOURCE / source['path']).read_bytes()).hexdigest() == source['sha256']
    assert capture['sources']['tags']['endpoint'] == '/api/v1/tags/list'
    assert capture['sources']['openapi']['endpoint'] == '/openapi.json'
    assert capture['live_revalidation']['saved_catalog_matches_live'] is True
    assert capture['live_revalidation']['saved_schema_matches_live'] is True


def test_every_configured_signal_and_test_symbol_matches_saved_api_metadata():
    live = json.loads((SOURCE / 'supplier-tags-2026-10-23.json').read_text())['tags']
    lookup = {raw['tag_name']: Tag.parse(raw) for raw in live}
    baseline = json.loads((ROOT / 'config/mock-tags.json').read_text())['tags']
    assert len(live) == len(lookup) == len(baseline) == 362
    assert set(lookup) == {raw['tag_name'] for raw in baseline}
    for raw in baseline:
        current = lookup[raw['tag_name']]
        for field in ('tag_name','device_address','data_type','read_write','multiplier'):
            assert getattr(current,field) == raw[field]
    for case in json.loads((ROOT / 'config/test-cases.json').read_text())['tests']:
        assert lookup[case['command_tag']].read_write == 'W'
        assert lookup[case['feedback_tag']].read_write == 'R'
        assert lookup[case['command_tag']].data_type == lookup[case['feedback_tag']].data_type == 'Bool'
    assert 'Tank01_HeaterOn' not in lookup and 'Tank1_AddWater' not in lookup
    assert lookup['Tank01_TempSV'].device_address == 'D4020'


def test_complete_difference_csv_preserves_omission_and_cosmetic_differences():
    live = {raw['tag_name']:raw for raw in json.loads((SOURCE / 'supplier-tags-2026-10-23.json').read_text())['tags']}
    baseline = {raw['tag_name']:raw for raw in json.loads((ROOT / 'config/mock-tags.json').read_text())['tags']}
    rows = list(csv.DictReader(io.StringIO((ROOT / 'docs/swagger-signal-differences-2026-10-23.csv').read_text())))
    assert len(rows) == len({row['tag_name'] for row in rows}) == 47
    expected = {name for name,raw in baseline.items() if any(raw.get(field) != live[name].get(field) for field in raw)}
    assert {row['tag_name'] for row in rows} == expected
    missing = [row for row in rows if row['changed_fields'] == 'low_limit,high_limit']
    cosmetic = [row for row in rows if row['changed_fields'] == 'description']
    assert len(missing) == 39 and len(cosmetic) == 8
    for row in rows:
        raw = live[row['tag_name']]
        assert row['device_address'] == raw['device_address']
        assert 'low_limit' not in raw and 'high_limit' not in raw
        parsed = Tag.parse(raw)
        assert parsed.low_limit is None and parsed.high_limit is None
    for row in cosmetic:
        assert ' '.join(row['pdf_description'].split()) == ' '.join(row['api_description'].split())


def test_mock_batch_uses_saved_swagger_response_shape():
    async def run():
        schema = json.loads((SOURCE / 'supplier-openapi-2026-10-23.json').read_text())['components']['schemas']
        client = MockPLCClient(ROOT / 'config/mock-tags.json')
        writes = [{'tag_name':'Tank01_TempSV','value':25.0},{'tag_name':'Tank01_TempAdj','value':-5.0}]
        result = await client.write_batch(writes)
        assert set(result) == set(schema['MultiTagWriteResponse']['required']) == {'results','count'}
        assert result['count'] == len(result['results']) == 2
        for requested,actual in zip(writes,result['results']):
            assert set(schema['TagWriteResponse']['required']).issubset(actual)
            assert actual['written'] is True
            assert actual['tag_name'] == requested['tag_name'] and actual['value'] == requested['value']
    asyncio.run(run())


def test_runtime_catalog_uses_api_metadata_without_pdf_limit_fallback(tmp_path):
    from server.log_service import LogService
    from server.signal_service import SignalService

    async def run():
        captured = json.loads((SOURCE / 'supplier-tags-2026-10-23.json').read_text())['tags']
        baseline = [Tag.parse(raw) for raw in json.loads((ROOT / 'config/mock-tags.json').read_text())['tags']]
        client = MockPLCClient(ROOT / 'config/mock-tags.json')
        client.tags = captured
        service = SignalService(client,LogService(tmp_path/'events.jsonl','test-key'),3000,baseline=baseline)
        loaded = {tag.tag_name:tag for tag in await service.load_tags()}
        assert len(loaded) == 362
        assert loaded['Tank01_TempSV'].device_address == 'D4020'
        assert loaded['Tank01_TempSV'].low_limit is None and loaded['Tank01_TempSV'].high_limit is None
        assert next(tag for tag in baseline if tag.tag_name=='Tank01_TempSV').high_limit == 999.9
        changes = [warning for warning in service.catalog_warnings if warning['code']=='CATALOG_DIFFERENCE']
        assert len(changes) == 47
        assert sum(set(warning['changed_fields'])=={'low_limit','high_limit'} for warning in changes) == 39
        assert sum(warning['changed_fields']==['description'] for warning in changes) == 8
        assert sum(warning['code']=='DUPLICATE_ADDRESS' for warning in service.catalog_warnings) == 5
    asyncio.run(run())
