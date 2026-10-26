# API command prerequisites — source review, 26 October 2026

The supplier manual and saved Swagger schema **do not specify the equipment
prerequisites for individual commands**. They define tag metadata and generic
write operations. They do not establish whether an On command requires Auto,
RemoteStart, water, a basket, a door position or a setpoint. An acknowledged
write whose related status does not change therefore does not identify whether
the cause is a PLC interlock, an API mapping, equipment readiness or the chosen
observation window.

This review used local primary evidence only. It sent no PLC or API requests.
The separate 26 October catalog comparison found no change from the saved
23 October schema/catalog; that does not validate operating behavior.

## Evidence and limits

Page numbers below are the printed PDF pages, also the PDF viewer page numbers.

| Subject | What the source establishes | What it does not establish | Primary source |
| --- | --- | --- | --- |
| Server readiness | The poller reads the configured PLC and stores polling records; the HTTP read operation serves the latest database record. Server setup requires network access, configured tags and an initial poll. | A recent HTTP response does not by itself prove a new PLC sample. | [Manual](source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf#page=2), p2 §1–3; p4 §6.2; Swagger `GET /api/v1/tags/read`. |
| Authentication | Protected operations use the configured API key. | Authentication does not establish equipment readiness. | Manual p3 §4; [saved OpenAPI](source/supplier-openapi-2026-10-23.json). |
| Single write | A catalogued W tag accepts an engineering value; Bool values are 0/1. Numeric values use the type, multiplier and configured limits. The write path acquires a shared PLC connection lock. | No command-specific permissive conditions, sequencing or operation timer are defined. | Manual pp4–6 §6.3, §7; Swagger `POST /api/v1/tags/write`, `TagWriteRequest`. |
| Write receipt | The response identifies the tag, PLC address, type, permission, value and whether the write was acknowledged. | The receipt model contains no physical-completion, permissive, interlock-reason or per-command feedback field. | Manual p5 §6.3; Swagger `TagWriteResponse`. |
| Batch write | One PLC session can contain 1–100 writes; the PDF rejects duplicate tag names. Swagger returns `results` and `count`. | Neither source promises atomic execution, simultaneous changes, command ordering, rollback on partial failure or a safe combination of equipment commands. A batch is not a PLC logic test specification. | Manual p5 §6.4; Swagger `POST /api/v1/tags/write/batch`, `MultiTagWriteRequest`, `MultiTagWriteResponse`. |
| Remote / Local | `Remote` is L4, R; `Local` is L3, R. Their descriptions distinguish API and manual mode. | No truth table states that these values alone enable an actuator. No instruction permits writing these read-only bits. | Manual pp8–9; catalog entries returned by `GET /api/v1/tags/list`. |
| Auto / On / RemoteStart | The catalog exposes separate named writable bits. | Their priority, combination rules, level/edge behavior, pulse duration and reset conditions are absent. The descriptions are not instructions to combine them. | Manual pp9–21 tag catalog; saved `/api/v1/tags/list` response. |
| Alarms and observations | The catalog names equipment alarms, level alarms, basket signals, door positions, flows and process values. | It does not define their polarity, which commands they block, their reset rules or all physical inputs used in PLC logic. | Manual pp6–8 and tank catalog pp9–21. |
| Door and other feedback pairs | Command and status tags are listed separately with addresses and descriptions. | No formal command-to-feedback transition table, guaranteed 1/0 polarity, completion timeout or general hold/reset procedure is supplied. | Manual pp9–21; Swagger `TagInfo` has metadata fields rather than behavioral mappings. |

The console's fresh-data guard and `Remote=1, Local=0` write gate are **local test
controls**. Its 15-second observation limit is a local setting. These are not
supplier guarantees of command completion. The confirmed Tank01 door reset rule
and physical Tank13/Tank12 tag correction are operator evidence, separate from
this source review.

The PDF's batch example uses `Tank01_HeaterOn`, which exists in neither catalog.
The exposed command is `Tank01_HeaterRemote`. Do not use the example name or
invent an alias. See the [source alignment report](swagger-alignment-2026-10-23.md#pdf-examples-and-api-contract-details).

## Seven failed first-pass cases to investigate

These are the local command/status associations used in the test. Both source
catalogs list the addresses below, but do not confirm the transition rules. All
are Bool; command entries are W and status entries are R, with multiplier 1.
The context column identifies useful readings, **not confirmed prerequisites**.

| Command and address | Related status and address | Read-only context to capture before/during/after a supervised retest | Manual pages |
| --- | --- | --- | --- |
| `Tank01_HeaterRemote`, M321 | `Tank01_HeaterStatus`, D1002.2 | `Tank01_TempPV`, `Tank01_TempSV`, `Tank01_FilterStatus`, `Tank01_HaveBasket`; `Alarm30` heater; `Alarm51` tank level low, `Alarm52/53` buffer levels. | 7–9 |
| `Tank01_USRemote`, M322 | `Tank01_USStatus`, Y4 | Existing `Tank01A_USSV` and `Tank01B_USSV`, basket and both door positions; `Alarm51/52/53`; operator observation of the ultrasonic equipment's own readiness indication. | 8–10 |
| `Tank11_FillWaterOn`, L150 | `Tank11_FillWaterStatus`, D1112.4 | Current `Tank11_FillWaterAuto`, `Tank11_RemoteStart`, `Tank11_WaterFlow`, `Tank11_HaveBasket`, `Alarm66` tank level low, `MainInletStatus`. Read the writable mode/setpoint bits without changing them. | 8, 17 |
| `Tank11_SprayRemote`, M371 | `Tank11_SprayStatus`, D1112.1 | `Tank11_RemoteStart`, fill status, flow, basket, `Alarm66`, `MainInletStatus`; there is no catalogued `Tank11_SprayAuto` bit. | 8, 17 |
| `Tank14_FilterRemote`, M391 | `Tank14_FilterStatus`, D1128.1 | `Tank14_RemoteStart`, `Tank14_HaveBasket`, `Alarm28` filter overload, `Alarm69/70/71` tank/buffer levels, `Tank14_WaterFlow`. | 7–8, 19 |
| `Tank14_HeaterRemote`, M392 | `Tank14_HeaterStatus`, D1128.2 | Existing temperature PV/SV, filter status, basket, `Alarm36` heater, `Alarm69/70/71`; record the equipment's own permissive/readiness display if available. | 7–8, 19 |
| `Tank07_FillWaterOn`, L130 | `Tank07_FillWaterStatus`, D1030.8 | `Tank07_FillWaterAuto`, `Tank07_RemoteStart`, basket, `Alarm60/61/62` tank/buffer levels and `MainInletStatus`; capture other relevant tank readings without enabling them. | 8, 14 |

For every case, also retain `Remote`, `Local`, supplier timestamp, poll success
counts, the exact metadata signature, command readback, the current alarm
snapshot, write receipt, restoration evidence and the operator's result. A
named status at 0 is distinct from an absent/null/stale read. An alarm at 0 or
1 must not be treated as a documented permissive truth table.

## Controlled hypothesis matrix

This matrix proposes evidence to collect. It is **not an executable combination
plan**, and does not authorize changing a prerequisite, setpoint or interlock.

| Hypothesis | Evidence that would help distinguish it | Controlled next step |
| --- | --- | --- |
| API write route/address differs from the intended PLC signal | Compare the exact API tag/address, written-value readback and an independently observed PLC/HMI bit for the same operation. | Supplier or operator identifies the independent bit; use one approved command and retain both observations. |
| PLC accepts the command but a permissive blocks the output | Compare a failed API request with a successful local operation under recorded, equivalent equipment conditions. Capture relevant alarms/modes/readings. | Ask the supplier for the actual permissive list or ladder evidence. Do not infer a bypass from an alarm name. |
| Auto/On/RemoteStart interaction is required | Supplier truth table or controlled HMI evidence identifying the required values and order. | Leave combinations untested until exact tags, values, ordering, timing and restoration are agreed. Test one changed factor at a time with an observer. |
| A process setpoint suppresses output | Record existing process PV/SV and equipment indications; compare a known successful local operation. | Read existing values first. A numeric change requires its own approved target and restoration plan. |
| Status mapping/polarity is incorrect | Physical operation occurs, but the proposed status does not follow it; another independently identified bit does. | Record a human result separately from API evidence. Supplier confirms the corrected feedback address/meaning; do not silently substitute another status. |
| Polling/timing hides the transition | Compare fresh supplier poll timestamps, command 1/0 readbacks, status samples and physical start/finish times. | Use an explicitly chosen observation window and retain raw samples. Do not equate timeout with a proven API-server defect. |

The supplier should provide each failed command's permissive conditions,
Auto/On/RemoteStart truth table, valid reset sequence, expected feedback address
and polarity, and expected timing. Those answers can turn hypotheses into an
approved human-in-the-loop test plan. Until then, record the failed API
observation and the human result separately.
