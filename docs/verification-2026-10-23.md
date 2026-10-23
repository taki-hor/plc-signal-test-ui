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


## Feedback, command modes and read-view update

This update uses GitHub `main` at `76d0d0b` as its base. It retains the sidebar
and Value write feedback feature. The earlier local snapshot remains on
`backup/local-before-github-2026-10-23`. Push preparation is recorded below.

### Diagnosed field reports

Operator-run supplier logs show Tank 01 open PASS with DoorOpened=1 in 5828 ms,
and close PASS with DoorClosed=1 in 7918 ms. Their write acknowledgements occurred
at 03:34:05.615744 UTC and 03:35:34.802824 UTC on 23 October. The old browser
result appeared below all 50 case cards, and the module did not receive live
poll data. These logs establish API observations, not independent physical
verification by this agent.

The initial supplier-catalogue request failed while the Ethernet NIC was absent.
Later healthy polling did not reload the browser catalogue, leaving Commands
empty. Initial failures now retry after communication returns. Loading,
unavailable, valid-empty and filtered-empty states have messages and actions.
A valid empty catalogue stops retries.

The later log contains Tank 05 Door Open TIMEOUT after 5001 ms, with opened
feedback still 0. At 04:23:01.961840 UTC, a candidate request failed with
“This command/feedback mapping requires supplier confirmation.” The running
backend still used the older opt-in behavior. The backend was then restarted
with the tested changes. Read-only checks confirmed REAL mode, fresh Remote
communication, 362 tags, 50 cases with 30-second windows, and write mode off.
The old timeout and rejection remain in the audit log.

### Implemented behavior

- Feedback tests place the active result above the case list. Live values,
  expected values, freshness, command readback and the recorded backend result
  remain separate. Live matching values alone cannot award PASS or OBSERVED.
- The compact **After 1: Hold 1 | Manual 0** control captures an explicit choice
  in the single send confirmation. Doors retain Manual 0. Hold becomes a local
  Keep record only after accepted 1 and a strictly later fresh command readback
  of 1. No extra write enforces that state.
- **Send 0** remains on the Feedback tests page. The single confirmation names
  the same command and its current value. It permits an explicit clear of a
  pending command even when its bit already returned to 0. Accepted 0 and a
  strictly later verified 0 remain separate from the original test result.
- Feedback tests share existing checklist records. Pending and held commands
  survive case changes and reloads. An unfinished request restores as unknown,
  without replay. A clear request returns a held command to pending until
  verified 0. Unknown or blocked clears cannot silently become Keep decisions.
- The 36 manual-derived pairs retain `requires_confirmation=true`. Explicit
  per-run opt-in permits **Mapping under test**. A fresh matching transition
  returns OBSERVED rather than a confirmed-mapping PASS. API requests without
  opt-in still block those pairs. Configuration is not promoted automatically.
- All 50 bundled feedback cases use `timeout_ms=30000`. The observation window
  does not stop equipment, clear a command or establish a hold duration.
- Only Tank 01 at M300/M301 has the operator-confirmed movement/manual-clear
  procedure. Other hold interpretations remain qualified in the rule details.
- The sidebar retains three separate read views: Tank monitor, Signal browser
  and Alarm signals. Tank monitor uses horizontal tabs with keyboard controls,
  visible A/B identities and R/W labels. All three mark missing, stale or
  disconnected observations. Alarm bits remain raw values without severity.
- Signal browser shows every matching card in manual group order. The old
  120-card cutoff is removed. Full descriptions wrap and filters remain usable.
- Each active or pending command row has its own Send 0 control. The latest
  clear is labelled separately from current bits. An unknown-origin clear uses
  a zero-only cleanup record. It never invents an accepted Send 1 or a full
  command cycle. Manual hints do not replace the selected mode.
- Malformed replies after dispatch remain uncertain. Only an explicit
  `write_dispatched=false` can release a rejected attempt. Clear verification
  requires the captured address and the current request's accepted receipt.
  An unknown retry cannot reuse an earlier acknowledgement.
- Setpoints & batch groups 39 numeric setpoints before 102 Bool commands. All
  141 writable tags remain accessible, and valid selections survive refresh.
- UI actions and results use short text. Longer rule evidence and technical
  detail remain accessible through disclosure. Supplier tag text stays intact.
  This is an STE-style clarity pass, not an official dictionary certification.

### Verification and limits

The final aggregate suite passed **354 tests in 271.26 seconds**, with no skips
or failures, using:

