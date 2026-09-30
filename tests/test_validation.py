import json
from pathlib import Path
import pytest
from server.models import Tag, ValidationError

def tag(kind='Word', rw='W', low=None, high=None):
    return Tag.parse({'tag_name':'Sample','device_address':'D1','data_type':kind,'read_write':rw,'multiplier':0.1,'description':'Sample','low_limit':low,'high_limit':high})

def test_metadata_parsing_and_description_fallback():
    raw = {'tag_name':'X','device_address':'M1','data_type':'Bool','read_write':'R','multiplier':1,'description':'','low_limit':'','high_limit':''}
    parsed = Tag.parse(raw)
    assert parsed.description == 'X' and parsed.low_limit is None and parsed.high_limit is None

def test_read_only_write_blocked():
    with pytest.raises(ValidationError, match='read-only'): tag(rw='R').validate_write(1)

@pytest.mark.parametrize('value',[-1,2,0.5,True,'1'])
def test_bool_rejects_invalid(value):
    with pytest.raises(ValidationError): tag('Bool').validate_write(value)

def test_bool_accepts_zero_and_one():
    assert tag('Bool').validate_write(0) == 0
    assert tag('Bool').validate_write(1) == 1

@pytest.mark.parametrize('kind', ['Word','SignedWord','Float'])
def test_numeric_engineering_value_unchanged_and_limits(kind):
    signal = tag(kind, low=0, high=50)
    assert signal.validate_write(25.0) == 25.0
    with pytest.raises(ValidationError): signal.validate_write(-0.1)
    with pytest.raises(ValidationError): signal.validate_write(50.1)
    with pytest.raises(ValidationError): signal.validate_write(float('nan'))

@pytest.mark.parametrize('value', [-999.0, -5.0, 0, 25.0, 999.9])
def test_signed_word_accepts_engineering_values(value):
    assert tag('SignedWord', low=-999.0, high=999.9).validate_write(value) == value

@pytest.mark.parametrize('value', [-999.1, 1000.0, float('nan'), float('inf'), float('-inf'), '-5', True, False])
def test_signed_word_rejects_invalid_values(value):
    with pytest.raises(ValidationError):
        tag('SignedWord', low=-999.0, high=999.9).validate_write(value)

def test_temp_adjustment_metadata_regression():
    catalog = json.loads((Path(__file__).resolve().parents[1] / 'config/mock-tags.json').read_text())
    signal = Tag.parse(next(t for t in catalog['tags'] if t['tag_name'] == 'Tank01_TempAdj'))
    assert (signal.data_type, signal.device_address, signal.multiplier, signal.low_limit, signal.high_limit) == (
        'SignedWord', 'D4010', 0.1, -999.0, 999.9)

@pytest.mark.parametrize('field,value', [('data_type','Unknown'), ('read_write','RW'),
    ('multiplier',0), ('multiplier',-0.1), ('multiplier',True), ('multiplier',float('inf')),
    ('low_limit',float('nan')), ('high_limit',float('inf')), ('low_limit',True),
    ('high_limit','invalid'), ('tag_name',''), ('device_address',''), ('tag_name',None), ('device_address',123)])
def test_invalid_metadata_rejected(field, value):
    raw = dict(tag().__dict__)
    raw[field] = value
    with pytest.raises(ValidationError): Tag.parse(raw)

def test_reversed_metadata_limits_rejected():
    with pytest.raises(ValidationError): tag(low=10, high=5)

def test_bool_supplier_limits_are_enforced():
    with pytest.raises(ValidationError): tag('Bool', low=0, high=0).validate_write(1)
