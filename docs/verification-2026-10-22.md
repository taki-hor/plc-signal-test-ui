# Verification — 2026-10-22

The initial phase used read-only real tests. The operator later authorized the
individual physical tests recorded below. Software regression tests used mock
clients or the isolated browser-test API.

## Real signal reads

The console at `http://127.0.0.1:8080` uses the supplier API at
`http://192.168.1.12:8000`, with `PLC_MOCK_MODE=false` and the credential held
only in the ignored `.env`.

All **362 catalog signals passed five successive read samples**. Each sample
had zero missing tags, nulls, invalid values or supplier-reported read failures.
The scan observed four different supplier poll snapshots. The catalog contains
277 Bool, 69 Word, eight SignedWord and eight Float tags. It marks 221 tags R
and 141 tags W. Reading a W tag does not issue a write. The scan checked Bool
values against 0/1. It checked the other types for finite numeric values. This verifies
transport, parsing and reported values, not physical sensor calibration or
command effects.

Local per-tag evidence is saved outside the repository in
`/home/nep/Documents/api_test/artifacts/`:

- `plc-signal-test-ui-all-signals-read-2026-10-22.json`
- `plc-signal-test-ui-all-signals-read-2026-10-22.csv`

The report includes metadata, latest value, sample count and PASS/FAIL for every
catalog tag. After the fixes, the app restarted and the read scan ran again.
The local artifacts retain the latest run timestamp.

## Confirmed software bugs fixed

1. The manual and batch confirmation dialog clears its previous return value
   before reopening. Confirm followed by Escape cannot submit another command.
2. The test runner checks feedback again at final write validation and requires
   a newer, corrected supplier timestamp at or after write acceptance. It does
   not use cyclic poll_count as a monotonic sequence.
3. Single, batch and configured reset writes recheck authorization immediately
   before dispatch. Tests also recheck authorization during feedback waiting.
   Disable/expiry during validation prevents the unsent command.
4. The remaining monotonic test deadline limits each feedback read.
   Late or unresponsive reads cannot produce PASS. The real and mock client wait
   helpers follow the same deadline rule.
5. A failed, malformed or overdue frontend refresh invalidates cached healthy
   state and disables write/test controls. Read requests time out after ten
   seconds. The stale-data watchdog acts sooner. POST requests allow sixty
   seconds for validation and configured feedback waiting.

Additional guards reject overlapping local writes/tests and malformed command
identities. Leaving Remote mode during verification blocks PASS. Disabling a
mode does not recall a command already submitted to the supplier. External PLC
clients are outside the local command lock. Recorded feedback remains timing
and state evidence, not proof that no external action influenced it.

## Automated checks

`env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider`

**161 passed in 54.67 seconds** after the edge-case review. This count includes
30 real-Firefox browser tests against a fake loopback API. The browser tests
require Firefox and geckodriver. The suite explicitly skips them on hosts
without those programs. No new Python dependency was added.
`git diff --check` passed. Changes are local and uncommitted.

## Temporary clock configuration and remaining field blockers

The supplier timestamps omit an offset. The operator confirmed Hong Kong time.
The supplier host clock was about 44 seconds behind this workstation, while its
polls advanced normally. This test uses:

```dotenv
PLC_TIMESTAMP_TIMEZONE=Asia/Hong_Kong
PLC_TIMESTAMP_OFFSET_SECONDS=44
PLC_STALE_AFTER_MS=3000
```

The UI labels the temporary +44-second correction. Raw supplier timestamps are
preserved and frozen data still exceeds the three-second stale limit. **After
synchronizing the API host clock, reset the offset to 0 and restart `./start`.**
Remeasure if either clock changes. The correction also affects the test runner's
supplier-timestamp comparison with write-acceptance time.

The 36 mappings marked `requires_confirmation=true` remain blocked. No command pulse, latch
or reset behavior was inferred. The agent operated only the operator-confirmed
Tank 01 door sequence below. The agent did not field-test other tanks, batches,
writable Float tags or unconfirmed mappings. Later operator UI exercises are
separate evidence. The supplier's duplicate addresses and live metadata
differences remain visible for supplier review.


## Individual physical tests — Tank 01

The operator confirmed area readiness for each movement. The operator specified
that commands must stay at 1 until movement finished. Physical confirmation was
required before each clear to 0. Both remote command bits were verified 0 before
the next direction was issued. Write mode was disabled after each command and
clear operation.

| Test | Observation limit | Software result | Operator observation | Command clear |
| --- | --- | --- | --- | --- |
| Initial open | 5 s | TIMEOUT at 5.002 s | Opened confirmed | 0 verified |
| Close | 30 s | PASS at 8.704 s | Closed confirmed | 0 verified |
| Repeat open | 30 s | PASS at 6.625 s | Opened confirmed | 0 verified |
| Restore close | 30 s | PASS at 8.453 s | Closed confirmed | 0 verified |