```sh
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

This includes the final inventory clears, manual hints, numeric/Bool selector
groups, horizontal tank tabs, all read views, malformed post-dispatch replies,
clear-address evidence, interrupted/retried clear histories and both Manual 0/1
receipt addresses. Earlier aggregate runs passed 313 tests before the final UI
refinements and 346 tests before the final receipt-address check.

`git diff --check` passed. A scan of all 33 changed/new files found no configured
API key. The private `.env` stays ignored with mode 0600. Nothing was staged
at the end of that verification run.

The scoped card palette and sources are in
[architecture.md](architecture.md#feedback-visibility-catalogue-recovery-and-card-design).
Checked text pairs range from 5.00:1 to 9.45:1. The blue focus color exceeds 3:1
against white. Fake-API desktop and 390-pixel screenshots confirmed complete
signal access and visible manual-clear and confirmation actions. The compact
mode control was moved above long confirmation details.

Browser tests use isolated loopback fake APIs only. No agent live PLC write,
automatic reset or physical test was performed for this update. Live checks were
GET requests. Physical behavior and supplier mapping semantics still require
field verification. No changes were staged, committed or pushed during that
verification run.


### Push preparation — 23 October 2026

GitHub `origin/main` was fetched again and still points to `76d0d0b`. The
feature branch is `feat/line-test-workflows`. The 33 intended source, test,
configuration and documentation files form the staging manifest. Final staging
checks and the suggested commit/PR text are recorded in the local
`plc-signal-test-ui-push-prep-2026-10-23.txt` artifact. The final review found an address-provenance gap in Manual 0/1: a
receipt for a remapped tag could be accepted against the browser's old address.
Both values now require a matching receipt address before acceptance. Missing
or contradictory identity remains unknown and pending. The eight new fake-API
regressions passed in 12.56 seconds. The aggregate suite then passed all
354 tests in 271.26 seconds, with no failures or skips.

The proposed files were checked for the configured API key, common GitHub token
formats and private keys. No match was found. Private settings, Wi-Fi credentials,
runtime logs, ZIP files and local network notes are excluded.

At the staging checkpoint, no commit or push had been made. GitHub CLI login
was verified as `neptulyx`, with push access to the repository. Git commit author
name/email was still unset; that identity is separate from GitHub authentication.
The live PLC was not written to for this review.


## Human results and feedback test controls

The operator reported that Tank 01 Heater and US were incorrectly shown as
complete. Supplier logs show TIMEOUT at 14:43:54 and 14:47:17 Hong Kong time,
with expected status 1 and actual 0. Their later clear requests were accepted.
The old checklist counted accepted 1, accepted 0 and a later readback 0 as
completion, even when feedback timed out. This was command evidence, not a
physical result.

Human completion is now separate on all write-test views. The Feedback result
dropdown saves explicit Not checked, Pass and Fail choices immediately. API
results and timers remain unchanged. Previous human choices and timestamps
remain in the browser audit. Legacy API cycles stay unchecked. A correction
cannot resume interrupted automatic Hold or release pending clears.

The default is now 15 seconds for all 50 cases. Per-run overrides accept whole
seconds from 1 through 300 and appear in the write confirmation and logs. The
request deadline includes observation plus transport overhead. Configuration
is unchanged by an override. Horizontal tank tabs filter cases while the active
result and pending clear inventory remain visible. Feedback mode initially
follows qualified manual Hold hints, with Manual 0 for doors or absent hints.

Focused backend checks passed 119 tests against the 15-second default. All
checks use mock or isolated loopback APIs. No agent live PLC write or physical
test is part of this update. Human choices remain browser-local; exported
checklist and value-feedback records retain them.

### Final verification for human results and feedback controls

The aggregate suite passed **423 tests in 350.56 seconds**, with no failures or
skips, using:

```sh
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
```

This includes explicit/reversible human choices, legacy API-only records,
exports, no-write result changes, interrupted Hold, preserved pending locks,
15-second defaults, valid/invalid overrides, captured deadlines, horizontal tank
tabs, selection/focus recovery, mode suggestions and manual overrides.

Fake-API previews at 1440 and 500 CSS pixels showed human Fail separately from
API TIMEOUT, with a visible result dropdown and no horizontal clipping. Preview
metrics and screenshots are in the local `ux-review-2026-10-23` artifact folder.
No preview contacted the line API.

`git diff --check` passed. A scan of all 24 changed/new files found no configured
API key, private-key block or GitHub token pattern. The private `.env` remains
ignored. This follow-up remains local and uncommitted on
`feat/line-test-workflows`; the previously pushed commit is `f9d20c8`.

The local backend was gracefully restarted to load the new defaults and timeout
handling. Read-only checks confirmed REAL mode, connected/fresh Remote data,
362 readable tags, and 50 cases with a 15000 ms default. Browser reload starts
in read-only mode and preserves existing browser history. Human decisions
remain separate from API observations and supplier mapping confirmation.

One final status sample was stale. The next three were fresh, with corrected
ages of 2693, 2283 and 1866 ms against the existing 3000 ms limit. The temporary
44-second timestamp correction and freshness guards were left unchanged. A stale
observation still blocks writes; human-result editing remains a separate local action.


## Parallel feedback observations

The operator requested that a feedback wait no longer block independent commands.
The backend now releases the command lock during observation. Its active-run
registry protects the same command/address, opposing door actuator and shared
feedback resource. Actual dispatch validation remains serialized. Explicit
same-command 0 interrupts only its observer at dispatch. A rejected preflight
clear leaves observation running. Interrupted reads cannot produce late PASS
or a configured reset. Each observer checks its own snapshot, including
freshness, Remote mode and captured command/feedback addresses.

The browser stores each session run separately. Test run selects its result,
mode, captured timeout, request elapsed time and human decision. Out-of-order
responses cannot change the selected run or another record. Pending and unknown
commands remain visible and protect conflicting requests. They do not lock
unrelated commands. Backend `run_id` is retained as `backend_run_id` in the
checklist audit/export. No jobs API, automatic retries or command queue was added.

### Regression verification

The current collection contains **471 tests**. All passed in two complementary
groups with the implementation and shared fixtures frozen:

- **112 passed in 205.90 seconds**: checklist, command modes and feedback bridge.
- **359 passed in 294.22 seconds**: every other collected test.

Neither group had failures or skips. Commands:

```sh
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_frontend_safety.py tests/test_command_modes.py tests/test_feedback_checklist_bridge.py
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --ignore=tests/test_frontend_safety.py --ignore=tests/test_command_modes.py --ignore=tests/test_feedback_checklist_bridge.py
```

The first interrupted aggregate run exposed an obsolete global-block assertion
and a nondeterministic zero-readback assertion. The former now checks that the
independent command stays available. The latter freezes the supplier stamp,
proves the conflict remains pending, then explicitly permits a later verified
0. No implementation change was needed for those two failures.

The backend group includes 34 new concurrency regressions. Four new browser
tests cover independent results/timers, reverse reply order, human-result
association, conflicts and early manual clear. The shared bridge adds ten
concurrency/clear/reload cases. Existing freshness, receipt, mode, mapping and
manual-completion safeguards remain covered.

Fake-API previews at 1440×1014 and 500×914 CSS pixels show one finished and one
waiting run, an accessible run selector and a frozen selected-run timer. There
is no horizontal clipping. Images and metrics are in the local
`ux-review-2026-10-23/parallel-*` artifacts. They sent no live PLC commands.

`git diff --check` passed. The 28 changed/new files passed the configured-secret,
private-key and GitHub-token scan. All follow-up changes remain local and
uncommitted on `feat/line-test-workflows`. The prior pushed commit is `f9d20c8`.

### Running program

The local backend was gracefully restarted after validation. Read-only checks
confirmed HTTP 200, REAL mode, connected/fresh Remote data, 362 readable tags
and no failed tags. All 50 case defaults remain 15000 ms. The running CSV
audit includes `run_id` and `timeout_ms`, confirming the updated backend loaded.
Reload the browser to load the new controls. Reload starts in read-only mode.
No agent live parallel test or physical line operation was performed. Software
resource guards do not establish physical independence between line commands.


## Supplier audit, operator verification and Manual-style write workspace

### Source evidence and field failures

The supplier Swagger page at `http://192.168.1.12:8000/docs` returned HTTP 200.
Its OpenAPI describes tag list/read and single/batch writes. Single writes use
`{tag_name, value}` with numeric engineering values. Bool values are 0 or 1.
The supplied 29 September manual and live catalogue agree for all 50 configured
command/status names, addresses, types and W/R permissions. Those reviewed
sources contain no explicit pair transition/polarity/deadline/hold-reset truth
table. The 14 Local pairs and 36 inferred pairs are application classifications,
not supplier sign-off. No case flags or expected values were promoted or guessed.

