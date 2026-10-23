# Signal test plan

1. Confirm the backend host can reach the supplier REST API over the intended Wi-Fi path. Record host, URL, date, and network result.
2. Confirm `X-API-Key` authentication with a read-only endpoint. Record 200 or the documented 401/503 response.
3. Load the local `GET /api/tags`, which parses the supplier `/api/v1/tags/list`; export/compare live metadata against the 29-SEP-2026 PDF baseline, including all types (especially SignedWord), addresses, permissions, descriptions, limits and multipliers. Record the live count dynamically. Review displayed/logged CATALOG DIFFERENCE and duplicate-address warnings with the supplier. Resolve shared `D1036`, the `Tank01_TempSV` API-example/table discrepancy and shared `L220` with the supplier; never silently correct live metadata.
4. Verify read-only signals using the single `/tags/read` snapshot. Record timestamp, age, `tags_ok`, `tags_failed`, and any null values. Do not treat HTTP 200 as proof of a fresh PLC poll.
5. Verify `Remote=1` with the supplier and machine operator. `Local`/`Remote` behavior beyond the documented descriptions needs confirmation.
6. Confirm the physical area and equipment with the responsible engineer. Enable write test mode on the local workstation. It expires after 30 minutes and a refresh disables the browser's ability to write.
7. Test permitted writable setpoints within catalog limits, beginning with non-motion values chosen by the engineer. Record entered engineering units, live address, supplier response, and observed readback. No scaling is applied in this app.
8. Run one reviewed command/feedback test at a time. Confirm initial feedback differs from the expected value. The runner records write acceptance, each feedback read, PASS/OBSERVED/FAIL/TIMEOUT/BLOCKED/COMMUNICATION ERROR, and elapsed time. Confirm whether commands are latched, momentary, or need explicit clearing before adding reset behavior.
9. Export communication and test logs as CSV/JSON. Save the persistent JSONL log with the test record if required.
10. Review failed and uncertain mappings with the PLC supplier. Do not promote a name-based mapping to confirmed field behavior without observation.

## Initial mappings

Door open/close command → actual door opened/closed feedback pairs are configured for tanks where both catalog tags exist. The remaining filter, heater, ultrasonic, swing, rectifier, spray and fill-water pairs are manual-derived candidates. They can be run as explicitly confirmed **Mapping under test** observations. A matching transition returns OBSERVED; their command semantics and physical feedback association still require confirmation before being treated as established mappings. Alarm polarity is undocumented in the catalog, so the UI displays raw Bool values without assigning severity.

## Latest static baseline

Source: HKPU PLC_API_User_Manual, Project PD-03726, Model KAL-1600-SG, 29-SEP-2026, Version 1.0. Snapshot: 362 total, 141 writable, 221 read-only. The historical Word/zero-low TempAdj definitions and Tank16_PH are superseded.

| Tags | Latest supplier metadata |
| --- | --- |
| Tank01/03/05/07/10/13/14/16_TempAdj | D4010 through D4017 respectively; SignedWord, W, multiplier 0.1, −999.0 to 999.9 °C |
| Tank03_SwingSV | D1008; Word, W, multiplier 1.0, 5–120 CPM |
| Tank05_SwingSV | D1018; Word, W, multiplier 1.0, 5–120 CPM |
| Tank10_SwingSV | D1100; Word, W, multiplier 1.0, 5–120 CPM |
| Tank14_SwingSV | D1124; Word, W, multiplier 1.0, 5–120 CPM |
| Tank07_AmperePV | D1055; Word, R, multiplier 0.1 (previously 0.01) |
| Tank07_AmpereSV | D1362 (previously D1038); Word, W, multiplier 0.1 (previously 0.01), 0–200 A |
| Tank07_VoltagePV | D1054; Word, R, multiplier 0.1 (previously 0.01) |
| Tank16_Conductivity | Replaces Tank16_PH at D1142; Float, R, multiplier 1.0; Conductivity Meter Reading (MOhmCM) |
| Tank09_WaterFlow | Added at D1036; Word, R, multiplier 0.1; Tank09 Water Flow Meter Value (LPM) |

**SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.** Keep both addresses exactly as supplied until confirmed. Duplicate addresses never prevent read-only startup.

Mock regression: write Tank01_TempAdj = −5.0, verify readback −5.0; reject −999.1/1000.0 and non-finite/non-numeric inputs. The API performs engineering scaling; neither real nor mock client sends −50. Run the configured door open/close mock tests for Tank01, Tank03, Tank05, Tank07, Tank10, Tank12 and Tank14. Validate every test-case definition against the snapshot, including command permissions and feedback type.

The supplier API defaults to host `127.0.0.1`, port `8000`. Its PowerShell example sets `PLC_API_HOST="0.0.0.0"` and `PLC_API_PORT="8080"` before `python plc_api.py`; obtain the actual field host IP, port and API key rather than assuming that example port. See README for `.env`, launch commands and read-only smoke requests. No write test precedes successful live metadata parsing and review of connection, mode, freshness and counts.

## Limits of mock evidence

Mock mode verifies application behavior and log output only. It does not prove Wi-Fi reachability, supplier authentication, PLC write acceptance, physical actuation, or safety behavior. The current catalog has no writable Float tag, so that field test is pending a supplier catalog update.


## Read-only field verification — 2026-10-22

The live console read all 362 supplier tags across five samples: 277 Bool,
69 Word, eight SignedWord and eight Float, including 221 R and 141 W metadata
entries. There were no missing, null or invalid values and zero supplier read
failures; four distinct poll snapshots were observed. Reading W-tag values
sends no write command. This initial phase was read only; physical writes and command-hold rules
were established only for the later Tank 01 tests recorded below. The 36 unconfirmed
command/feedback mappings were blocked during that initial field session; the
later supervised Mapping under test path does not retroactively confirm them. See [verification-2026-10-22.md](verification-2026-10-22.md).


## Tank 01 physical follow-up

The operator approved separate open/close tests and confirmed the command rule:
hold 1 during movement, then write 0 after physical completion. Open operated
and later feedback agreed, but the original five-second software window timed
out. Close passed in 8.704 seconds under the subsequently agreed thirty-second
window, with physical closure confirmed. Both command bits were verified 0
after clearing; the door was closed. Only Tank 01 open/close definitions were
changed to timeout_ms=30000. Other tanks require their own readiness and command
semantics confirmation. The original TIMEOUT remains in the evidence record.


Tank 01 repeat results: the approved 30-second open case passed in 6.625 seconds,
with physical opening confirmed and M300 clear verified. A separately approved
restore-close passed in 8.453 seconds, with physical closure confirmed and M301
clear verified. Both directions have software PASS and operator confirmation.
At the end of these agent-operated tests, Tank 01 was closed with both
commands 0; no other tank was operated by the agent. The combined per-step JSON/CSV summary is saved in the local artifacts directory.

## Command hold and reset findings

Recorded 2026-10-22 against [HKPU PLC API User Manual, PD-03726,
29-SEP-2026, version 1.0](source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf).
Page 5 accepts Bool values 0/1 and reports `written=true` for a successful write.
It does not specify an automatic command reset or a complete per-tag hold/pulse
protocol. The connection-lock reset on page 2 is unrelated to command-bit reset.

These five groups cover all 102 writable Bool tags in the bundled baseline.
Counts describe that snapshot; live metadata remains the runtime authority.
A description is evidence of the intended function, not proof of PLC timing,
polarity, interlocks or reset behavior.