The original open TIMEOUT is preserved. A later poll agreed with the operator's
first open observation, but that does not qualify the original five-second
window as PASS. The operator then approved a thirty-second observation window
for Tank 01 open/close. The repeat open passed in 6.625 seconds. Close passed in
8.704 seconds and the final restore-close passed in 8.453 seconds. These are
software feedback latencies, not independent measurements of mechanical travel.

The change set only the two Tank 01 case timeouts to 30000 ms. The configuration
validation test passed afterward. The agent did not operate or retime other tanks.
No automatic command retry or inferred pulse/reset was used. Commands were
cleared only after the operator confirmed completion, and subsequent polls
verified the clear.

**Final state: DoorOpened=0, DoorClosed=1, DoorOpenRemote=0, DoorCloseRemote=0.**
Tank 01 is restored to its starting closed position and the automation's write
tokens were disabled after the final clear.

Per-step JSON and the combined JSON/CSV summary are stored locally in
`/home/nep/Documents/api_test/artifacts/`. The summary files are:

- `plc-signal-test-ui-tank01-physical-test-summary-2026-10-22.json`
- `plc-signal-test-ui-tank01-physical-test-summary-2026-10-22.csv`


## 0/1 checklist UI update

The operator requested one confirmation before each send. The UI therefore has
no readiness checkboxes or physical-confirmation buttons. It lists all 102
writable Bool commands with search/group/progress filters and keeps all 141
writable tags in the existing Manual write form. API receipts, later 0 readback,
notes, issue recording, attempt timing, browser-local history and CSV/JSON
exports form the checklist. No new dependency was added.

The browser regression tests cover these behaviors:

- Command counts and read-only, failed-refresh and unresponsive-refresh guards.
- One confirmation with Escape cancellation for both values.
- No automatic write or clear, timer updates and retained log details.
- Export contents and escaping of spreadsheet formulas.
- History after reload with write mode off.
- Rejection of pre-clear poll timestamps, including a slightly fast corrected supplier clock.
- Isolation of pending commands and issue cleanup without loss of history.
 The clear check also requires a timestamp later than the pre-clear snapshot.
This rejects cached 0 even when the corrected clock is slightly fast.
The backend test checks that a naive Hong Kong supplier timestamp
with the temporary correction compares correctly against a UTC write receipt.

Desktop (1380 px) and narrow (430 px) Firefox previews used the isolated fake API.
Neither layout had horizontal overflow. In this initial UI revision, the timer
included operator and network delay. The later update below measures completion
feedback time instead. **API CYCLE COMPLETE** means accepted 1, accepted 0 and
later 0 readback. It does not certify physical operation. Operator observations belong in notes.
No real PLC write was performed for this UI update.

The final read-only smoke check followed the app restart. It confirmed REAL
mode, REMOTE and fresh data. All 362 tags were readable across five new samples
and four advancing supplier snapshots.

A separate Firefox profile loaded the real page. It confirmed 102 checklist
commands, 141 Manual write choices, automatic updates and the configured
Tank 01 feedback reference. Write mode stayed off.
Tank 01 remained closed with both remote command bits 0. Local smoke reports and
a page screenshot are saved in the artifacts directory.

The review checked callers, configuration, tests and documentation across the
complete uncommitted diff, including all three new files. Credential and whitespace checks
passed for all 25 changed files. The private `.env` stays ignored. The credential
files remain permission 0600. No commit or push was performed.

## Operator UX follow-up — completion timing and maintained states

The actual operator browser log confirmed a local 403 at 08:08:55 UTC (write
mode disabled/expired) was incorrectly left as a pending 1. It also showed the
open record started 3.476 seconds before Send 1 and finished only after manual
clear/readback. The logged 22.651-second open attempt and 19.585-second close
attempt were cycle/interaction durations, not API completion feedback times.
The historical records are retained. Their missing completion times cannot be
reconstructed from the clear events. A private pre-fix browser-log snapshot is
saved in the workspace artifacts, outside Git.

The timer now starts only at Confirm Send 1. A confirmed mapping's final
pre-dispatch baseline comes from the backend, and completion requires a fresh
API poll strictly later than both baseline and acceptance. It stops at the
opened/closed feedback, independently of Send 0. API response latency is shown
separately. New attempt stays at zero and cannot generate more unused attempts.
Already-set, unknown, interrupted or early-cleared feedback is not timed as a
confirmed transition. The separate configured verification runner retains its
existing deadlines and PASS rules. Manual monitoring does not award that PASS.

