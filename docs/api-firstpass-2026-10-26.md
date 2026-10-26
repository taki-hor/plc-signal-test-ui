# API first pass — 26 October 2026

The operator approved non-door binary On commands and 23 distinct Auto bits for
individual 0 → 1 → 0 cycles. Each API pass requires an accepted write, later fresh
command readback, related status where mapped, and verified restoration. An HTTP
success alone does not qualify. API evidence does not prove physical operation.

## Results and limits

The prepared queue contains 56 commands: 33 On commands with independent status
mappings, and 23 Auto bits with command readback only. The automatic run completed
49 cycles: **42 API pass and 7 API fail**. All 49 completed cycles restored the
command and required status to 0. The seven failures had fresh command 1 readback,
but their mapped status did not reach 1 within 15 seconds:

- Tank01_HeaterRemote → Tank01_HeaterStatus
- Tank01_USRemote → Tank01_USStatus
- Tank11_FillWaterOn → Tank11_FillWaterStatus
- Tank11_SprayRemote → Tank11_SprayStatus
- Tank14_FilterRemote → Tank14_FilterStatus
- Tank14_HeaterRemote → Tank14_HeaterStatus
- Tank07_FillWaterOn → Tank07_FillWaterStatus

Tank01_FilterRemote passed during this run. Later operator retests produced newer
failures, which must remain visible rather than being hidden by the earlier pass.
All 23 distinct Auto bits passed their own command readback and restoration test;
this does not establish the behavior of associated equipment in Auto mode.

The queue stopped at item 50, Tank13_HeaterRemote, after a communication error
before a write receipt was obtained. The report contains no write-1 request or
receipt. No cycle is claimed for this item. Seven items remain without a completed
cycle from this queue: Tank13_HeaterRemote, Tank14_FillWaterOn, Tank14_SwingRemote,
Tank15_FillWaterOn, Tank16_FillWaterOn, Tank16_FilterRemote and Tank16_HeaterRemote.
The stop marker remains in place; this run has not automatically restarted.

An independent fresh read at 05:18:23 UTC showed Tank01_DoorOpenRemote,
Tank01_DoorCloseRemote and Tank01_FilterRemote all at 0, Tank01_DoorClosed at 1,
and Tank13_HeaterRemote/HeaterStatus at 0. Later user-operated door tests are
separate from this non-door automatic run.

The retained API cache subsequently contained 50 API pass and 13 API fail results,
with no pending observations; it includes earlier tests and later operator writes,
so these totals are not the result count of the 49-cycle queue. Signals without
valid evidence remain Unchecked.

Door writes, numeric setpoints, RemoteStart, MainInlet and ambiguous shared-address
cases were outside this automatic pass. No prerequisite or physical diagnosis is
inferred from a missing status transition. See
[the prerequisite review](api-prerequisites-2026-10-26.md).

## Source and timing checks

The live OpenAPI definition and 362-tag catalogue matched the saved 23 October
supplier baseline. This comparison establishes contract alignment, not PLC
behavior. The line API still omits the timezone from its timestamps; Hong Kong
time is configured. This testing PC's ignored local configuration temporarily
uses a +46-second correction, measured from fresh reads. The 3-second freshness
guard remains enabled. The supplier clock was not changed. Re-measure this local
correction before another hardware session.

Raw plan, per-command evidence and result summaries remain in the testing PC's
`/home/nep/Documents/api_test/artifacts/` directory. Runtime API evidence and the
append-only event log remain in ignored `logs/` files; credentials are not part
of the repository or this report.

## Saved result behavior

The visible API choices are **API pass / API fail / Unchecked**. The legacy
transport/export enum `checked` means API pass and remains compatible with older
records. Automatic passes retain fresh 1/status/0 evidence. A saved human Pass
can backfill API pass with the explicit source **Human-confirmed test**; a newer
automated failure takes precedence. Changed command or feedback metadata
invalidates old API evidence.

New attempt creates an unjudged attempt. It does not reset the saved signal's
human judgment or replace the history. Polling and temporary result-fetch failures
also do not reset judgments. A pending API retest retains the previous settled
result until new conclusive evidence is available; the detail identifies the
pending attempt. New actual failures remain visible.

Each write page has compact saved API and human result controls. These record an
explicit, timestamped browser decision with the previous value and send no PLC
command. **Use API evidence** releases a manual API override. A manual override
is labelled as manual; any existing automated failure remains in its detail.
Human choices remain **Not checked / Pass / Fail**. Attempt-specific results and
signal-wide saved results are distinct. JSON exports include the manual decision
history. Browser decisions are local to this browser, supplier target, operating
mode and signal metadata; they are not automatically synchronized to other PCs.

## Verification of this update

A combined backend/transport/validation/runner suite passed **322 tests** using
mocked or in-memory suppliers. Separate Firefox regressions cover API labels and
filters, saved human judgments, explicit corrections, context/metadata isolation,
exports and history preservation. The final direct queue has 28 fake-only tests,
including cancellation, terminal restoration, unknown acknowledgments and audit
storage failure during cleanup.

Read-only application checks after restart recovered all 63 stored API results
(50 pass / 13 fail), with no pending observation and fresh Remote data. No active
binary command was present before the restart. The new direct human queue was
previewed offline only; it has not been executed against the production line.

See [human queue instructions](human-line-test.md) for the P / I / N workflow,
result files, scope and outstanding physical checks.
