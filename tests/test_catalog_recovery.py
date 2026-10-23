"""Command catalog recovery uses only the loopback browser harness."""
import time

from test_frontend_safety import browser, harness, pytestmark


def test_failed_initial_catalog_recovers_after_network_returns(harness):
    state, wd, prefix, js, wait_for, url = harness
    state['fault'] = 'catalog_503'
    state['mode'] = False
    state['writes'].clear()
    wd(prefix + '/url', {'url':url + '#/commands'})
    try:
        wait_for("return document.getElementById('freshness').textContent==='FRESH'")
        wait_for("return document.getElementById('bool-empty-message')?.textContent.includes('catalog unavailable')")
        assert js("return document.querySelectorAll('[data-command-tag]').length") == 0
        assert js("return !document.getElementById('bool-catalog-retry').classList.contains('hidden')")
        state['fault'] = None
        wait_for("return document.querySelectorAll('[data-command-tag]').length===102 && document.getElementById('write-tag').options.length===141")
        assert js("return document.getElementById('bool-empty').classList.contains('hidden')")
        assert js("return document.getElementById('write-banner-title').textContent==='READ-ONLY MODE'")
        assert js("return document.getElementById('bool-one').disabled && document.getElementById('bool-zero').disabled")
        assert state['mode'] is False and not state['writes']
    finally:
        state['fault'] = None
        wd(prefix + '/url', {'url':'about:blank'})


def test_valid_empty_catalog_does_not_retry_forever(harness):
    state, wd, prefix, js, wait_for, url = harness
    state['fault'] = 'catalog_empty'
    state['mode'] = False
    wd(prefix + '/url', {'url':url + '#/commands'})
    try:
        wait_for("return document.getElementById('freshness').textContent==='FRESH'")
        wait_for("return document.getElementById('bool-empty-message')?.textContent.includes('No writable 0/1 commands')")
        reads = state['catalog_reads']
        state['fault'] = None
        time.sleep(.8)
        assert state['catalog_reads'] == reads
        assert js("return document.querySelectorAll('[data-command-tag]').length") == 0
        assert js("return document.getElementById('bool-catalog-retry').classList.contains('hidden')")
    finally:
        state['fault'] = None
        wd(prefix + '/url', {'url':'about:blank'})


def test_empty_command_filters_explain_and_restore_list(browser):
    state, _, _, js, wait_for = browser
    js("document.getElementById('bool-search').value='no-such-command'; document.getElementById('bool-search').dispatchEvent(new Event('input'))")
    wait_for("return document.getElementById('bool-empty-message')?.textContent==='No commands match your filters.'")
    assert js("return document.querySelectorAll('[data-command-tag]:not(.hidden)').length") == 0
    js("document.getElementById('bool-clear-filters').click()")
    wait_for("return document.querySelectorAll('[data-command-tag]:not(.hidden)').length===102")
    assert js("return document.getElementById('bool-empty').classList.contains('hidden')")
    js("document.getElementById('bool-filter').value='complete'; document.getElementById('bool-filter').dispatchEvent(new Event('input'))")
    wait_for("return !document.getElementById('bool-empty').classList.contains('hidden')")
    assert not state['writes']
