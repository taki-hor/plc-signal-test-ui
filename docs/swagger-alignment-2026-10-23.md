# PDF and saved Swagger/API alignment — 23 October 2026

## Scope and source quality

The user authorized the first comparison while the line adapter was absent.
It used a historical API capture from about 18:37 Hong Kong time on 23 October 2026.
The operator then reconnected the adapter.

A fresh GET-only check ran at **20:05:19 Hong Kong time on 23 October 2026**.
It confirmed that the live Swagger schema and all 362 tag definitions match the
saved captures in meaning. The docs, schema, catalog and read endpoints returned
HTTP 200. The read snapshot contained all 362 catalog signals, with 362 OK and
0 failed.

The audit retains the original captures and the fresh check as evidence.
It sent no production write or actuator test.

The PDF is `docs/source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf`,
SHA256 `a157cfc7165fa86ee23ea10fc7293b343b4a2e356c8f7a70b863876b4ad0f40e`.
Its copy at `docs/HKPU PLC_API_User_Manual (PD-03726).pdf` is byte-identical.
The audit independently extracted all 362 rows from the PDF table. Their names,
addresses, types, permissions, multipliers, descriptions and published limits
match the existing PDF-derived mock fixture. This avoids treating that fixture
as independent proof of the PDF's content.

The repository contains this primary evidence beside the PDF:

- [Swagger OpenAPI schema](source/supplier-openapi-2026-10-23.json).
- [Actual `/api/v1/tags/list` response](source/supplier-tags-2026-10-23.json).
- [Capture provenance, timestamps, hashes and counts](source/supplier-api-capture-2026-10-23.json).
- [Complete 47-signal comparison CSV](swagger-signal-differences-2026-10-23.csv).

Swagger's OpenAPI schema defines generic request/response models. It does not
contain an authoritative per-signal list or command-to-feedback truth table.
The saved response from its `/api/v1/tags/list` operation supplies the 362 actual
signal definitions. The retained capture has no API key or authentication token.

## Result

Both sources list 362 signals: 141 writable and 221 read-only. There are no missing
or extra catalog names. All 362 addresses, data types, W/R permissions and
multipliers agree. The app keeps all operational tag names.

The differences affect 47 signal definitions. The API omits the PDF limits for
39 numeric signals. Another 8 descriptions differ only in spacing.
The API response omits both limit keys for every tag. It does not return
explicit null values. The saved Swagger TagInfo model also omits these properties.
Missing metadata does not prove that a numeric write is unlimited or that the
supplier no longer enforces the PDF limits. The audit sent no out-of-range writes.

## Every numeric signal with unavailable API limits

For each row below, the PDF supplies both bounds, while both API limit keys are
absent. These 39 signals account for 78 missing published bound values.

