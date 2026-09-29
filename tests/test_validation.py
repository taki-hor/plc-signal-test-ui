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

@pytest.mark.parametrize('kind', ['Word','Float'])
def test_numeric_engineering_value_unchanged_and_limits(kind):
    signal = tag(kind, low=0, high=50)
    assert signal.validate_write(25.0) == 25.0
    with pytest.raises(ValidationError): signal.validate_write(-0.1)
    with pytest.raises(ValidationError): signal.validate_write(50.1)
    with pytest.raises(ValidationError): signal.validate_write(float('nan'))