The operator reports all door pairs tested, with every marked Pass physically
checked by eye. Failed cases did not operate. This is operator evidence. The
implementation preserves those decisions and labels them separately from source
provenance and API outcomes. It does not mark all doors Pass automatically.

The initial audit of the recent full run found 43 attempts across 40 distinct
cases. Latest per-case outcomes were 28 API matches/observations and 12 timeouts.
The timed-out writes were acknowledged, but all sampled expected feedback
values remained 0. One earlier Tank14 Heater attempt also returned supplier HTTP
502; its later retry was acknowledged and timed out. Neither UI labels nor a
correct tag table establishes the PLC's operating conditions.

With explicit user authorization for non-door writes, the agent then tested:

- Tank01 FilterRemote, HeaterRemote and USRemote.
- Tank03 and Tank05 FillWaterOn.
- Tank11 SprayRemote and FillWaterOn.
- Tank14 FilterRemote and HeaterRemote.

Each trial started with request/status 0, used a 15-second observation, and
received written=true. All nine showed API command readback 1 without feedback
1. Every trial timed out with Remote 1 and Local 0 in the sampled data. Each
request was explicitly restored to its original 0. A final fresh snapshot was
later than every clear acknowledgement and showed all nine commands at 0.
No door tag, RemoteStart sequence, Auto setting or interlock was changed.

