# Signal test plan

This document contains a test plan and dated field records.
Those records retain their original session scope.
See [the 26 October review](swagger-second-run-2026-10-26.txt) for later full-catalog results.

1. Check access to the supplier REST API through the intended Wi-Fi path.
   Record host, URL, date and network result.
2. Check `X-API-Key` authentication through a read-only endpoint.
   Record HTTP 200 or the documented 401/503 response.
3. Load local `GET /api/tags` to parse supplier `/api/v1/tags/list`.
   Export live metadata.
   Compare it with the 29-SEP-2026 PDF baseline.
   Include types, addresses, permissions, descriptions, limits and multipliers.
   Check SignedWord definitions explicitly.
   Record the live count dynamically.
   Review CATALOG DIFFERENCE and duplicate-address warnings with the supplier.
   Resolve shared `D1036`, the `Tank01_TempSV` example/table difference and shared `L220` with the supplier.
   Do not silently change live metadata.
4. Check read-only signals from one `/tags/read` snapshot.
   Record timestamp, age, `tags_ok`, `tags_failed` and null values.
   Do not treat HTTP 200 as proof of a fresh PLC poll.
5. Check `Remote=1` with the supplier and machine operator.
   `Local`/`Remote` behavior beyond the descriptions needs confirmation.
6. Check the physical area and equipment with the responsible engineer.
   Enable local write test mode.
   It expires after 30 minutes. Browser refresh disables browser writes.
7. Test permitted setpoints within catalog limits.
   Start with non-motion values chosen by the engineer.
   Record engineering units, live address, supplier response and readback.
   The app applies no scaling.
8. Run one reviewed command/feedback test at a time.
   Check that initial feedback differs from the expected value.
   The runner records acceptance, feedback reads, elapsed time and PASS/OBSERVED/FAIL/TIMEOUT/BLOCKED/COMMUNICATION ERROR.
   Confirm command hold, pulse and clear rules before adding reset behavior.
9. Export communication and test logs as CSV/JSON.
   Save persistent JSONL with the test record if required.
10. Review failed and uncertain mappings with the supplier.
    Do not treat a name-derived mapping as confirmed field behavior without observation.

## Initial mappings

Door command/position pairs exist where both catalog tags are present.
Filter, heater, ultrasonic, swing, rectifier, spray and fill-water pairs are manual-derived candidates.
They support explicitly confirmed **Mapping under test** observations.
A matching transition returns OBSERVED.
Command behavior and physical feedback associations still need confirmation before the mapping becomes established.

The catalog does not document alarm polarity.
The UI therefore shows raw Bool values without severity.

## Static baseline — 29-SEP-2026

Source: HKPU PLC_API_User_Manual, Project PD-03726, Model KAL-1600-SG, 29-SEP-2026, Version 1.0.
Snapshot: 362 total, 141 writable, 221 read-only.
This baseline replaces the historical Word/zero-low TempAdj definitions and Tank16_PH.

| Tags | Latest supplier metadata |
| --- | --- |
| Tank01/03/05/07/10/13/14/16_TempAdj | D4010 through D4017 respectively. SignedWord, W, multiplier 0.1, −999.0 to 999.9 °C |
| Tank03_SwingSV | D1008. Word, W, multiplier 1.0, 5–120 CPM |
| Tank05_SwingSV | D1018. Word, W, multiplier 1.0, 5–120 CPM |
| Tank10_SwingSV | D1100. Word, W, multiplier 1.0, 5–120 CPM |
| Tank14_SwingSV | D1124. Word, W, multiplier 1.0, 5–120 CPM |
| Tank07_AmperePV | D1055. Word, R, multiplier 0.1 (previously 0.01) |
| Tank07_AmpereSV | D1362 (previously D1038). Word, W, multiplier 0.1 (previously 0.01), 0–200 A |
| Tank07_VoltagePV | D1054. Word, R, multiplier 0.1 (previously 0.01) |
| Tank16_Conductivity | Replaces Tank16_PH at D1142. Float, R, multiplier 1.0. Conductivity Meter Reading (MOhmCM) |
| Tank09_WaterFlow | Added at D1036. Word, R, multiplier 0.1. Tank09 Water Flow Meter Value (LPM) |

**SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.**
Keep both supplied addresses until confirmation.
Duplicate addresses do not prevent read-only startup.

For the mock regression, write Tank01_TempAdj = −5.0.
Check readback −5.0.
Check rejection of −999.1/1000.0 and non-finite/non-numeric inputs.
The API applies engineering scaling. Real and mock clients do not send −50.
Run configured door mock tests for Tank01, Tank03, Tank05, Tank07, Tank10, Tank12 and Tank14.
Check every test definition against the snapshot.
Include command permissions and feedback type.

The supplier API defaults to host `127.0.0.1`, port `8000`.
Its PowerShell example sets `PLC_API_HOST="0.0.0.0"` and `PLC_API_PORT="8080"` before `python plc_api.py`.
Get the actual field IP, port and API key.
Do not assume the example port.
See README for `.env`, start commands and read-only smoke requests.
Write tests require successful live metadata parsing and reviewed connection, mode, freshness and counts.

## Limits of mock evidence

Mock mode checks application behavior and logs only.
It does not prove Wi-Fi access, supplier authentication, PLC write acceptance, physical actuation or safety behavior.
The current catalog has no writable Float tag.
That field test requires a supplier catalog update.

## Read-only field verification — 2026-10-22

The console read all 362 supplier tags across five samples:
277 Bool, 69 Word, eight SignedWord and eight Float.
Metadata included 221 R and 141 W entries.
No values were missing, null or invalid. The supplier reported zero read failures.
The samples contained four distinct polls.

Reading W-tag values sends no write.
This initial phase was read only.
The later Tank 01 tests below established physical writes and hold rules for that tank only.
The initial session blocked 36 unconfirmed command/feedback mappings.
Later supervised Mapping under test observations do not confirm those earlier mappings retroactively.
See [verification-2026-10-22.md](verification-2026-10-22.md).

## Tank 01 physical follow-up — 2026-10-22

The operator approved separate open/close tests and confirmed the command rule.
The rule holds 1 during movement and sends 0 after physical completion.
Open operated and later feedback agreed. The original five-second window timed out.
Close passed in 8.704 seconds under the agreed thirty-second window.
The operator confirmed physical closure.

Later reads confirmed both command bits at 0. The door was closed.
At this follow-up, only Tank 01 open/close definitions changed to timeout_ms=30000.
Other tanks required separate readiness and command-rule confirmation.
The original TIMEOUT remains in the evidence.

The approved repeat open passed in 6.625 seconds.
The operator confirmed opening. The test checked M300 clear.
A separately approved close passed in 8.453 seconds.
The operator confirmed closure. The test checked M301 clear.
Both directions have software PASS and operator confirmation.

These agent-operated tests ended with Tank 01 closed and both commands at 0.
The agent operated no other tank during this follow-up.
The local artifacts directory retains the combined per-step JSON/CSV summary.

## Command hold and reset findings — 2026-10-22

Source: [HKPU PLC API User Manual, PD-03726,
29-SEP-2026, version 1.0](source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf).
Page 5 accepts Bool 0/1 and reports `written=true` for a successful write.
It specifies no automatic reset or complete per-tag hold/pulse procedure.
The page 2 connection-lock reset does not reset command bits.

Five groups cover all 102 writable Bool tags in the bundled baseline.
These counts describe that snapshot. Live metadata controls runtime behavior.
Descriptions suggest intended functions. They do not prove timing, polarity, interlocks or reset behavior.