| Signal | Address | PDF low | PDF high | API low/high | PDF page |
| --- | --- | ---: | ---: | --- | ---: |
| Tank01A_USSV | D1044 | 0.0 | 8.0 | Not published | 9 |
| Tank01B_USSV | D1048 | 0.0 | 8.0 | Not published | 9 |
| Tank01_TempAdj | D4010 | -999.0 | 999.9 | Not published | 9 |
| Tank01_TempSV | D4020 | 0.0 | 999.9 | Not published | 9 |
| Tank01_TimeSV | D4051 | 0.0 | 9999.0 | Not published | 9 |
| Tank02_TimeSV | D4052 | 0.0 | 9999.0 | Not published | 10 |
| Tank03_SwingSV | D1008 | 5.0 | 120.0 | Not published | 11 |
| Tank03_TempAdj | D4011 | -999.0 | 999.9 | Not published | 11 |
| Tank03_TempSV | D4021 | 0.0 | 999.9 | Not published | 11 |
| Tank03_TimeSV | D4053 | 0.0 | 9999.0 | Not published | 11 |
| Tank04_TimeSV | D4054 | 0.0 | 9999.0 | Not published | 12 |
| Tank05_SwingSV | D1018 | 5.0 | 120.0 | Not published | 12 |
| Tank05_TempAdj | D4012 | -999.0 | 999.9 | Not published | 12 |
| Tank05_TempSV | D4022 | 0.0 | 999.9 | Not published | 12 |
| Tank05_TimeSV | D4055 | 0.0 | 9999.0 | Not published | 13 |
| Tank06_TimeSV | D4056 | 0.0 | 9999.0 | Not published | 13 |
| Tank07_AmpereSV | D1362 | 0.0 | 200.0 | Not published | 13 |
| Tank07_TempAdj | D4013 | -999.0 | 999.9 | Not published | 14 |
| Tank07_TempSV | D4023 | 0.0 | 999.9 | Not published | 14 |
| Tank07_TimeSV | D4057 | 0.0 | 9999.0 | Not published | 14 |
| Tank08_TimeSV | D4058 | 0.0 | 9999.0 | Not published | 15 |
| Tank09_TimeSV | D4059 | 0.0 | 9999.0 | Not published | 15 |
| Tank10_SwingSV | D1100 | 5.0 | 120.0 | Not published | 16 |
| Tank10_TempAdj | D4014 | -999.0 | 999.9 | Not published | 16 |
| Tank10_TempSV | D4024 | 0.0 | 999.9 | Not published | 16 |
| Tank10_TimeSV | D4060 | 0.0 | 9999.0 | Not published | 16 |
| Tank11_TimeSV | D4061 | 0.0 | 9999.0 | Not published | 17 |
| Tank12_TimeSV | D4062 | 0.0 | 9999.0 | Not published | 18 |
| Tank13_TempAdj | D4015 | -999.0 | 999.9 | Not published | 18 |
| Tank13_TempSV | D4025 | 0.0 | 999.9 | Not published | 18 |
| Tank13_TimeSV | D4063 | 0.0 | 9999.0 | Not published | 18 |
| Tank14_SwingSV | D1124 | 5.0 | 120.0 | Not published | 19 |
| Tank14_TempAdj | D4016 | -999.0 | 999.9 | Not published | 19 |
| Tank14_TempSV | D4026 | 0.0 | 999.9 | Not published | 19 |
| Tank14_TimeSV | D4064 | 0.0 | 9999.0 | Not published | 19 |
| Tank15_TimeSV | D4065 | 0.0 | 9999.0 | Not published | 20 |
| Tank16_TempAdj | D4017 | -999.0 | 999.9 | Not published | 20 |
| Tank16_TempSV | D4027 | 0.0 | 999.9 | Not published | 21 |
| Tank16_TimeSV | D4066 | 0.0 | 9999.0 | Not published | 21 |

## Every spacing-only description difference

These eight API descriptions contain two spaces before `(Degree Celsius)`.
The PDF contains one. The wording, address and signal meaning otherwise agree. The
CSV retains both exact strings. This is formatting, not a different device.

| Signal | Address | PDF page | Difference |
| --- | --- | ---: | --- |
| Tank01_TempPV | D4000 | 9 | Extra API space before unit |
| Tank03_TempPV | D4001 | 11 | Extra API space before unit |
| Tank05_TempPV | D4002 | 12 | Extra API space before unit |
| Tank07_TempPV | D4003 | 14 | Extra API space before unit |
| Tank10_TempPV | D4004 | 16 | Extra API space before unit |
| Tank13_TempPV | D4005 | 18 | Extra API space before unit |
| Tank14_TempPV | D4006 | 19 | Extra API space before unit |
| Tank16_TempPV | D4007 | 21 | Extra API space before unit |

## PDF examples and API-contract details

1. PDF page 4's abbreviated tag-list example assigns Tank01_TempSV to D4000. The
   PDF's own table and captured API assign it to D4020. D4000 belongs to
   Tank01_TempPV. The app gets the correct address from the API.
   It does not submit the example address or use that address to route writes.
2. PDF page 5 uses Tank01_HeaterOn in batch examples. That tag exists in neither
   catalog. The actual writable symbol is Tank01_HeaterRemote (M321). Do not send
   the example name or invent an automatic alias. The current app does not use it.
3. Swagger's generic request-field example says Tank1_AddWater. It is also absent
   from the captured catalog. It is an example string, not an exposed signal.
