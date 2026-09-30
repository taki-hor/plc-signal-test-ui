# Signal test plan

1. Confirm the backend host can reach the supplier REST API over the intended Wi-Fi path. Record host, URL, date, and network result.
2. Confirm `X-API-Key` authentication with a read-only endpoint. Record 200 or the documented 401/503 response.
3. Load the local `GET /api/tags`, which parses the supplier `/api/v1/tags/list`; export/compare live metadata against the 29-SEP-2026 PDF baseline, including all types (especially SignedWord), addresses, permissions, descriptions, limits and multipliers. Record the live count dynamically. Review displayed/logged CATALOG DIFFERENCE and duplicate-address warnings with the supplier. Resolve shared `D1036`, the `Tank01_TempSV` API-example/table discrepancy and shared `L220` with the supplier; never silently correct live metadata.
4. Verify read-only signals using the single `/tags/read` snapshot. Record timestamp, age, `tags_ok`, `tags_failed`, and any null values. Do not treat HTTP 200 as proof of a fresh PLC poll.
5. Verify `Remote=1` with the supplier and machine operator. `Local`/`Remote` behavior beyond the documented descriptions needs confirmation.
6. Confirm the physical area and equipment with the responsible engineer. Enable write test mode on the local workstation. It expires after 30 minutes and a refresh disables the browser's ability to write.
7. Test permitted writable setpoints within catalog limits, beginning with non-motion values chosen by the engineer. Record entered engineering units, live address, supplier response, and observed readback. No scaling is applied in this app.
8. Run one reviewed command/feedback test at a time. Confirm initial feedback differs from the expected value. The runner records write acceptance, each feedback read, PASS/FAIL/TIMEOUT/BLOCKED/COMMUNICATION ERROR, and elapsed time. Confirm whether commands are latched, momentary, or need explicit clearing before adding reset behavior.
9. Export communication and test logs as CSV/JSON. Save the persistent JSONL log with the test record if required.
10. Review failed and uncertain mappings with the PLC supplier. Do not promote a name-based mapping to confirmed field behavior without observation.

## Initial mappings

Door open/close command → actual door opened/closed feedback pairs are configured for tanks where both catalog tags exist. The remaining filter, heater, ultrasonic, swing, rectifier, spray and fill-water name matches are included as blocked candidates. Their command semantics and physical feedback association require supplier confirmation. Alarm polarity is undocumented in the catalog, so the UI displays raw Bool values without assigning severity.

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