| Group | Bool tags | Manual evidence | Hold/reset finding |
| --- | ---: | --- | --- |
| `MainInlet`, `*_FillWaterOn`, `*_AirAgitationOn`, `Tank07_CoolerOn` | 26 | Descriptions identify Always On requests. Examples appear on pages 8–10 and 14. | The working interpretation is a maintained ON request: 1 requests ON, and 0 removes that request. Descriptions suggest this meaning. No documented PLC truth table or stop guarantee establishes it. |
| `*_FillWaterAuto`, `*_AirAgitationAuto`, `Tank07_CoolerAuto` | 25 | Auto settings. Examples appear on pages 9–10 and 13–14. | Descriptions suggest maintained mode selections. They do not specify bit polarity or mode interactions. Sending 0 does not guarantee equipment stopping. |
| `*_FilterRemote`, `*_HeaterRemote`, `*_USRemote`, `*_SwingRemote`, `*_RectRemote`, `*_SprayRemote` | 21 | Remote On descriptions. Examples appear on pages 9–11, 14 and 17. | Descriptions suggest maintained run/enable requests. The supplier must confirm whether 1 must stay high and what 0 does. |
| `*_DoorOpenRemote`, `*_DoorCloseRemote` | 14 | Remote commands and separate actual opened/closed feedback. Examples appear on page 9. | The manual identifies command/feedback signals. It does not define duration/reset rules. The operator-confirmed Tank 01 procedure below does not establish rules for every tank. |
| `*_RemoteStart` | 16 | Remote Start descriptions. An example appears on page 9. | Unclassified. The manual states no pulse width, edge/level trigger, hold duration or reset rule. It does not establish Hold 1 or reset to 0. |

The operator confirmed the Tank 01 rule: hold 1 during door movement, then send 0 after physical completion.
Tests observed open/close feedback and later command clear.
This procedure comes from operator confirmation and tests, not an explicit manual instruction.
Software completion time and physical travel time remain different measures.

Sending 0 removes a request only where PLC logic gives it that meaning.
Auto mode, another request or PLC interlocks may still control equipment.
The 39 numeric writes are engineering setpoints: 31 Word and eight SignedWord.
The Bool table does not define a reset-to-zero rule for numeric values.

The compact After 1 toggle records the operator's decision in the send confirmation.
Hold becomes a local Keep at 1 record only after an accepted write and later fresh 1 readback.
It sends no additional write. It keeps the active state visible and permits the next guided test.
Eligibility does not confirm a non-door tag's hold behavior. RemoteStart remains unclassified.
Door commands keep the guided clear-to-0 procedure. The UI infers no pulse or reset.

Configuration retains 36 manual-derived mappings as unconfirmed.
The operator can select a supervised **Mapping under test** observation for each run.
A matching transition is **OBSERVED**, not confirmed-mapping PASS.
The default API path blocks these mappings without explicit selection.
Record supplier-confirmed rules before marking behavior or mapping as confirmed.

Earlier on 23 October, all 50 bundled cases used 30-second windows.
A later operator request changed the default to `timeout_ms=15000`.
Feedback tests permit a per-run override of 1–300 whole seconds.
Confirmation and logs retain that value.
This setting limits software observation only. It does not define hold duration, stopping or automatic reset.

## Physical Tank 13 door uses Tank12 API names — 23 October 2026

The operator confirmed Open and Close both operate the physical Tank 13 door.
Both API position signals follow that door's physical position.
The operator reported that physical Tank 12 has no door.

| Physical Tank 13 function | Supplier API tag | Address |
| --- | --- | --- |
| Open door | Tank12_DoorOpenRemote | M310 |
| Close door | Tank12_DoorCloseRemote | M311 |
| Door opened feedback | Tank12_DoorOpened | D1116.4 |
| Door closed feedback | Tank12_DoorClosed | D1116.5 |

Manual PDF page 17 and the catalog label these four tags Tank12.
Neither source contains a Tank13_Door tag.
The operator confirmed a physical identity difference in the supplied names.
Agreement between API and manual did not establish the physical tank number.
This finding does not imply swapped Open/Closed feedback.

Use the existing API names for transport.
Do not invent Tank13_Door names.
Do not rename all Tank12 signals.
The physical correction applies only to the four door tags above.
Supplier approval and a corrected source catalog remain pending.

