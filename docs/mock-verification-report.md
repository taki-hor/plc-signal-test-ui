# Mock verification report — 2026-09-30

**REAL PLC TEST: PENDING.** No real supplier API or physical PLC was reached. This report verifies the console's mock behavior and compatibility with the supplier document.

## Delivery state and changed files

Reviewed `main` base SHA: `2937199c463be244fed12425ac46e5c668161ef7`, matching remote main at the initial review. The compatibility update is delivered on `main`; Git history records its commit SHA. The supplied PDF and canonical source copy are included in the repository.

- Backend: `server/models.py`, `server/signal_service.py`, `server/app.py`, new `server/catalog_diagnostics.py`.
- Frontend: `frontend/index.html`, `frontend/js/controls.js`, `frontend/js/signals.js`, `frontend/js/dashboard.js`, `frontend/js/dom.js`.
- Catalog: `config/mock-tags.json`. `config/test-cases.json` was validated and needs no edits.
- Tests: `tests/test_validation.py`, `tests/test_signal_service.py`, `tests/test_plc_client.py`, `tests/test_test_runner.py`, new `tests/test_app_safety.py`.
- Documentation: `README.md`, `docs/architecture.md`, `docs/signal-test-plan.md`, `docs/user-guide.md`, this report, new `docs/source/README.md` and the supplier PDF copy below.

`server/plc_client.py` already preserves SignedWord engineering values without scaling and required no transport changes. The existing supplier PDF at `docs/HKPU PLC_API_User_Manual (PD-03726).pdf` was preserved.

## Source and static baseline

Authoritative static reference: HKPU PLC_API_User_Manual, Project PD-03726, Model KAL-1600-SG, dated 29-SEP-2026, Version 1.0. The supplied `docs/HKPU PLC_API_User_Manual (PD-03726).pdf` was copied byte-for-byte to [docs/source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf](source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf). Both copies have SHA-256 `a157cfc7165fa86ee23ea10fc7293b343b4a2e356c8f7a70b863876b4ad0f40e`. `Tag_catalog.docx` is retained as a superseded historical reference.

The updated mock snapshot contains **362 tags: 141 writable, 221 read-only**. Types: 277 Bool, 69 Word, eight SignedWord, eight Float. All Float tags are read-only. Programmatic extraction of the PDF's complete table verified every mock tag's name, address, type, permission, multiplier, description and low/high limits against all 362 supplier rows. Description continuation lines were joined with spaces; 52 additional descriptions were updated, chiefly engineering unit labels, beyond the changes listed below.

REAL MODE always uses the live `/api/v1/tags/list` metadata and dynamic counts. This static snapshot is used only for mock/development and advisory comparison. Live differences are displayed/logged without replacing live metadata or blocking operation merely because the catalog differs.

## Applied supplier catalog changes

| Change | Updated static snapshot |
| --- | --- |
| Eight TempAdj tags | Tank01/03/05/07/10/13/14/16 at D4010–D4017 respectively; SignedWord, W, multiplier 0.1, −999.0 to 999.9 |
| SwingSV limits | Tank03 D1008, Tank05 D1018, Tank10 D1100, Tank14 D1124; Word, W, multiplier 1.0, 5–120 CPM |
| Tank07_AmperePV | D1055, Word, R, multiplier 0.1 |
| Tank07_AmpereSV | D1362 replaces D1038; Word, W, multiplier 0.1 replaces 0.01, 0–200 A |
| Tank07_VoltagePV | D1054, Word, R, multiplier 0.1 replaces 0.01 |
| Tank16_Conductivity | Replaces Tank16_PH at D1142; Float, R, multiplier 1.0; Conductivity Meter Reading (MOhmCM) |
| Tank09_WaterFlow | Added at D1036; Word, R, multiplier 0.1; Tank09 Water Flow Meter Value (LPM) |

**SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.** Both addresses are retained. Duplicate addresses are advisory; duplicate tag names remain errors. Diagnostics also report the supplier's other shared addresses (D1002.8, D1012.8, D1022.8, L220); no address changes were inferred.

## Automated verification

Run from the activated virtual environment:

```bash
env -u PYTHONPATH pytest -q
```

Fresh full-suite result: **92 passed in 5.34s**, exit status 0. `git diff --check` also passed.

