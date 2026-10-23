# Functional improvement port — 23 October 2026

Source: `/home/ano/Downloads/plc-signal-test-ui-full-2026-10-22/plc-signal-test-ui`.
Destination: `/home/ano/development/plc-signal-test-ui`.

The original project already contains the source copy's other backend, configuration,
transport, validation and test-runner improvements. Its worktree had existing
uncommitted changes; those were retained. This is a selective local code port,
with no Git merge, commit or push.

## Imported

- Every single-write receipt now includes `console_command_baseline_utc`, normalized
  from the final validated supplier snapshot immediately before dispatch. This also
  covers unmapped commands and value 0.
- Checklist Keep at 1 and verified clear to 0 require a supplier timestamp strictly
  newer than that backend snapshot, the browser baseline and write acceptance.
  Cached readback therefore cannot qualify when validation advances to a slightly
  future supplier timestamp.
- Missing or legacy receipt evidence leaves new readback unverified and uses the
  existing hint area to explain recovery. Completed historical records remain intact.
- JSON event records and CSV exports include the new timestamp.
- Backend and isolated-browser regressions and the relevant operating documentation.

## Retained original UI and behavior

HTML, CSS, sidebar/router, page labels, layout, controls, write gates and other page
modules are byte-for-byte unchanged from the destination at the start of this task.
Only the checklist's verification logic, audit data and missing-evidence hint changed.
The source's tab UI, workflow classifier/guides, badges, filters, button relabeling and
activity banner were excluded.

The original pagehide and restored-WAITING protections remain: interrupted completion
monitoring cannot resume and produce a measured result after a reload. The source
copy removes those protections; that change was excluded.

## Verification

- Before changes, existing non-browser suite: **131 passed**.
- Four imported browser regressions reproduced the cached/missing-baseline defect
  against the original logic: **4 failed** before the fix.
- After the port: **172 passed in 35.96 seconds**, including **38 Firefox cases**,
  using `env -u PYTHONPATH PLC_MOCK_MODE=true .venv/bin/python -m pytest -q`.
- `git diff --check` passed; file hashes confirmed the UI assets and unrelated
  original files were preserved.
- Restarted the original backend gracefully at `http://127.0.0.1:8080` in mock mode.
  Chrome showed the original sidebar UI, 362/0 tags, fresh data and READ-ONLY MODE.
  No live PLC write or physical test was performed.


## Value write read-signal feedback

Added a panel within the existing Value write page, retaining the original sidebar
and page layout. It shows all live read-only tags (221 in the mock catalog), puts
mapped and same-group signals first, shows both door position signals, and supports
search and a selected-group filter. It remains available in read-only mode.

Single and batch receipts include all read-only values from the final validated
pre-dispatch poll, UTC timestamps and configured mapping evidence, including
unconfirmed candidates. Browser records separate baseline values, retained later
readings, live values and mapping status. Only a fresh poll strictly newer than
both the baseline and accepted receipt can qualify as a subsequent observation.
Already-set signals and candidate mappings cannot become confirmed transitions.
Partial or mismatched batch receipts do not qualify as full acceptance.

The last 50 manual requests are retained per API/mode in browser storage, with
JSON/CSV export. Record current read values captures a later numeric reading
without sending a command, resuming interrupted monitoring or certifying a mapping.
Reload, stale/disconnected data, leaving Remote, and subsequent manual writes
interrupt unfinished observation. Accepted, rejected and uncertain outcomes stay
separate. No automatic reset or retry was added.

Validation: **191 passed in 44.03 seconds**, including **51 isolated Firefox
cases**. Final batch-selection and manual capture checks: **3 passed in 4.40
seconds**. JavaScript syntax and `git diff --check` passed. The original mock
backend was restarted and Chrome showed Tank01 door-open selected, DoorClosed=1,
DoorOpened=0, and all 221 read signals. The preview stayed read-only and sent no
commands. No live PLC or physical test was performed for this feature.