Existing tank12-door-open/close test IDs and saved marks refer to physical Tank 13.
This review did not rewrite or copy records.
At this review, the UI still grouped source-named tags under Tank12.
A later physical display alias must retain the raw API name and operator evidence.

A read-only recheck compared all 14 door pairs with supplier metadata.
Names and addresses agreed with written sources.
The recheck did not physically test other door identities.
It sent no door commands or other line writes.
Local evidence: api_test/artifacts/door-physical-identity-audit-2026-10-23.json.

## Guided run list outside Feedback tests — stopped 23 October session

The operator requested tests outside the Feedback test list.
The live catalog contained 91 such signals: 52 Bool and 39 numeric.
The operator did not approve the old Tank01 filter readiness proposal.
This list replaced that proposal.

The first seven devices later received explicit test approval.
Those tests used 14 acknowledged writes, including restoration.
At the stopped session, all seven retained API checked status.
The operator reset all current human marks to Not checked.
History retained three original physical confirmations.
The session stopped because water was off. This list is not an unattended schedule.

The first block proposed seven On commands with distinct related statuses from the supplier table.
These are mappings under test. They are not supplier-certified completion pairs.

| Order | Command | Address | Read-status reference | Address |
| --- | --- | --- | --- | --- |
| 1 | Tank07_AirAgitationOn | L135 | Tank07_AirAgitationStatus | D1030.F |
| 2 | Tank07_CoolerOn | L131 | Tank07_CoolerStatus | D1030.B |
| 3 | Tank08_AirAgitationOn | L132 | Tank08_AirAgitationStatus | D1030.C |
| 4 | Tank09_AirAgitationOn | L133 | Tank09_AirAgitationStatus | D1030.D |
| 5 | Tank12_AirAgitationOn | L161 | Tank12_AirAgitationStatus | D1118.4 |
| 6 | Tank15_AirAgitationOn | L180 | Tank15_AirAgitationStatus | D1136.4 |
| 7 | Tank16_AirAgitationOn | L182 | Tank16_AirAgitationStatus | D1136.6 |

For each approved device, capture fresh baseline values.
Check stable tag/address metadata.
Proceed only with command/status 0, fresh data and Remote mode.
After operator readiness, propose command 1 for up to 15 seconds.
Record the receipt, later fresh command readback and related status.
Send 0 within that approved sequence.
Check later fresh command 0.
Observe related status and physical results.

Status 1 needs investigation. It does not prove another write will stop equipment.
Start the next device only after request restoration and operator readiness.
Human Pass/Fail remains separate from API readback and status.

Later blocks and pending items at that session:

- 23 distinct Auto bits: approved transitions and own-bit readback only.
  Actuator status does not prove Auto-mode acceptance.
- 39 numeric values: capture the fresh original value.
  Use an approved engineering test value.
  Check later own-tag readback.
  Restore the original value.
  Check restoration.
  Do not require immediate process PV equality as completion.
- 3 Air On tags on Tanks02/04/06: status bits share other tanks' Fill status addresses.
- 2 FillWaterAuto tags on Tanks03/05: both use L220.
- MainInlet: the planning snapshot was already 1.
  Preserve its state.
- 16 RemoteStart bits: agree operation, pulse/hold and reset sequence before writes.
  Names do not define a start sequence.

Seven proposed tests, 62 later tests and 22 pending items cover all 91 outside-list writes.
Plan values are snapshots for review. They do not authorize later restoration values.
Capture values again immediately before each test.
The Tank12 door correction does not rename Tank12 air tags.

The complete 91-row plan remains outside Git in api_test/artifacts/remaining-write-run-list-2026-10-23.csv and .json.
This supervised block tested no Auto, numeric, RemoteStart, shared-address or MainInlet cases.
Further execution requires a new instruction and current equipment readiness.
See [the stopped-session record](verification-2026-10-23.md#current-human-marks-reset-physical-evidence-retained) for that session's state and retained evidence.