4. Swagger declares batch requests as `writes` and responses as `results` plus
   `count`. The PDF describes the request but does not specify the response
   shape. The production backend checks the documented response.
   Before this update, the mock client returned a legacy `writes` response.
   The update changes that response to the Swagger shape.
   The backend still accepts the legacy response for compatibility.
5. Swagger declares HTTP 422 for request validation. The PDF's error table omits
   it. The client now gives that status a specific request-validation message.
6. Swagger permits nullable data_type in TagInfo/TagWriteResponse, while the PDF
   lists the supported type names. Every captured tag has a supported non-null
   type. Untyped metadata is not guessed or made writable.

## Physical findings and unresolved aliases shared by both sources

These are not differences between the sources. Copying the API alone cannot
correct them.

The operator explicitly confirmed these physical findings:

- Physical Tank 13 has the door.
- Physical Tank 12 has no door.
- Both commands and both feedback bits refer to Tank 13.

| Physical Tank 13 function | API/PDF name | Address |
| --- | --- | --- |
| Open | Tank12_DoorOpenRemote | M310 |
| Close | Tank12_DoorCloseRemote | M311 |
| Opened feedback | Tank12_DoorOpened | D1116.4 |
| Closed feedback | Tank12_DoorClosed | D1116.5 |

The PDF page 17 and saved API both contain these Tank12 names. Neither contains
a Tank13_Door tag. The source/API names remain intact. This operator-observed
physical correction covers only these four door tags, not every Tank12 signal.
Changing the physical tank labels requires a supplier naming correction or a
separately specified display alias. See the [field evidence](signal-test-plan.md#physical-tank-13-door-uses-tank12-api-names).

Both sources also contain these five shared-address groups:

| Address | Signal names sharing it |
| --- | --- |
| D1002.8 | Tank01_FillWaterStatus, Tank02_AirAgitationStatus |
| D1012.8 | Tank03_FillWaterStatus, Tank04_AirAgitationStatus |
| D1022.8 | Tank05_FillWaterStatus, Tank06_AirAgitationStatus |
| D1036 | Tank08_WaterFlow, Tank09_WaterFlow |
| L220 | Tank03_FillWaterAuto, Tank05_FillWaterAuto |

The audit did not infer address replacements or feedback polarity.
The source documents do not supply operating prerequisites, pulse/reset rules
or a complete table of command and feedback transitions.
HTTP 200/written=true acknowledges the write. It does not prove physical completion.
Catalog agreement does not resolve the earlier device failures.

## Software alignment

Production signal names, addresses, types, permissions and multipliers already
come from live `/tags/list`. The app does not use the offline capture as a runtime fallback.
The PDF-derived mock fixture remains a validation fixture, including optional
limits. It is not a substitute for the supplier's current metadata.

This update makes these changes:

- The mock batch response uses Swagger's results/count shape.
- The client handles HTTP 422.
- The UI labels unpublished numeric limits as unavailable.

It preserves finite-number/type checks, supplied-limit checks, live metadata
refresh and write authorization/confirmation guards. It does not restore
missing bounds from the PDF or interpret an omitted bound as permission to
write any value. This API capture does not support a change to any signal name,
address or permission.

The raw read timestamp was 2026-10-23T20:04:32.831352. Against the client at
capture, this is about 46.2 seconds old before the existing temporary clock
correction. The value includes polling/transport delay and is not a direct
measurement of PLC clock error. The supplier timestamp has no timezone.
This audit kept the previously confirmed Hong Kong interpretation and the
existing 44-second temporary correction. Clock concerns remain separate from
catalog identity.

## Software verification

Affected client, catalog, type/limit, API-safety, Bool-control and new UI/contract
checks passed **192 tests in 37.66 seconds**. A follow-up runtime-catalog test
verifies that saved API metadata wins over PDF limits without a guessed fallback.
That contract group plus parallel-backend checks passed **39 tests in 2.71 seconds**.
The groups overlap. Final source-provenance, catalog-contract, client and UI
checks passed **20 tests in 10.08 seconds** after live confirmation was recorded.
The audit did not repeat the complete earlier suite for these small changes
to response formats, error messages and displays.

The audit did not enable write mode or send a production POST request.
The live check used only the four GET endpoints in the capture manifest.
Publishing these audit notes requires no additional line connection.
