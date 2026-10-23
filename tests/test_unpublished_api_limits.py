"""Missing supplier limit metadata is not presented as an unlimited range."""
import json

import pytest

from test_frontend_safety import browser, harness, pytestmark


@pytest.mark.parametrize('limits,expected', [
    ({},'API limits: Not published'),
    ({'low_limit':0},'API limits: 0.0 to not published'),
    ({'high_limit':999.9},'API limits: not published to 999.9'),
])
def test_unpublished_bounds_are_labelled_without_inventing_values_or_sending_writes(browser, limits, expected):
    state, _, _, js, wait_for = browser
    js("window.limitFetch=window.fetch;window.fetch=async (url,options)=>{const response=await window.limitFetch(url,options);if(url!=='/api/tags')return response;const data=await response.json();data.tags=data.tags.map(tag=>{if(tag.tag_name!=='Tank01_TempSV')return tag;const {low_limit,high_limit,...other}=tag;return {...other,..."+json.dumps(limits)+"}});return new Response(JSON.stringify(data),{status:200,headers:{'Content-Type':'application/json'}})};location.hash='#/write';document.getElementById('write-tag').value='Tank01_TempSV';document.getElementById('write-tag').dispatchEvent(new Event('change'));document.getElementById('refresh-btn').click()")
    wait_for("return document.getElementById('write-limits').textContent.startsWith("+json.dumps(expected)+")")
    assert 'unbounded' not in js("return document.getElementById('write-limits').textContent+document.getElementById('write-detail').textContent")
    assert js("return [...document.getElementById('write-detail').querySelectorAll('span')].some(span=>span.textContent==='API limits')")
    assert not state['writes']
