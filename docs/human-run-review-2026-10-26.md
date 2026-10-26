# Operator review of the human queue — 26 October 2026

The operator completed all 63 cases and explicitly confirmed every P as human
Pass. The 30 N entries mix no visible response and uncertainty. They require an
ordered rerun and are not confirmed physical failures. Raw reports stay unchanged.

- **33 human Pass**: explicit judgments imported into the web records.
- **30 pending rerun**: do not reset or replace existing web judgments.
- **56 API pass / 7 API fail**: separate from the human result.
- **63 verified returns to 0**: API restoration, separate from physical stopping.

## Confirmed P results

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

## Unresolved API observations

Seven mapped statuses did not reach 1 despite fresh command 1 readback:
Tank01_FilterRemote, Tank01_HeaterRemote, Tank01_USRemote, Tank11_FillWaterOn,
Tank11_SprayRemote, Tank14_FilterRemote and Tank14_HeaterRemote. Each restored to
0. Tank07_FillWaterOn now has both API pass and human Pass; an earlier automatic
check timed out. These changes do not prove an API fault or a prerequisite.

Of the 30 N entries, 21 Auto bits and Tank02_FillWaterOn/Tank04_FillWaterOn passed
API verification; seven failed as above. Tank07_AirAgitationAuto and
Tank07_CoolerAuto received P. An Auto readback alone does not define a physical
success condition.

Raw snapshots contain low-level-labelled Alarm51/53 during Tank01 failures and
Alarm69/71 during Tank14 failures. Tank11 failures do not share that pattern.
Tank07 fill succeeded with MainInletStatus, RemoteStart, Auto and basket at 0.
These are supplier-review clues, not confirmed interlock rules. See the
[prerequisite review](api-prerequisites-2026-10-26.md).

## Web records and ordered rerun

Imported Pass decisions retain the review time, original observation time,
frozen metadata and source reference. Later explicit browser corrections win.
API failure precedence uses observation time, so a later review does not hide an
API failure recorded after that physical check. No N is imported as Fail or used
to clear an existing judgment. The import is separate from API-cycle proof.

The ignored local run folder
`logs/human-line-test-20261026T054921-c083f3c0/` also contains:

- `reviewed-results.json` and `.csv`: operator review preserving the raw evidence.
- `rerun-unconfirmed.json`: exactly 30 N cases, excluding all 33 confirmed P cases.

A local convenience copy is `logs/rerun-unconfirmed.json`. Preview from the repository:

```bash
.venv/bin/python tools/human_line_test.py --plan logs/rerun-unconfirmed.json
```

Add `--execute` only when ready to operate the line. The queue sorts by tank
number and related function. Before each new tank, it verifies the previous 0
and waits for Enter/R so the operator can move; Q stops. Same-tank cases continue
automatically. This ordering does not enable prerequisites or combine commands.

The rerun was prepared and previewed offline only. API restoration and the
operation-at-1 verdict do not establish physical stopping.


## Verification of the update

150 targeted backend/runner checks and the 25-case Firefox import/preservation
suite passed. A separate missing-store reload regression passed after the final
persistence adjustment. The revised queue has 34 fake-only tests. A read-only
Firefox check of the running application showed all 33 exact P-tag Human Pass
badges; write controls remained disabled. No PLC command was sent for the import,
verification or preparation of the rerun.
