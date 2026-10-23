# Verification — 2026-10-22

The initial real-test phase was read only. The operator later authorized the
individual physical tests recorded below. Simulated software regressions used
mock clients or the isolated browser-test API.

## Real signal reads

The console at `http://127.0.0.1:8080` uses the supplier API at
`http://192.168.1.12:8000`, with `PLC_MOCK_MODE=false` and the credential held
only in the ignored `.env`.

All **362 catalog signals passed five successive read samples**. Each sample
had zero missing tags, nulls, invalid values or supplier-reported read failures.
Four different supplier poll snapshots were observed. The catalog contains
277 Bool, 69 Word, eight SignedWord and eight Float tags; 221 are marked R and
141 W. Reading a W tag does not issue a write. Bool values were checked against
0/1; the other types were checked for finite numeric values. This verifies
transport, parsing and reported values, not physical sensor calibration or
command effects.

Local per-tag evidence is saved outside the repository in
`/home/nep/Documents/api_test/artifacts/`:

- `plc-signal-test-ui-all-signals-read-2026-10-22.json`
- `plc-signal-test-ui-all-signals-read-2026-10-22.csv`

The report includes metadata, latest value, sample count and PASS/FAIL for every
catalog tag. The app was restarted after the fixes and the read scan repeated;
the local artifacts retain the latest run timestamp.

## Confirmed software bugs fixed

1. The manual and batch confirmation dialog clears its previous return value
   before reopening. Confirm followed by Escape cannot submit another command.
2. The test runner checks feedback again at final write validation and requires
   a newer, corrected supplier timestamp at or after write acceptance. It does
   not use cyclic poll_count as a monotonic sequence.
3. Single, batch and configured reset writes recheck authorization immediately
   before dispatch. Tests also recheck authorization during feedback waiting.
   Disable/expiry during validation prevents the unsent command.
4. Each feedback read is bounded by the remaining monotonic test deadline;
   late or hung responses cannot produce PASS. The real and mock client wait
   helpers follow the same deadline rule.
5. A failed, malformed or overdue frontend refresh invalidates cached healthy
   state and disables write/test controls. Read requests time out after ten
   seconds; the stale-data watchdog acts sooner. POST requests allow sixty
   seconds for validation and configured feedback waiting.

Additional guards reject overlapping local writes/tests and malformed command
identities. Leaving Remote mode during verification blocks PASS. Disabling a
mode does not recall a command already submitted to the supplier. External PLC
clients are outside the local command lock; recorded feedback remains timing
and state evidence, not proof that no external action influenced it.

## Automated checks

`env -u PYTHONPATH PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider`

**161 passed in 54.67 seconds** after the edge-case follow-up, including 30
real-Firefox browser tests against a fake loopback API. The browser tests require Firefox and geckodriver and are
explicitly skipped on hosts without them. No new Python dependency was added.
`git diff --check` passed. Changes are local and uncommitted.

## Temporary clock configuration and remaining field blockers

The supplier timestamps omit an offset; the operator confirmed Hong Kong time.
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

The 36 mappings marked `requires_confirmation=true` remain blocked. No command
pulse, latch or reset behavior was inferred. The agent-operated physical tests cover only the operator-confirmed Tank 01
door sequence below. No other tank, batch, writable Float or unconfirmed mapping
was field-tested by the agent; later operator UI exercises are separate evidence. The supplier's duplicate-address and live
metadata differences remain visible for supplier review.


## Individual physical tests — Tank 01

The operator confirmed area readiness for each movement and specified holding
commands at 1 until movement finished, then clearing to 0 after physical
confirmation. Both remote command bits were verified 0 before the next direction
was issued. Write mode was disabled after each command and clear operation.

| Test | Observation limit | Software result | Operator observation | Command clear |
| --- | --- | --- | --- | --- |
| Initial open | 5 s | TIMEOUT at 5.002 s | Opened confirmed | 0 verified |
| Close | 30 s | PASS at 8.704 s | Closed confirmed | 0 verified |
| Repeat open | 30 s | PASS at 6.625 s | Opened confirmed | 0 verified |
| Restore close | 30 s | PASS at 8.453 s | Closed confirmed | 0 verified |

The original open TIMEOUT is preserved. A later poll agreed with the operator's
first open observation, but that does not qualify the original five-second
window as PASS. The operator then approved a thirty-second observation window
for Tank 01 open/close. The repeat open passed in 6.625 seconds; close passed in
8.704 seconds and the final restore-close passed in 8.453 seconds. These are
software feedback latencies, not independent measurements of mechanical travel.

Only the two Tank 01 case timeouts were changed to 30000 ms; the configuration
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

The browser regressions cover command counts, read-only and failed/hung-refresh
guards, one confirmation with Escape cancellation for both values, no automatic
write/clear, timer updates, retained log details, export contents and spreadsheet
formula escaping, history after reload with write mode off, rejection of
pre-clear poll timestamps (including a slightly fast corrected supplier clock),
pending-command isolation, and issue cleanup without
losing history. The clear check also requires a timestamp later than the pre-clear snapshot,
so a slightly fast corrected clock cannot let cached 0 count as a new readback.
The backend test checks that a naive Hong Kong supplier timestamp
with the temporary correction compares correctly against a UTC write receipt.

