# Signal test plan

1. Confirm the backend host can reach the supplier REST API over the intended Wi-Fi path. Record host, URL, date, and network result.
2. Confirm `X-API-Key` authentication with a read-only endpoint. Record 200 or the documented 401/503 response.
3. Load `/tags/list`; export/compare the live metadata against the supplied catalog, including addresses, permissions, limits and multipliers. Resolve the `Tank01_TempSV` address conflict and duplicate `L220` address with the supplier.
4. Verify read-only signals using the single `/tags/read` snapshot. Record timestamp, age, `tags_ok`, `tags_failed`, and any null values. Do not treat HTTP 200 as proof of a fresh PLC poll.
5. Verify `Remote=1` with the supplier and machine operator. `Local`/`Remote` behavior beyond the documented descriptions needs confirmation.
6. Confirm the physical area and equipment with the responsible engineer. Enable write test mode on the local workstation. It expires after 30 minutes and a refresh disables the browser's ability to write.
7. Test permitted writable setpoints within catalog limits, beginning with non-motion values chosen by the engineer. Record entered engineering units, live address, supplier response, and observed readback. No scaling is applied in this app.
8. Run one reviewed command/feedback test at a time. Confirm initial feedback differs from the expected value. The runner records write acceptance, each feedback read, PASS/FAIL/TIMEOUT/BLOCKED/COMMUNICATION ERROR, and elapsed time. Confirm whether commands are latched, momentary, or need explicit clearing before adding reset behavior.
9. Export communication and test logs as CSV/JSON. Save the persistent JSONL log with the test record if required.
10. Review failed and uncertain mappings with the PLC supplier. Do not promote a name-based mapping to confirmed field behavior without observation.

## Initial mappings

Door open/close command → actual door opened/closed feedback pairs are configured for tanks where both catalog tags exist. The remaining filter, heater, ultrasonic, swing, rectifier, spray and fill-water name matches are included as blocked candidates. Their command semantics and physical feedback association require supplier confirmation. Alarm polarity is undocumented in the catalog, so the UI displays raw Bool values without assigning severity.

## Limits of mock evidence

Mock mode verifies application behavior and log output only. It does not prove Wi-Fi reachability, supplier authentication, PLC write acceptance, physical actuation, or safety behavior. The current catalog has no writable Float tag, so that field test is pending a supplier catalog update.
