"""Feedback run guidance uses only the isolated loopback fake API."""
import json

import pytest

from test_frontend_safety import browser, harness, pytestmark
from test_verifier_ui import intercept_test, start_test

CASE = 'tank01-door-open'
TAG = 'Tank01_DoorOpenRemote'


def select_pair(browser, case=CASE):
    _, _, _, js, wait_for = browser
    js("document.querySelector('[data-nav=verify]').click()")
    wait_for("return !document.getElementById('verify').classList.contains('hidden')")
    js("document.querySelector('[data-select-test=" + case + "]').click()")


def assert_reason(browser, expected, case=CASE):
    _, _, _, js, wait_for = browser
    wait_for("return document.getElementById('test-run-hint').textContent.includes(" + json.dumps(expected) + ")")
    assert js("return document.getElementById('test-run-selected').disabled")
    assert js("return document.getElementById('test-run-hint').getClientRects().length>0")
    assert js("return document.getElementById('test-run-selected').getAttribute('aria-describedby')") == 'test-run-hint'
    button = "document.querySelector('[data-test-id=" + case + "] [data-run-test]')"
    assert js('return ' + button + '.disabled')
    assert expected in js('return ' + button + '.title')
    assert js('return ' + button + ".getAttribute('aria-describedby').split(' ').some(id=>document.getElementById(id)?.textContent.includes(" + json.dumps(expected) + '))')


@pytest.mark.parametrize('blocked,expected', [
    ('readonly', 'Enable write test mode'),
    ('already-one', 'Command is already 1'),
    ('invalid-wait', 'whole-number wait limit'),
    ('missing-readback', 'verified 0'),
    ('stale', 'fresh, matching API data'),
])
def test_disabled_feedback_run_explains_why_without_sending_or_changing_results(browser, blocked, expected):
    state, _, _, js, wait_for = browser
    intercept_test(browser)
    select_pair(browser)
    assert not js("return document.getElementById('test-run-selected').disabled")
    if blocked == 'readonly':
        js("document.getElementById('mode-btn').click()")
    elif blocked == 'already-one':
        state['values'][TAG] = 1
    elif blocked == 'invalid-wait':
        js("const input=document.getElementById('test-timeout');input.value='15.5';input.dispatchEvent(new Event('input'))")
    elif blocked == 'missing-readback':
        state['values'][TAG] = None
    else:
        state['fault'] = 'signals_503'
    assert_reason(browser, expected)
    js("document.getElementById('test-run-selected').click()")
    assert js('return window.testRequests') == []
    assert not state['writes']
    assert js("return document.getElementById('test-result-state').dataset.state") == 'NOT RUN'


def test_conflicting_pending_test_has_a_reason_and_does_not_block_unrelated_pairs(browser):
    state, _, _, js, wait_for = browser
    intercept_test(browser, hold=True)
    start_test(browser)
    wait_for("return typeof window.releaseTest==='function'")
    select_pair(browser, 'tank01-door-close')
    assert_reason(browser, 'active write or pending command', 'tank01-door-close')
    select_pair(browser, 'tank03-door-open')
    assert not js("return document.getElementById('test-run-selected').disabled")
    assert 'Ready to run' in js("return document.getElementById('test-run-hint').textContent")
    assert js('return window.testRequests') == [{'id': CASE, 'end_mode': 'manual0'}]
    assert not state['writes']
    js('window.releaseTest()')
