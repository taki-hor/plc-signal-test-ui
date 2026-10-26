# API command prerequisites — source review, 26 October 2026

The supplier manual and saved Swagger schema **do not specify equipment prerequisites for individual commands**.
They define tag metadata and generic write operations.
They do not establish required Auto, RemoteStart, water, basket, door or setpoint conditions for an On command.

An accepted write with unchanged status does not identify the cause.
Possible causes include a PLC interlock, API mapping, equipment readiness or the observation window.
This review used local primary evidence only. It sent no PLC or API requests.
A separate 26 October comparison found no change from the saved 23 October schema/catalog.
That comparison did not establish operating behavior.

## Evidence and limits

The printed PDF pages and viewer page numbers agree.

| Subject | What the source establishes | What it does not establish | Primary source |
| --- | --- | --- | --- |
| Server readiness | The poller reads the configured PLC and stores polling records. HTTP reads return the latest database record. Setup requires network access, configured tags and an initial poll. | A recent HTTP response alone does not prove a new PLC sample. | [Manual](source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf#page=2), p2 §1–3, p4 §6.2, Swagger `GET /api/v1/tags/read`. |
| Authentication | Protected operations use the configured API key. | Authentication does not establish equipment readiness. | Manual p3 §4, [saved OpenAPI](source/supplier-openapi-2026-10-23.json). |
| Single write | A catalog W tag accepts an engineering value. Bool values are 0/1. Numeric values use type, multiplier and configured limits. The write path locks the shared PLC connection. | The sources define no command-specific permissive conditions, sequence or operation timer. | Manual pp4–6 §6.3, §7, Swagger `POST /api/v1/tags/write`, `TagWriteRequest`. |
| Write receipt | The response identifies the tag, PLC address, type, permission, value and write acknowledgment. | The receipt has no physical-completion, permissive, interlock-reason or command-specific feedback field. | Manual p5 §6.3, Swagger `TagWriteResponse`. |
| Batch write | One PLC session can contain 1–100 writes. The PDF rejects duplicate tag names. Swagger returns `results` and `count`. | Neither source promises atomic execution, simultaneous changes or command ordering. Neither promises rollback after partial failure or safe command combinations. A batch does not specify a PLC logic test. | Manual p5 §6.4, Swagger `POST /api/v1/tags/write/batch`, `MultiTagWriteRequest`, `MultiTagWriteResponse`. |
| Remote / Local | `Remote` is L4, R. `Local` is L3, R. Their descriptions distinguish API and manual mode. | No truth table says these values alone enable an actuator. No instruction permits writes to these read-only bits. | Manual pp8–9, catalog entries from `GET /api/v1/tags/list`. |
| Auto / On / RemoteStart | The catalog exposes separate named writable bits. | The sources omit priority, combination rules, level/edge behavior, pulse duration and reset conditions. Descriptions do not instruct users to combine these bits. | Manual pp9–21 tag catalog, saved `/api/v1/tags/list` response. |
| Alarms and observations | The catalog names equipment alarms, level alarms, baskets, door positions, flows and process values. | It does not define polarity, blocked commands, reset rules or all physical inputs in PLC logic. | Manual pp6–8 and tank catalog pp9–21. |
| Door and other feedback pairs | The catalog lists separate command/status tags, addresses and descriptions. | The sources provide no formal transition table, guaranteed 1/0 polarity, completion timeout or general hold/reset procedure. | Manual pp9–21, Swagger `TagInfo` contains metadata rather than behavioral mappings. |

The console's fresh-data guard and `Remote=1, Local=0` write gate are **local test controls**.
The 15-second observation limit is a local setting.
These controls are not supplier guarantees of completion.
Tank01 door reset rules and the physical Tank13/Tank12 correction come from operator evidence.
They remain separate from this source review.

The PDF batch example uses `Tank01_HeaterOn`. Neither catalog contains that name.
The exposed command is `Tank01_HeaterRemote`.
Do not use the example name.
Do not invent an alias.
See the [source alignment report](swagger-alignment-2026-10-23.md#pdf-examples-and-api-contract-details).

## Seven failed first-pass cases to investigate

These are the local command/status associations from the first pass.
Both source catalogs list these addresses. Neither confirms transition rules.
All entries are Bool with multiplier 1. Commands are W. Statuses are R.
The context column identifies useful readings, **not confirmed prerequisites**.
Later results do not change the scope of this historical first-pass list.

| Command and address | Related status and address | Read-only context before/during/after a supervised retest | Manual pages |
| --- | --- | --- | --- |
| `Tank01_HeaterRemote`, M321 | `Tank01_HeaterStatus`, D1002.2 | `Tank01_TempPV`, `Tank01_TempSV`, `Tank01_FilterStatus`, `Tank01_HaveBasket`, `Alarm30` heater, `Alarm51` tank level low, `Alarm52/53` buffer levels. | 7–9 |
| `Tank01_USRemote`, M322 | `Tank01_USStatus`, Y4 | Existing `Tank01A_USSV` and `Tank01B_USSV`, basket, both door positions and `Alarm51/52/53`. Also record the ultrasonic equipment's readiness indication. | 8–10 |
| `Tank11_FillWaterOn`, L150 | `Tank11_FillWaterStatus`, D1112.4 | Current `Tank11_FillWaterAuto`, `Tank11_RemoteStart`, `Tank11_WaterFlow`, `Tank11_HaveBasket`, `Alarm66` tank level low, `MainInletStatus`. Read mode/setpoint bits without changing them. | 8, 17 |
| `Tank11_SprayRemote`, M371 | `Tank11_SprayStatus`, D1112.1 | `Tank11_RemoteStart`, fill status, flow, basket, `Alarm66`, `MainInletStatus`. The catalog contains no `Tank11_SprayAuto` bit. | 8, 17 |
| `Tank14_FilterRemote`, M391 | `Tank14_FilterStatus`, D1128.1 | `Tank14_RemoteStart`, `Tank14_HaveBasket`, `Alarm28` filter overload, `Alarm69/70/71` tank/buffer levels, `Tank14_WaterFlow`. | 7–8, 19 |
| `Tank14_HeaterRemote`, M392 | `Tank14_HeaterStatus`, D1128.2 | Existing temperature PV/SV, filter status, basket, `Alarm36` heater, `Alarm69/70/71`. Record any equipment permissive/readiness display. | 7–8, 19 |
| `Tank07_FillWaterOn`, L130 | `Tank07_FillWaterStatus`, D1030.8 | `Tank07_FillWaterAuto`, `Tank07_RemoteStart`, basket, `Alarm60/61/62` tank/buffer levels, `MainInletStatus`. Record other relevant readings without enabling commands. | 8, 14 |

For every case, retain these records:

- `Remote` and `Local`.
- Supplier timestamp and poll success counts.
- Exact metadata signature and command readback.
- Current alarms and write receipt.
- Restoration evidence and operator result.

Status 0 differs from an absent, null or stale value.
An alarm at 0 or 1 is not a documented permissive truth table.

## Controlled hypothesis matrix

This matrix proposes evidence to collect. It is **not a plan for executable combinations**.
It does not authorize prerequisite, setpoint or interlock changes.

| Hypothesis | Evidence that helps distinguish it | Controlled next step |
| --- | --- | --- |
| API write route/address differs from the intended PLC signal | Exact API tag/address, value readback and an independent PLC/HMI bit observed for the same operation. | Ask the supplier or operator to identify the independent bit. Use one approved command. Retain both observations. |
| PLC accepts the command but a permissive blocks output | Failed API operation and successful local operation under equivalent, recorded equipment conditions. Relevant alarms, modes and readings. | Ask the supplier for the actual permissive list or ladder evidence. Do not infer a bypass from an alarm name. |
| Auto/On/RemoteStart interaction is required | Supplier truth table or controlled HMI evidence for required values and order. | Agree exact tags, values, order, timing and restoration before testing combinations. Change one factor at a time with an observer. |
| A process setpoint suppresses output | Existing process PV/SV, equipment indications and a known successful local operation. | Read existing values first. A numeric change requires its own approved target and restoration plan. |
| Status mapping/polarity is incorrect | Equipment operates but the proposed status does not follow. Another independently identified bit follows the operation. | Record the human result separately from API evidence. Ask the supplier to confirm the corrected feedback address and meaning. Do not silently substitute a status. |
| Polling/timing hides the transition | Fresh poll timestamps, command 1/0 readbacks, status samples and physical start/finish times. | Select an explicit observation window. Retain raw samples. Do not treat timeout as proof of an API-server defect. |

The supplier should provide these details for each failed command:

- Permissive conditions.
- Auto/On/RemoteStart truth table.
- Valid reset sequence.
- Expected feedback address and polarity.
- Expected timing.

These answers can support an approved plan with an operator.
Until then, record failed API observations and human results separately.