The cause of missing operation is not established by the reviewed API/manual.
The provided material has no PLC project, actual API source, TagsMap workbook,
or written permissive/operating sequence. RemoteStart is metadata only. The
three Air/Fill read-address aliases also need engineering review. No address,
polarity, trigger sequence or timing guarantee was invented to make a case pass.

Local artifacts include:

- `feedback-full-run-audit-2026-10-23.json/csv`
- `feedback-mapping-provenance-2026-10-23.json/csv`
- `feedback-card-coverage-2026-10-23.json`
- `authorized-non-door-write-summary-2026-10-23.json/csv` and per-trial reports
- `supplier-command-diagnostics-handoff-2026-10-23.txt` (prepared, not sent)

These files are in the local api_test artifacts folder, outside the Git project.
Operator marks were not changed by the API probes. Legacy video was not reviewed
frame by frame, and the physical cause remains unproven.

### UI and HCI changes

Feedback now follows Manual 0/1: a compact left picker and right workspace.
Both use a native tank selector, search and human-result filters. Saved marks
show labelled Pass/Fail/Not checked indicators with color and icons. Selection
is review-only. Run retains one explicit command confirmation. Independent
observations, request timers, run selection and clear ownership are preserved.

Command bits live in one shared topbar on the three write routes. Recorded
intent is separate from live readback. A missing or remapped address remains
visible as Needs review. Its old request cannot clear a different current
address. Enable/Disable write mode is compact beside Refresh now, with visible
OFF/ON status. Healthy read-only data says MONITORING READY; authorized healthy
Remote data says READY TO TEST. Neither label establishes machine interlocks.

Manual and Feedback use page scrolling. Explicit keyboard selection reaches
the workspace, and Choose another returns to search. Polling never moves focus.
Current command and feedback are labelled as separate readbacks rather than an
apparent transition. Manual live values are distinct from recorded API evidence.
The advanced read-comparison table retains bounded, keyboard-accessible scrolling.

All three pages use the same human-result vocabulary. Setpoints/batch now
autosaves unchecked/pass/fail, preserving valid legacy human completion marks
and prior choices in its audit. API outcomes, snapshots and timing stay separate.
Bool engineering values use a labelled 0/1 selector; numeric types retain input.
Changed selection/address/type/permission/API/mode blocks a stale single-write
confirmation before any observation or POST.

The supplier batch schema returns `results` and `count`. The app now validates
that documented shape, with complete matching items, explicit written=true and
a valid count. Legacy `writes` is used only when results is absent. Malformed or
partial replies remain uncertain. This bug did not cause the single-tag timeouts.
Future test results/logs include command_readback, Remote and Local from the
same feedback poll. No additional PLC request or inferred historical value is added.

### Final software verification

The current collection contains **556 software tests**. All unique checks were
validated against the final implementation:

- Group A: **162 passed in 314.49 seconds**, no failures or skips.
- Complementary Group B: **390 passed**, with four tooltip-copy assertions
  expecting the old word confirmation. The group took 315.78 seconds.
- Those four assertions now check the accurate inferred/not-specified wording.
  Their focused rerun passed **4 tests in 8.77 seconds**. No implementation or
  fixture changed after the two main groups.