The shell's inherited ROS `PYTHONPATH` causes ordinary `pytest -q` to load an unrelated `launch_testing` plugin and fail before collection on a missing `yaml` import. Removing that inherited path runs the full repository suite; no tests are excluded.

Coverage includes:

- SignedWord parser and unchanged negative engineering values; accepted −999.0, −5.0, 0, 25.0, 999.9; rejected −999.1, 1000.0, NaN, ±Infinity, strings and bools.
- Finite metadata, positive multiplier, ordered limits and required identity/type/permission fields; Bool and supplier-limit validation.
- Exact snapshot counts and all requested catalog mappings/descriptions, obsolete Tank16_PH absence, SignedWord single/batch mock write/store/read.
- Exact supplier REST request bodies for TempSV=25.0 and TempAdj=−5.0, including batch; backend-only X-API-Key.
- All 50 configured test-case entries validated against the new catalog. Fourteen door cases remain configured; 36 uncertain candidates remain blocked with requires_confirmation=true. No reset_command is configured.
- Door open/close PASS for Tank01, Tank03, Tank05, Tank07, Tank10, Tank12 and Tank14; existing-feedback block, timeout, communication failure and supplier write rejection remain covered.
- Advisory comparison for every live metadata field, count differences, added/missing tags and duplicate addresses; live permissions remain authoritative. Duplicate tag names are rejected.
- Backend guard regressions: default mode off, loopback only, cross-origin rejection, expired/disabled token, fresh data, Remote=1, read-only tags, batch confirmation, no startup writes and credential redaction.

## Running mock UI and API observations

The app launched with `PLC_MOCK_MODE=true` on `127.0.0.1:8765`. Browser interaction and HTTP verification observed:

| Check | Observed |
| --- | --- |
| Startup | MOCK MODE, READ-ONLY MODE, CONNECTED, REMOTE, FRESH |
| Loaded signals | 362 / 362 signals; supplier poll counts 362 OK / 0 failed |
| Both type filters | Bool, Word, SignedWord, Float; SignedWord selected eight signals/rows |
| TempAdj advanced row and manual detail | Tank01_TempAdj, D4010, SignedWord, W, multiplier 0.1, −999.0 to 999.9 |
| Explicit manual confirmation | Signal, address, current and new value displayed before Confirm write |
| SignedWord mock write/readback | WRITE ACCEPTED; entered −5.0, response/readback −5.0; UI renders current −5 |
| Tank07_AmpereSV | D1362, Word, W, multiplier 0.1, 0.0–200.0 displayed |
| Tank16_Conductivity | Present at D1142, Float, R, multiplier 1.0 |
| Tank16_PH search | Showing 0 of 362 tags |
| Tank09_WaterFlow | Present at D1036, Word, R, multiplier 0.1 |
| D1036 duplicate | Displayed as SUPPLIER CONFIRMATION REQUIRED; startup and reads succeed |
| Tank01 door open/close in browser | PASS, actual feedback 1; 502/503 ms after acceptance |
| Other six tanks, open/close through mock HTTP API | All twelve cases PASS; 502–504 ms |
| Writes without mode | HTTP 403 |
| Read-only, below/above supplier limits | HTTP 400 |
| Browser reload | READ-ONLY MODE restored; Review write disabled |
| Browser errors | None observed |

The mock verification used a canary API key. HTML, metadata, poll, status and relevant API/log responses contained no canary. Test code separately verifies secret redaction and that monitoring does not issue writes. API transport and write safeguards retain the existing architecture.

## Field validation remains pending

Obtain the supplier API host IP, actual port and API key. The supplier service defaults to `127.0.0.1:8000`; its manual's PowerShell binding to `0.0.0.0:8080` is an example, not the assumed field port. README includes `.env` and read-only smoke commands.

Before enabling write test mode, the local `GET /api/tags` must successfully parse all live tags, including SignedWord; inspect `/api/signals` and `/api/status` for connection, Remote/Local status, data freshness, dynamic counts and parsing errors. Review catalog differences and the shared D1036 address with the supplier. Confirm physical interlocks, test-area readiness and command/pulse/reset semantics; uncertain candidates stay blocked. The manual's TempSV API example/table discrepancy and shared L220 also require supplier review. Mock results do not establish live communication, PLC actuation, or commissioning authority.
