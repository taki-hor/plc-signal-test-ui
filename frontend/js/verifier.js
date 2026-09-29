import {$, node} from './dom.js';
import {post, modeEnabled} from './api.js';
let cases = [], status = null, running = false;
export function updateVerifier(nextCases, nextStatus) {
  if (nextCases) cases = nextCases;
  if (nextStatus) status = nextStatus;
  const list = $('test-list'); list.replaceChildren();
  for (const test of cases) {
    const card = node('div', 'test-card'), row = node('div','row');
    row.append(node('h3','',test.name),node('span',`pill ${test.requires_confirmation ? 'amber' : ''}`,test.requires_confirmation ? 'NEEDS CONFIRMATION' : 'CONFIGURED'));
    card.append(row,node('p','',`WRITE ${test.command_tag} = ${test.command_value}\nEXPECT ${test.feedback_tag} = ${test.expected_feedback}\nTIMEOUT ${(test.timeout_ms/1000).toFixed(1)} s`));
    const button = node('button','button small primary','Run test'); button.type = 'button';
    button.disabled = running || test.requires_confirmation || !modeEnabled() || !status?.data_fresh || status?.plc_mode !== 'REMOTE';
    button.addEventListener('click', () => runTest(test)); card.append(button); list.append(card);
  }
}
async function runTest(test) {
  if (!window.confirm(`Run ${test.name}? This sends ${test.command_tag}=${test.command_value} to the PLC. No automatic reset is configured.`)) return;
  running = true; updateVerifier();
  $('test-result').textContent = `RUNNING · ${test.name} · waiting for feedback…`;
  try {
    const result = await post('/api/test/run',{id:test.id});
    const report = node('div','report');
    report.append(node('strong', result.result === 'PASS' ? 'good' : 'bad',`${result.result} · ${result.test_name}`),
                  node('p','',`Command: ${result.command} · HTTP: ${result.http_status ?? '—'}`),
                  node('p','',`Expected: ${result.expected_feedback} · Actual: ${result.actual_feedback ?? 'NO DATA'}`),
                  node('p','',`Elapsed: ${result.elapsed_ms} ms${result.error ? ` · ${result.error}` : ''}`));
    $('test-result').replaceChildren(report);
  } catch (error) { $('test-result').textContent = `COMMUNICATION ERROR · ${error.message}`; }
  finally { running = false; updateVerifier(); }
}