Status now validates the requesting browser's token. Disabling write mode
clears local authorization immediately. An old status response cannot revoke a
newer token. Explicit local pre-dispatch rejections do not require clearing a
command that was never sent. Historical local authorization-rejection records
are recovered without deleting their evidence. Unknown write outcomes remain
pending. The page names the reason a write button is disabled.

The operator also requested maintained non-door states. The supplier manual
labels On/Auto controls but does not define every pulse/reset rule. After an
accepted write and later readback of 1, the operator can explicitly Keep at 1
for a non-door command. This sends nothing, records the decision, keeps the
active state visible, and permits another guided test. Clearing a prior held
command remains possible while another command is pending. Doors cannot use
Keep at 1. The 36 unconfirmed feedback mappings remain blocked.

The browser regressions cover all reported UX failures and completion arriving
after acceptance but before clear. They also cover frozen feedback, preexisting
completion, unknown outcomes, old 403 recovery and token/status races. Coverage
includes maintained-state readback and clearing held commands during another
pending command. All
simulated writes use an isolated fake API. No PLC write was issued by the agent
for this update.

## Additional edge-case review

Regression tests first reproduced three failures:

- Notes entered before the first send were lost.
- A delayed early-clear request allowed false completion feedback.
- Unfinished transport states remained stuck after reload.
 Backend regressions reproduced
supplier catalog/read failures returning no indication that dispatch had never
started. Ten new cases failed against the previous implementation. Three
control cases passed. All 13 focused regressions pass after the fixes.

Preparation notes now survive selection and reload without starting the timer.
The UI tracks an early clear before its response arrives. It distinguishes
blocked, accepted and unknown outcomes. In-flight states restored after a reload
become unknown without re-sending a command. Catalog/read failures before both
single and batch writes explicitly return `write_dispatched=false`. Simulated
failures after write transport starts remain uncertain, including a test where
the mock value has already changed before acknowledgement is lost.

The complete suite passed after this review: **161 passed in 54.67 seconds**,
including 30 isolated Firefox cases. No live write was used to reproduce or
validate these fixes. The full changed-file credential and whitespace checks
were repeated before handoff.

## Hold/reset documentation and push preparation

The [hold/reset findings](signal-test-plan.md#command-hold-and-reset-findings)
cover all 102 writable Bool tags in five groups and identify the source manual
and page references. Always On, Auto and Remote On descriptions support working
interpretations, rather than confirmed PLC hold/reset rules. The Tank 01
hold-until-complete, then-clear sequence is explicitly identified as operator
confirmation and field evidence. RemoteStart remains unclassified, and 0 is
not documented as a guaranteed stop under other active PLC logic. No mapping,
reset behavior or application code was changed for this documentation update.

The operator requested staged changes only. Remote main was fetched and matched
the local base before staging. The staged change contains the UI fixes, new
files and documentation together. Credentials, browser logs and local artifacts
stay outside that change. No commit or push is performed in this preparation
step.

## Local installation and reload timing fix

The 25-file staged update was applied over the complete project at
`/home/ano/development/plc-signal-test-ui`. The launcher, dependencies, tag and
safety configuration, supporting modules, Git history, and existing `.env`
were retained. A private rollback archive of the previous project, excluding
the virtual environment and Python caches, is saved in Downloads as
`plc-signal-test-ui-before-update-2026-10-22-173915.tar.gz`.

Two browser regression tests reproduced the reload bug. An accepted command with
completion still WAITING could resume after a page reload and report CONFIRMED.
This included transitions that occurred while the page was closed. Leaving the
page now interrupts an unfinished measurement. Restored WAITING records are also
marked MONITORING INTERRUPTED, covering closures where the page could not save
its final state. The UI awards no completion time across that gap. Accepted
commands and history remain available for explicit manual clearing. Previously
confirmed timing remains unchanged.

The installed project passed **165 tests**, including **34 Firefox browser
cases**, with:

```bash
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

The actual `./start` launcher and a Firefox page were also checked together
against the installed backend in mock mode. All nine imported JavaScript
modules loaded, all 362 tags were readable, and the page showed 102 checklist
commands and 141 Manual write choices. Startup was READ-ONLY MODE with fresh
Remote data and write controls disabled. No mode-enable, write or test command
was sent during this launcher check. The temporary server was stopped afterward.
`bash -n start` and whitespace checks passed.

For the next session, run `./start` from the installed project and open
`http://127.0.0.1:8080`. The preserved local `.env` currently selects mock
mode. The launcher will keep that configuration. Use the README's configuration
instructions when preparing a real API session. No supplier timezone or clock
correction was guessed or copied into the local `.env`. This
installation check used mock data. The earlier field results above are retained
evidence from the staged documentation.