| Group | Bool tags | Manual evidence | Hold/reset finding |
| --- | ---: | --- | --- |
| `MainInlet`, `*_FillWaterOn`, `*_AirAgitationOn`, `Tank07_CoolerOn` | 26 | Descriptions identify Always On requests; examples on pages 8–10 and 14. | A maintained ON request is the working interpretation: keep 1 while requesting ON and use 0 to withdraw that request. This is inferred from the descriptions, not a documented PLC truth table or guaranteed stop. |
| `*_FillWaterAuto`, `*_AirAgitationAuto`, `Tank07_CoolerAuto` | 25 | Auto settings; examples on pages 9–10 and 13–14. | These suggest maintained mode selections. Exact bit polarity and mode interactions are not specified. Sending 0 must not be interpreted as a guaranteed equipment stop. |
| `*_FilterRemote`, `*_HeaterRemote`, `*_USRemote`, `*_SwingRemote`, `*_RectRemote`, `*_SprayRemote` | 21 | Remote On descriptions; examples on pages 9–11, 14 and 17. | Maintained run/enable requests are a working interpretation. Whether 1 must stay high and what 0 does still require supplier/PLC confirmation. |
| `*_DoorOpenRemote`, `*_DoorCloseRemote` | 14 | Remote commands and separate actual opened/closed feedback; examples on page 9. | The manual identifies command/feedback signals but does not define command duration/reset rules. The separately confirmed Tank 01 procedure is recorded below. It does not establish the rule for every tank. |
| `*_RemoteStart` | 16 | Remote Start descriptions; example on page 9. | Unclassified: no pulse width, edge/level trigger, hold duration or reset rule is stated. The manual alone does not establish whether to keep 1 or reset to 0. |

For the supervised Tank 01 tests, the operator explicitly confirmed: hold 1
while the door moves, then send 0 after physical completion. Open/close feedback
and subsequent command clear were observed. This procedure comes from operator
confirmation and those tests, rather than an explicit manual instruction. The
software completion timer and physical travel time remain different measures.

Sending 0 removes a request only where the PLC logic implements that meaning.
Auto mode, another request, or PLC interlocks may still control the equipment.
The 39 numeric writable tags (31 Word and eight SignedWord in this baseline)
are engineering setpoints; the Bool hold/reset table does not define a rule to
reset those values to zero.

The UI's compact After 1 toggle records an explicit operator decision in the
send confirmation. Hold becomes a local Keep at 1 record only after an accepted
write and later fresh readback of 1. It sends no additional write, keeps the
state visible, and permits the next guided test. Eligibility of a non-door tag
for this option does not confirm its hold behavior; RemoteStart remains
unclassified. Door commands retain the guided clear-to-0 workflow. No pulse or
reset is inferred. The 36 manual-derived command/feedback mappings remain marked
unconfirmed in configuration, but can be selected for a supervised per-run
**Mapping under test** observation. A matching transition is **OBSERVED**, rather
than a confirmed-mapping PASS. The default API path still blocks these mappings
without explicit opt-in. Record supplier-confirmed rules before promoting a
tag's behavior or mapping to confirmed status.


Earlier on 23 October, all 50 bundled cases used a 30-second window. The later
operator request changes the default to `timeout_ms=15000`. Feedback tests allow
a per-run override of 1–300 whole seconds, captured in confirmation and logs.
This limits software observation only. It does not specify a hold duration,
stop or automatic reset.

## Physical Tank 13 door uses Tank12 API names

On 23 October 2026, the operator explicitly confirmed both Open and Close
operate the physical Tank 13 door. The operator also confirmed both API position
feedback signals follow that door's actual position. Physical Tank 12 has no
door, according to the operator.

| Physical Tank 13 function | Supplier API tag | Address |
| --- | --- | --- |
| Open door | Tank12_DoorOpenRemote | M310 |
| Close door | Tank12_DoorCloseRemote | M311 |
| Door opened feedback | Tank12_DoorOpened | D1116.4 |
| Door closed feedback | Tank12_DoorClosed | D1116.5 |

The supplier manual PDF page 17 and current live catalog both label these four
tags Tank12. Neither contains a Tank13_Door tag. This is an operator-confirmed
physical identity discrepancy in the supplied names. Matching the API to the
manual did not establish the correct physical tank number. This finding does
not imply an Open/Closed feedback swap.

