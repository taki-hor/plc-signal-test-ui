# Operator review of the human queue — 26 October 2026

This note records the first 63-case human run and its initial review.
It does not describe the final 141-tag results or later operator corrections.
See [the second-run review](swagger-second-run-2026-10-26.txt) for those later results.

The operator completed all 63 cases and confirmed every P as human Pass.
The 30 N entries mixed no visible response and uncertainty.
They needed a tank-ordered rerun. They were not confirmed physical failures.
Raw reports remain unchanged.

- **33 human Pass**: explicit judgments imported into web records.
- **30 pending rerun**: no reset or replacement of existing web judgments.
- **56 API pass / 7 API fail**: separate from the human result.
- **63 verified returns to 0**: API restoration, separate from physical stopping.

## Confirmed P results at this review

| Tank | Confirmed commands |
| --- | --- |
| Tank03 | `Tank03_FilterRemote`, `Tank03_HeaterRemote`, `Tank03_SwingRemote` |
| Tank05 | `Tank05_FilterRemote`, `Tank05_HeaterRemote`, `Tank05_SwingRemote` |
| Tank06 | `Tank06_FillWaterOn` |
| Tank07 | `Tank07_AirAgitationOn`, `Tank07_AirAgitationAuto`, `Tank07_CoolerOn`, `Tank07_CoolerAuto`, `Tank07_FillWaterOn`, `Tank07_FilterRemote`, `Tank07_RectRemote` |
| Tank08 | `Tank08_AirAgitationOn` |
| Tank09 | `Tank09_AirAgitationOn`, `Tank09_FillWaterOn` |
| Tank10 | `Tank10_FillWaterOn`, `Tank10_FilterRemote`, `Tank10_HeaterRemote`, `Tank10_SwingRemote` |
| Tank12 | `Tank12_AirAgitationOn`, `Tank12_FillWaterOn` |
| Tank13 | `Tank13_FillWaterOn`, `Tank13_HeaterRemote` |
| Tank14 | `Tank14_FillWaterOn`, `Tank14_SwingRemote` |
| Tank15 | `Tank15_AirAgitationOn`, `Tank15_FillWaterOn` |
| Tank16 | `Tank16_AirAgitationOn`, `Tank16_FillWaterOn`, `Tank16_FilterRemote`, `Tank16_HeaterRemote` |

## Unresolved API observations at this review

Seven mapped statuses did not reach 1 despite fresh command 1 readback:

- Tank01_FilterRemote
- Tank01_HeaterRemote
- Tank01_USRemote
- Tank11_FillWaterOn
- Tank11_SprayRemote
- Tank14_FilterRemote
- Tank14_HeaterRemote

Each command returned to 0.
Tank07_FillWaterOn gained API pass and human Pass after an earlier automatic timeout.
These results did not prove an API fault or a prerequisite.

Of the 30 N entries, 21 Auto bits and Tank02_FillWaterOn/Tank04_FillWaterOn passed API checks.
Seven failed as listed above.
Tank07_AirAgitationAuto and Tank07_CoolerAuto received P.
An Auto readback alone does not define physical success.

Raw snapshots contained Alarm51/53 during Tank01 failures and Alarm69/71 during Tank14 failures.
Their labels describe low levels. Tank11 failures did not share that pattern.
Tank07 fill succeeded with MainInletStatus, RemoteStart, Auto and basket at 0.
These observations help supplier review. They do not confirm interlock rules.
See [the prerequisite review](api-prerequisites-2026-10-26.md).

## Web records and tank-ordered rerun

Imported Pass decisions retain review time, original observation time, fixed metadata and source reference.
Later explicit browser corrections take priority.
API failure priority uses observation time.
A later review must not hide an API failure recorded after the physical check.
The import does not treat N as Fail or clear an existing judgment.
The import remains separate from API-cycle proof.

The ignored local folder `logs/human-line-test-20261026T054921-c083f3c0/` also contains:

- `reviewed-results.json` and `.csv`: operator review with raw evidence preserved.
- `rerun-unconfirmed.json`: exactly 30 N cases, excluding all 33 confirmed P cases.

`logs/rerun-unconfirmed.json` is a local convenience copy.
Preview it from the repository:

```bash
.venv/bin/python tools/human_line_test.py --plan logs/rerun-unconfirmed.json
```

Add `--execute` only when ready to operate the line.
The queue sorts by tank number and function.
Before each new tank, it checks the previous 0 and waits for Enter/R.
This pause lets the operator move. Q stops the queue.
Cases at the same tank continue automatically.
The order does not enable prerequisites or combine commands.

At this review, preparation included an offline preview only.
API restoration and the operation-at-1 verdict did not establish physical stopping.

## Verification of this update

150 targeted backend/runner checks and the 25-case Firefox suite passed.
The Firefox suite covered imports and result retention.
A separate missing-store reload test passed after the final persistence change.
The revised queue had 34 tests with fake suppliers only.

A read-only Firefox check showed all 33 exact P-tag Human Pass badges in the running application.
Write controls stayed disabled.
Import, verification and rerun preparation sent no PLC commands.