Desktop (1380 px) and narrow (430 px) Firefox previews used the isolated fake API.
Neither layout had horizontal overflow. At this initial UI revision, the
timer included operator and network delay; the follow-up below replaces it with
completion feedback timing. **API CYCLE COMPLETE** means accepted 1, accepted 0 and later 0 readback;
it does not certify physical operation. Operator observations belong in notes.
No real PLC write was performed for this UI update.

The final read-only smoke check after restarting the app confirmed REAL mode,
REMOTE, fresh data, all 362 tags readable across five new samples and four
advancing supplier snapshots. A separate Firefox profile loaded the real page,
confirmed 102 checklist commands and 141 Manual write choices, verified automatic
updates and the configured Tank 01 feedback reference, and kept write mode off.
Tank 01 remained closed with both remote command bits 0. Local smoke reports and
a page screenshot are saved in the artifacts directory.

The complete uncommitted diff, including all three new files, was reviewed for
callers, configuration, tests and documentation. Credential and whitespace checks
passed for all 25 changed files. The private `.env` stays ignored; the credential
files remain permission 0600. No commit or push was performed.

## Operator UX follow-up — completion timing and maintained states

The actual operator browser log confirmed a local 403 at 08:08:55 UTC (write
mode disabled/expired) was incorrectly left as a pending 1. It also showed the
open record started 3.476 seconds before Send 1 and finished only after manual
clear/readback. The logged 22.651-second open attempt and 19.585-second close
attempt were cycle/interaction durations, not API completion feedback times.
The historical records are retained; their missing completion times cannot be
reconstructed from the clear events. A private pre-fix browser-log snapshot is
saved in the workspace artifacts, outside Git.

The timer now starts only at Confirm Send 1. A confirmed mapping's final
pre-dispatch baseline comes from the backend, and completion requires a fresh
API poll strictly later than both baseline and acceptance. It stops at the
opened/closed feedback, independently of Send 0. API response latency is shown
separately. New attempt stays at zero and cannot generate more unused attempts.
Already-set, unknown, interrupted or early-cleared feedback is not timed as a
confirmed transition. The separate configured verification runner retains its
existing deadlines and PASS rules; manual monitoring does not award that PASS.

Status now validates the requesting browser's token. Disabling write mode
clears local authorization immediately; an old status response cannot revoke a
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

The browser regressions cover all reported UX failures, completion arriving
after acceptance but before clear, frozen feedback, preexisting completion,
unknown outcomes, old 403 recovery, token/status races, maintained-state
readback, and clearing held commands during another pending command. All
simulated writes use an isolated fake API. No PLC write was issued by the agent
for this update.

## Additional edge-case review

Regression tests first reproduced loss of notes entered before the first send,
false completion feedback during a delayed early-clear request, and unfinished
transport states remaining stuck after reload. Backend regressions reproduced
supplier catalog/read failures returning no indication that dispatch had never
started. Ten new cases failed against the previous implementation; three
control cases passed. All 13 focused regressions pass after the fixes.

Preparation notes now survive selection and reload without starting the timer.
Early clear is tracked before its response arrives; blocked, accepted and
unknown outcomes are distinguished. In-flight states restored after a reload
become unknown without re-sending a command. Catalog/read failures before both
single and batch writes explicitly return `write_dispatched=false`; simulated
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
the local base before staging. The UI fixes, new files and documentation are
prepared together; credentials, browser logs and local artifacts stay outside
the staged change. No commit or push is performed in this preparation step.

## Local installation and reload timing fix

The 25-file staged update was applied over the complete project at
`/home/ano/development/plc-signal-test-ui`. The launcher, dependencies, tag and
safety configuration, supporting modules, Git history, and existing `.env`
were retained. A private rollback archive of the previous project, excluding
the virtual environment and Python caches, is saved in Downloads as
`plc-signal-test-ui-before-update-2026-10-22-173915.tar.gz`.

Two browser regressions reproduced the reload bug: an accepted command whose
completion was still WAITING could resume after a page reload and report
CONFIRMED, including when the transition happened while the page was closed.
Leaving the page now interrupts an unfinished measurement. Restored WAITING
records are also marked MONITORING INTERRUPTED, covering closures where the
page could not save its final state. No completion time is awarded across that
gap. Accepted commands and history remain available for explicit manual
clearing; previously confirmed timing is preserved.

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
`http://127.0.0.1:8080`. The preserved local `.env` currently selects mock mode;
the launcher will keep that configuration. Use the README's configuration
instructions when preparing a real API session. No supplier timezone or clock
correction was guessed or copied into the local `.env`. This installation
check used mock data; the earlier field results above are retained evidence
from the staged documentation.