Use the exact existing API names for transport. Do not invent Tank13_Door API
names or rename all Tank12 signals. The physical correction applies only to the
four door tags above. Supplier sign-off and a corrected source catalog remain
pending. Existing tank12-door-open/close test IDs and saved operator marks refer
to the physical Tank 13 door; no record was rewritten or copied. The current UI
still groups these source-named tags under Tank12. Any future physical display
alias must retain the raw API name and this operator evidence.

A read-only recheck compared all 14 door pair definitions with the supplier
metadata. Their names and addresses agree with the written sources, but no new
physical identity test was performed for the other doors. No door commands or
other line writes were sent during this check. The detailed local artifact is
api_test/artifacts/door-physical-identity-audit-2026-10-23.json.

## Guided run list outside Feedback tests

The operator requested tests of writes outside the existing Feedback test list.
The live catalog contains 91 such signals: 52 Bool and 39 numeric. The old
Tank01 filter readiness question was not approved and was superseded by this
list. The first seven devices were subsequently tested with explicit operator
authorization, using 14 acknowledged writes including restoration. All seven
retain API checked; all current human marks are Not checked at the operator's
request. Three original physical confirmations remain in history. Testing is
stopped because water was turned off. This list is not an unattended schedule.

First proposed block: seven On commands with distinct, related read-status
references from the supplier tag table. These are mappings under test, not new
supplier-certified completion pairs.

| Order | Command | Address | Read-status reference | Address |
| --- | --- | --- | --- | --- |
| 1 | Tank07_AirAgitationOn | L135 | Tank07_AirAgitationStatus | D1030.F |
| 2 | Tank07_CoolerOn | L131 | Tank07_CoolerStatus | D1030.B |
| 3 | Tank08_AirAgitationOn | L132 | Tank08_AirAgitationStatus | D1030.C |
| 4 | Tank09_AirAgitationOn | L133 | Tank09_AirAgitationStatus | D1030.D |
| 5 | Tank12_AirAgitationOn | L161 | Tank12_AirAgitationStatus | D1118.4 |
| 6 | Tank15_AirAgitationOn | L180 | Tank15_AirAgitationStatus | D1136.4 |
| 7 | Tank16_AirAgitationOn | L182 | Tank16_AirAgitationStatus | D1136.6 |

For each approved device, capture fresh baseline values and stable tag/address
metadata. Proceed only with verified request/status 0, fresh data and Remote
mode. After operator readiness, propose command 1 for up to 15 seconds. Record
its receipt, subsequent fresh request readback and related status. Send 0 as
part of that explicitly approved sequence. Verify later fresh readback 0 and
observe the related status/physical result. A status still at 1 is an observation
to investigate, not proof that another write will stop it. Do not start the next
device until the current request is restored and the operator is ready. Human
Pass/Fail stays separate from API readback and status observations.

Later blocks and pending items:

- 23 distinct Auto bits: approved transitions and own-bit readback only. An
  actuator status does not prove Auto-mode acceptance.
- 39 numeric values: capture the fresh original value, use an operator-approved
  engineering test value, verify later own-tag readback, then restore and verify
  the original. Do not treat a process PV as immediate equality completion.
- 3 Air On tags on Tanks02/04/06: status bits alias other tanks' Fill status.
- 2 FillWaterAuto tags on Tanks03/05: both use L220.
- MainInlet: the planning snapshot is already 1. Preserve its state.
- 16 RemoteStart bits: operating, pulse/hold and reset sequence must be agreed
  before any write. No start sequence is inferred from the tag names.

The seven proposed tests plus 62 later tests and 22 pending items cover all 91
outside-list writes. All values in the plan are snapshots
for review, never authority for a later restore. Recapture immediately before
each test. The Tank12-door physical correction does not rename Tank12 air tags.
The complete 91-row plan is saved outside Git as api_test/artifacts/
remaining-write-run-list-2026-10-23.csv and .json. No Auto-mode, numeric,
RemoteStart, shared-address or MainInlet test was run in this supervised block.
Further execution requires a new instruction and current equipment readiness.
See the [latest verification record](verification-2026-10-23.md#current-human-marks-reset-physical-evidence-retained)
for the stopped-session state and preserved evidence.
