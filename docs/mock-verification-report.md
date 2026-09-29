# Mock verification report — 2026-09-29

**REAL PLC TEST: PENDING.** No supplier API or physical PLC was connected. The results below qualify only this application's mock behavior.

## Source and catalog

The requested `Tag_catalog(2).docx` was not available in the searched workspace paths. The bundled `docs/source/Tag_catalog.docx` is a byte-for-byte copy of `/home/europa/development/anodizing_line/Tag_catalog.docx` (SHA-256 `11d283a19bfc9e43c60b8f876e0b3a89a089690158364c494fa23ccf7c511b87`). Its detailed table contains 361 unique tag names, including 141 `W` tags and seven Float tags; all Float tags are `R`.

## Automated checks

`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q` → **28 passed**. This covers metadata parsing, read-only/Bool/Word/Float/limit validation, supplier HTTP error mapping, unchanged engineering units, API-key redaction, mock behavior, command-feedback PASS, TIMEOUT, FAIL, existing-feedback block, communication failure, and fail-closed null-tag freshness. JavaScript module syntax checks and Python compilation also passed.

## Running mock API observations

The FastAPI app started with `PLC_MOCK_MODE=true` on loopback. Observed through HTTP requests:

| Check | Observed |
| --- | --- |
| Startup | `MOCK`, write mode `OFF` |
| Metadata | 361 tags, 141 writable |
| Poll | `tags_ok=361`, `tags_failed=0`, `Remote=1`, fresh ISO timestamp |
| Write while mode off | HTTP 403 |
| Read-only write | HTTP 400, blocked |
| Invalid Bool and over-limit Word | HTTP 400, blocked |
| Word engineering write | 25.0 transmitted and returned as 25.0 |
| Batch without confirmation | HTTP 400 |
| Confirmed batch | HTTP 200; readback 26.0 |
| Tank 01 door open command/feedback | PASS, 502 ms after write acceptance |
| Tank 03 door open with 10 s simulated delay | TIMEOUT, 5001 ms |
| Injected mock read failure | HTTP 502; status reported disconnected |
| CSV and JSON exports | HTTP 200 for communication and test categories |
| Disabled token | HTTP 403 on later write |

A browser session displayed MOCK MODE, READ-ONLY MODE, CONNECTED, REMOTE, FRESH, and `361 / 0`; search narrowed 361 signals to four door matches, tank selection displayed grouped signals, and a confirmed mock setpoint write showed the address/current/new values. Reload restored READ-ONLY MODE. An injected mock read failure displayed DISCONNECTED and the communication error in the UI. An old write token was rejected with HTTP 403 after backend restart.

## Security and automatic-command review

With a canary `PLC_API_KEY`, 13 HTML/CSS/JS/API/export responses contained no canary. The frontend files and `logs/events.jsonl` contained no canary. The key is sent only in the backend supplier client `X-API-Key` header. Write-related supplier calls occur only inside the guarded `/api/write`, `/api/write/batch`, and `/api/test/run` paths after explicit user actions. Startup loads metadata and a read snapshot; periodic browser work performs reads only. No configured test has `reset_command`, and no emergency-stop command is exposed as an ordinary action.

## Supplier and engineer confirmations required

1. Provide or confirm the intended `Tag_catalog(2).docx` revision and compare it with the bundled source before field work.
2. Resolve the `Tank01_TempSV` address mismatch: API example `D4000`, detailed table `D4020`.
3. Confirm the repeated `L220` address for `Tank03_FillWaterAuto` and `Tank05_FillWaterAuto`.
4. Confirm `Remote`/`Local` mode behavior and whether the mode signal alone is sufficient to permit each command.
5. Confirm command semantics, especially pulse/latched/reset behavior, physical interlocks and test-area procedure.
6. Confirm the 36 staged name-matched command/status associations before enabling those test cases.
7. Confirm alarm polarity and which values represent active alarms.
8. Supply a writable Float tag if a physical Float write qualification is required; the current catalog has none.