The groups are complementary and the four corrected cases complete the 556-test
collection. Their commands were:

```sh
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_frontend_safety.py tests/test_command_modes.py tests/test_feedback_checklist_bridge.py tests/test_inventory_clear_ui.py tests/test_manual_single_scroll.py tests/test_manual_result_indicators.py tests/test_feedback_workbench.py tests/test_feedback_card_results.py
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider --ignore=tests/test_frontend_safety.py --ignore=tests/test_command_modes.py --ignore=tests/test_feedback_checklist_bridge.py --ignore=tests/test_inventory_clear_ui.py --ignore=tests/test_manual_single_scroll.py --ignore=tests/test_manual_result_indicators.py --ignore=tests/test_feedback_workbench.py --ignore=tests/test_feedback_card_results.py
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_command_mode_hints.py -k feedback_initially_selects
```

Software regressions use isolated mock/loopback APIs. They are distinct from
the nine authorized live trials, whose API outcomes remained TIMEOUT. HCI
previews checked desktop/narrow layouts, keyboard access, role/state labels,
physical-result separation and preservation of simulated legacy Pass marks.
This is a scoped HCI review, not whole-application accessibility certification.

All follow-up changes remain local and uncommitted on feat/line-test-workflows.
The previously pushed commit is f9d20c8. No credentials or raw runtime logs are
intended for Git. The original supplier source documents remain unchanged.

### Runtime reload and final read-only check

The local real-mode app was gracefully restarted after verification. GET-only
checks returned HTTP 200 for the UI, status, signals, feedback cases and CSV
export. The supplier was connected in Remote mode with fresh data, 362 tags OK
and 0 failed. The 50 cases retained 15000 ms defaults. The CSV header included
command_readback, Remote, Local, run_id and timeout_ms. All nine diagnostic
request bits still read 0. No command was written during this reload/check.
Write mode remained OFF. The existing 44-second temporary clock adjustment and
3000 ms freshness guard were unchanged. Reloading the browser loads the updated
UI; the restart requires renewed write authorization before any later write.

Final diff checks passed across 37 changed/new files, with 0 staged files. A
scan using the configured private API key plus private-key/GitHub-token patterns
found no matches in the changed files. No environment file, runtime log or ZIP
is included in the source changes. A read-only runtime summary is saved locally
as api_test/artifacts/final-runtime-check-2026-10-23.json.

## Broader console HCI pass

The follow-up [HCI review](hci-review-2026-10-23.md) covers all nine pages and
their read/write workflows. It fixes hidden global mode failures, unexplained
disabled Feedback Run actions, catalog keyboard focus loss during polling,
missing accessible names, route/skip navigation, low contrast and repeated
unchanged live status text. Catalog warnings use an accessible disclosure that
retains every warning and its expanded state. Source labels match across pages.
The requested neutral Feedback result-card borders remain unchanged.

The affected suite passed **126 tests in 213.62 seconds**, including 22 new HCI
checks, using isolated mock/loopback APIs. Nine-route previews at 1440, 1024 and
500 CSS pixels found no page-width overflow or unnamed visible form controls.
Contrast measurements, screenshots, limits and primary guidance are linked in
the review. JavaScript module syntax and diff checks passed. No line commands,
network changes, saved operator marks or supplier mapping changes were made.
This is not formal accessibility certification. Actual screen-reader listening,
other browser engines, sub-500 CSS-pixel reflow and operator-distance testing
remain outside the verified scope. All changes remain local and uncommitted.

## Failed-pair source recheck against the live supplier API

A fresh read-only check returned HTTP 200 from the supplier /docs page and read
its /openapi.json and /api/v1/tags/list. All 12 historical TIMEOUT cases in the
full-run audit still match the current config and supplied tag table for symbol,
address, Bool type and W/R permission. An independent reread of the extracted
manual/catalog found no mismatch between their tank/equipment labels and the
app labels, or an open/closed swap. This check did not establish physical tank
identity. The later Tank12/Tank13 correction below demonstrates that limit. The read endpoint returns general tag values. The write receipt written=true
acknowledges the write; it does not confirm physical operation.

