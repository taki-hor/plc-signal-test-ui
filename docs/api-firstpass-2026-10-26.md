# API first pass — 26 October 2026

This note records the first automatic pass and the application state at that time.
Later results appear in [the second-run review](swagger-second-run-2026-10-26.txt).

The operator approved individual 0 → 1 → 0 cycles for non-door On commands and 23 distinct Auto bits.
Each API pass requires an accepted write and later fresh command readback.
It also requires mapped status feedback and verified restoration where applicable.
HTTP success alone does not qualify. API evidence does not prove physical operation.

## Results and limits

The prepared queue contained 56 commands: 33 On commands with independent status mappings and 23 Auto bits.
Auto tests checked command readback only.
The automatic run completed 49 cycles: **42 API pass and 7 API fail**.
All 49 completed cycles restored the command and required status to 0.
The seven failures showed fresh command 1 readback.
Their mapped status did not reach 1 within 15 seconds:

- Tank01_HeaterRemote → Tank01_HeaterStatus
- Tank01_USRemote → Tank01_USStatus
- Tank11_FillWaterOn → Tank11_FillWaterStatus
- Tank11_SprayRemote → Tank11_SprayStatus
- Tank14_FilterRemote → Tank14_FilterStatus
- Tank14_HeaterRemote → Tank14_HeaterStatus
- Tank07_FillWaterOn → Tank07_FillWaterStatus

Tank01_FilterRemote passed during this run. Later operator retests produced failures.
Those later failures must remain visible. The earlier pass must not hide them.
All 23 distinct Auto bits passed command readback and restoration checks.
These results do not establish equipment behavior in Auto mode.

The queue stopped at item 50, Tank13_HeaterRemote, after a communication error before a write receipt.
The report contains no write-1 request or receipt. This item has no completed cycle in this report.
Seven items had no completed cycle from this queue:

- Tank13_HeaterRemote
- Tank14_FillWaterOn
- Tank14_SwingRemote
- Tank15_FillWaterOn
- Tank16_FillWaterOn
- Tank16_FilterRemote
- Tank16_HeaterRemote

The stop marker remained in place. This run did not restart automatically.

An independent fresh read at 05:18:23 UTC showed these values:

- Tank01_DoorOpenRemote, Tank01_DoorCloseRemote and Tank01_FilterRemote: 0.
- Tank01_DoorClosed: 1.
- Tank13_HeaterRemote and Tank13_HeaterStatus: 0.

Later operator door tests were separate from this automatic non-door run.

The API cache later contained 50 API pass and 13 API fail results, with no pending observations.
It included earlier tests and later operator writes. These totals do not describe only the 49-cycle queue.
Signals without valid evidence remained Unchecked.

This pass excluded doors, numeric setpoints, RemoteStart, MainInlet and ambiguous shared addresses.
A missing status transition does not establish a prerequisite or a physical fault.
See [the prerequisite review](api-prerequisites-2026-10-26.md).

## Source and timing checks

The live OpenAPI definition and 362-tag catalog matched the saved 23 October supplier baseline.
This comparison established agreement between the API sources. It did not establish PLC behavior.
The line API omitted timezones from timestamps. The local configuration used Hong Kong time.
The testing PC temporarily used a +46-second correction in its ignored local configuration.
Fresh reads supplied that measurement. The 3-second freshness guard remained enabled.
The supplier clock did not change.
Measure this local correction again before another hardware session.

The testing PC retains the raw plan, per-command evidence and summaries in `/home/nep/Documents/api_test/artifacts/`.
Ignored `logs/` files retain API evidence and append-only events.
The repository and this report exclude credentials.

## Saved result behavior at this update

The visible API choices were **API pass / API fail / Unchecked**.
The legacy transport/export value `checked` means API pass. It remains compatible with older records.
Automatic passes retain fresh 1/status/0 evidence.
A saved human Pass can supply API pass with the source **Human-confirmed test**.
A newer automated failure takes priority. Changed command or feedback metadata invalidates old API evidence.

New attempt creates an attempt without a judgment.
It does not reset the saved human judgment or replace history.
Polling and temporary result-read failures do not reset judgments.
A pending API retest retains the previous settled result until new conclusive evidence arrives.
The detail identifies the pending attempt. New actual failures remain visible.

Each write page has compact API and human result controls.
Each control records an explicit browser decision, its timestamp and the previous value.
These controls send no PLC command. **Use API evidence** removes a manual API override.
The UI labels an override as manual. Its detail retains any existing automated failure.
Human choices remain **Not checked / Pass / Fail**.

Attempt results and saved signal results remain separate.
JSON exports include manual decision history.
Browser decisions apply to that browser, supplier target, operating mode and signal metadata.
At this update, browser decisions did not synchronize automatically to other PCs.

## Verification of this update

A combined backend, transport, validation and runner suite passed **322 tests** with mock or in-memory suppliers.
Separate Firefox tests covered API labels, filters, saved human judgments, explicit corrections, context and metadata separation, exports, and history.
The direct queue had 28 tests with fake suppliers only.
They covered cancellation, terminal restoration, unknown acknowledgments and audit storage failure during cleanup.

Read-only application checks after restart recovered all 63 stored API results: 50 pass and 13 fail.
No observation was pending. Remote data was fresh.
No binary command was active before restart.
At this update, preparation of the direct human queue included an offline preview only.
It did not include a production-line execution.

See [human queue instructions](human-line-test.md) for P / I / N, result files, scope and physical checks.
