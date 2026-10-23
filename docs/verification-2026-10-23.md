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