| Command | Address | Feedback | Address | Metadata |
| --- | --- | --- | --- | --- |
| Tank01_FilterRemote | M320 | Tank01_FilterStatus | D1002.1 | Matches |
| Tank01_HeaterRemote | M321 | Tank01_HeaterStatus | D1002.2 | Matches |
| Tank01_USRemote | M322 | Tank01_USStatus | Y4 | Matches |
| Tank03_FillWaterOn | L110 | Tank03_FillWaterStatus | D1012.8 | Matches |
| Tank05_FillWaterOn | L120 | Tank05_FillWaterStatus | D1022.8 | Matches |
| Tank07_DoorOpenRemote | M306 | Tank07_DoorOpened | D1028.4 | Matches |
| Tank10_DoorOpenRemote | M308 | Tank10_DoorOpened | D1102.4 | Matches |
| Tank11_SprayRemote | M371 | Tank11_SprayStatus | D1112.1 | Matches |
| Tank11_FillWaterOn | L150 | Tank11_FillWaterStatus | D1112.4 | Matches |
| Tank14_DoorOpenRemote | M312 | Tank14_DoorOpened | D1126.4 | Matches |
| Tank14_FilterRemote | M391 | Tank14_FilterStatus | D1128.1 | Matches |
| Tank14_HeaterRemote | M392 | Tank14_HeaterStatus | D1128.2 | Matches |

The reviewed documents list the command and status tags separately. They do
not explicitly establish command 1 → feedback 1, timing, prerequisite modes or
hold/reset behavior. Pair behavior remains unconfirmed by supplier documentation.
Tank03 FillWaterStatus D1012.8 also names Tank04 AirAgitationStatus; Tank05
FillWaterStatus D1022.8 also names Tank06 AirAgitationStatus. These source-level
aliases require supplier clarification. No replacement address was guessed.

The 12-case list is the historical API TIMEOUT set, not a new physical failure
ledger. Later operator Pass marks remain separate evidence. This recheck sent
no writes and changed no code, mappings or operator marks. Fresh schema, catalog
and pair comparison JSON are saved locally under api_test/artifacts with the
failed-pair-recheck prefix.

## Operator-confirmed Tank12/Tank13 physical door naming correction

The operator explicitly confirmed that Tank12_DoorOpenRemote/CloseRemote operate
physical Tank 13, and Tank12_DoorOpened/Closed follow its actual position. The
supplier manual PDF page 17 and current API both retain Tank12 names; there are
no Tank13_Door tags. All 14 door pairs match the written sources at the metadata
level. That agreement does not establish physical identity.

The four-tag mapping, operator evidence, affected existing test IDs and limits
are recorded in the [signal test plan](signal-test-plan.md#physical-tank-13-door-uses-tank12-api-names).
The supplier handoff now includes this naming discrepancy. No API names, write
routing, feedback addresses, UI grouping or operator marks changed. No commands
were sent. A source correction/display alias is separate follow-up work.

## Supervised outside-Feedback test: Tank07 air agitation

The operator approved one test: Tank07_AirAgitationOn (L135) =1 for up to
15 seconds, observing Tank07_AirAgitationStatus (D1030.F), then command 0.
Both baseline values were0 in fresh REAL/Remote data. The supplier acknowledged1.
Later fresh data newer than the receipt showed command1/status1. Command 0 was
then acknowledged; a later fresh snapshot showed command 0/status0. The operator
explicitly confirmed physical start and stop and selected Pass.

This is operator-observed evidence for this device/address, not supplier source
sign-off. No Feedback test definition was added and no other actuator was written.
The script's own write token was disabled afterward. Evidence, timestamps and
raw sampled values are saved outside Git as
api_test/artifacts/supervised-tank07-air-20261023T110029.json. The 91-item run list
now records this result. Step2 remains pending equipment-readiness confirmation.

## Supervised outside-Feedback test: Tank07 cooling circulation

The operator approved Tank07_CoolerOn (L131) =1 for up to15 seconds while
observing Tank07_CoolerStatus (D1030.B), followed by0. Fresh baseline command/status
were0. Both writes were acknowledged. Later fresh readbacks newer than each
receipt showed command/status1 and then command/status0. The operator selected
Pass and confirmed physical start/stop. This evidence applies to this device
and address. No other actuator was written. The script's own token was disabled.
Evidence is api_test/artifacts/supervised-tank07-cooler-20261023T110210.json.
The outside-Feedback run list now has two physically confirmed Pass results.

## Additional supervised outside-Feedback test results

These tests use the approved 1/up-to-15-seconds/0 sequence. Human Pass is recorded
only from explicit operator confirmation. Fresh reads newer than each receipt
verify the API transitions independently.

| Command | Read status | API result | Human result | Local evidence |
| --- | --- | --- | --- | --- |
| Tank08_AirAgitationOn | Tank08_AirAgitationStatus | command/status0→1→0; restored0 | Pass: start/stop confirmed | supervised-tank08-air-20261023T110329.json |


## Authorized automatic remainder of the seven status checks

After explicitly confirming three physical Pass results, the operator authorized
automatic continuation when API feedback is correct. Only the remaining four
air-agitation items in the first seven-device block were run: Tanks09,12,15,16.
Each test captured command/status0, wrote1, observed a later fresh post-receipt
command/status1, wrote0, and verified later fresh command/status0. The queue ran
one device at a time and would stop on a mismatch or failed clear. Each script's
own write token was disabled after cleanup. No unrelated tag or door was written.

All seven status-check devices therefore have API0→1→0 evidence. Tank07 air,
Tank07 cooler and Tank08 air also have explicit operator physical Pass. The four
automatic cases remain human Not checked. No physical Pass was inferred from
an API match or copied into browser-local results. The Tank12 air test uses its
source API identity; the separate door naming correction is not generalized.

A final fresh snapshot newer than all seven clear acknowledgements showed all
seven command and status bits0. The final evidence is saved outside Git as
api_test/artifacts/supervised-first-seven-summary-2026-10-23.json. The complete
91-row CSV/JSON run list holds per-device results and raw evidence filenames.
Seven devices consumed14 acknowledged writes, including restoration. MainInlet,
shared-address items, Auto bits, numeric values and RemoteStart were not changed.

## Supervised session stopped: water turned off

The operator asked to mark the completed tests checked, then explicitly stopped
testing because line water was turned off. All seven completed device tests are
marked API checked in the run list. The three explicit physical Pass results
remain separate; the four automatic cases have no recorded physical observation.
No browser-local human marks were inferred from API readbacks.

The proposed23 Auto-mode tests were never authorized and no Auto bit was written.
The earlier pending readiness question no longer authorizes any continuation.
No unattended job exists. Resume requires a new instruction and current equipment
readiness. Numeric values, RemoteStart, MainInlet, shared-address items and doors
were not written in this supervised outside-Feedback session.

A final GET-only check recorded all seven tested request/status bits0. Details
and freshness are saved as api_test/artifacts/supervised-line-stop-2026-10-23.json.
Testing remains stopped. The local read-only monitoring app is left running.

## Current human marks reset; physical evidence retained

After stopping the session, the operator explicitly requested that the three
physical confirmations stay in history while their current human marks return
to Not checked. This was applied to Tank07 air agitation, Tank07 cooling
circulation and Tank08 air agitation. Their original Pass values, confirmation
timestamps and exact physical observations remain in each report's human result
history and a separate human-pass-reset audit artifact. Earlier verification
sections describe the original results at the time, rather than current marks.

All seven completed items retain API checked. Their current human results are
now all Not checked, with zero current human Pass marks. The 91-item run list
and CSV reflect this correction. The current results are also saved outside Git
as api_test/artifacts/supervised-first-seven-current-results-2026-10-23.json.
Testing remains stopped and requires a new instruction to resume. No live API
requests or writes were sent to make this bookkeeping change. Browser-local
UI marks were not changed; the correction applies to the saved supervised run
records, which were the records created during these tests.

## Feature-branch push preparation

The operator selected the existing feat/line-test-workflows branch and a pull
request into main. A fresh origin fetch still shows main at 76d0d0b and feature
HEAD at f9d20c8, one commit ahead. No PR existed for the earlier feature push.
The reviewed source/tests/docs are prepared for a feature-branch commit and a
pull request into main. After validation, the operator explicitly authorized
publishing the update. Merge into main remains a separate review step.

Review found and fixed two concrete gaps:

- Active feedback observers now reject command/feedback data-type or multiplier
  changes at the same address. Four regressions cover both signals and both
  metadata fields, including reservation cleanup and dispatch provenance.
- Single, Batch and Manual 0/1 confirmations now retain primitive API/mode,
  symbol, address, type, permission and multiplier identity. Changed identity
  blocks before observations or POST. Sixteen browser cases reproduce the
  original Batch remap failure, block changed identities, and allow one write
  after an unchanged metadata refresh.

Stale architecture/layout text and run-plan current-state text were corrected.
Earlier dated physical results remain in history; the latest current human
marks are Not checked while all seven completed field items remain API checked.
Line testing remains stopped. No live API calls or writes were made for this
Git preparation. The raw Tank12 door names still refer to physical Tank13 as
operator-confirmed; this supplier naming discrepancy is documented, not renamed.

### Final software checks

The current collection has **598 tests**. Validation uses the full run plus
final targeted reruns, rather than claiming one clean monolithic run:

- Full run: **577 passed, 1 failed in 679.98 seconds**. The one failing assertion
  treated aria-describedby as a single element ID. The UI correctly references
  both its mapping note and blocked-run reason. The test now checks the ID list.
- Final verifier group after that test-only correction: **30 passed in 60.48 seconds**.
- Final backend safety/parallel subset after the metadata fix: **267 passed in 14.39 seconds**, including four new regressions.
- Final dedicated confirmation-identity suite: **16 passed in 40.35 seconds**.
- Existing single/manual/batch/Bool/clear/receipt checks after that frontend fix:
  **33 passed in 72.40 seconds**.

The full run collected 578 cases before the last 20 new review regressions were
added. Its corrected assertion is covered in the 30-case rerun. The final 267
backend, 16 new frontend and 33 legacy frontend reruns cover the product changes
made during review. All 598 unique checks therefore have passing validation.
No implementation changed after the final affected checks.

All test commands set PLC_MOCK_MODE=true, remove inherited PYTHONPATH and disable
bytecode/cache writes. Test APIs are mock or isolated loopback instances. The
key commands were:

```sh
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_app_safety.py tests/test_plc_client.py tests/test_signal_service.py tests/test_test_runner.py tests/test_validation.py tests/test_parallel_feedback_backend.py
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_write_confirmation_identity.py
env -u PYTHONPATH PLC_MOCK_MODE=true PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider tests/test_verifier_ui.py
```

Final staging checks cover exact configured-secret scanning, private-key and
GitHub-token patterns, source syntax and git diff formatting. Environment files,
raw logs, local evidence/ZIP/PDF files and temporary test scripts stay outside
the staged source. Runtime field artifacts remain local; committed verification
summaries identify their scope and limits. The backend must be restarted before
using newly edited server guards. No additional live equipment tests were run.

## PDF and live Swagger/catalog alignment

The user requested every PDF/API signal discrepancy and software alignment,
then authorized use of local history and publication of all findings. The first
comparison used the retained 23 October schema/catalog captures. A later live
GET-only recheck at 20:05:19 Hong Kong time on 23 October 2026 confirmed both are
semantically identical to the current server. All four GET endpoints returned
HTTP 200; /read contained all 362 signals, with 362 OK and 0 failed. No production
POST, write-mode enable or actuator test occurred. The line adapter can be
disconnected after that check; publication uses ordinary Internet access.

The actual PDF table was independently extracted and all 362 rows matched the
PDF-derived fixture. Against the saved/live API, names, addresses, types, W/R
permissions and multipliers all agree. The complete report lists 39 numeric
signals whose PDF limits are omitted from the API, eight description spacing
differences, incorrect PDF/example references, the four operator-confirmed
Tank12-door/physical-Tank13 tags and all five shared-address groups. An omitted
API bound does not establish unlimited operating range. Shared source errors
were not mislabeled as PDF-versus-Swagger differences or guessed remappings.

Published notes and primary evidence:

- [Complete audit](swagger-alignment-2026-10-23.md).
- [All 47 differing signal definitions](swagger-signal-differences-2026-10-23.csv).
- [Provenance/hashes and live confirmation](source/supplier-api-capture-2026-10-23.json).
- Saved OpenAPI schema and full 362-tag response under docs/source.

Implementation changes are limited to Swagger-shaped mock batch results/count,
an explicit HTTP 422 request-validation message and truthful Not published
numeric-limit labels. Production already obtains tag definitions from the live
API. No tag routing/name/address, permission, finite/type/supplied-limit guard,
authorization or calibration setting was weakened or replaced by the PDF.
The retained source snapshots are evidence, not an offline runtime fallback.

Affected offline validation: 192 passed in 37.66s; contract/runtime-catalog and
parallel-backend follow-up: 39 passed in 2.71s; final contract/client/UI checks
after fresh provenance: 20 passed in 10.08s. These groups overlap. Syntax, diff
and credential checks passed. The complete earlier suite was not repeated for
these small targeted changes. Raw /read operating values remain outside Git;
source evidence contains only schema/catalog and capture metadata, without
API keys or authentication tokens. Line write testing remains stopped.
