# Anodizing PLC Communication & Signal Test Console

This engineering console tests the supplier REST API before AGV or robot integration.
It records command values and feedback evidence. It is not a production controller or a safety system.
See [verification-2026-10-22.md](docs/verification-2026-10-22.md) for the first live reads and supervised Tank 01 tests.
Confirm the target, command/reset procedure and operator readiness before each physical test.

## Source and architecture

Latest authoritative static supplier reference: **HKPU PLC_API_User_Manual**, Project **PD-03726**, Model **KAL-1600-SG**, dated **29-SEP-2026**, Version **1.0**. A copy is in [docs/source](docs/source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf). `Tag_catalog.docx` is retained there as a superseded historical reference.

The [PDF/Swagger alignment audit](docs/swagger-alignment-2026-10-23.md) compares
all 362 PDF rows with the saved supplier schema and catalog, with every differing
signal in a [CSV](docs/swagger-signal-differences-2026-10-23.csv). It records the
39 unpublished numeric limit pairs, eight spacing-only descriptions, stale
examples and shared physical/address issues. A fresh GET-only comparison at
20:05:19 Hong Kong time on 23 October 2026 confirmed the retained schema/catalog
still match the live server. These files are evidence, not a runtime fallback. The Tank12 door naming error also exists in
the captured API and is not corrected by renaming transport tags.

`config/mock-tags.json` contains a development snapshot with **362 tags, 141 writable and 221 read-only**.
The supported types are **Bool, Word, SignedWord and Float**.
REAL MODE uses live `GET /api/v1/tags/list` metadata for names, addresses, types, permissions, multipliers, descriptions and engineering limits.
The console gets tag counts from that metadata. Static addresses cannot route or authorize real writes.

The browser sends requests to the local FastAPI backend. Only the backend sends `X-API-Key` to the supplier.
The console does not access PLC registers directly.

```
Browser HTML/CSS/JS → local FastAPI backend → supplier PLC REST API → Wi-Fi → PLC
```

## Install and run

Requires Python 3.11 or newer.

Run the backend and frontend together:

```bash
./start
```

The launcher creates `.venv`, installs dependencies on first run or when
`requirements.txt` changes, and creates `.env` from `.env.example` if missing.
It preserves existing configuration. Open `http://127.0.0.1:8080`. Press Ctrl+C
to stop. For the remote PC, set `PLC_API_BASE_URL=http://192.168.1.12:8000`,
`PLC_API_KEY`, and `PLC_MOCK_MODE=false` in `.env`, then restart `./start`.

For manual setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn server.app:app --host 127.0.0.1 --port 8080
```

Open `http://localhost:8080`. For mock mode, leave `PLC_MOCK_MODE=true`. No hardware or API key is needed. For real mode set `PLC_MOCK_MODE=false`, the actual supplier `PLC_API_BASE_URL`, and `PLC_API_KEY` in `.env`, then restart the backend. The manual's `Tank01_TempSV=D4000` API example differs from its detailed table (`D4020`). Record the live `/tags/list` metadata and refer discrepancies to the supplier.

The supplier API defaults to `PLC_API_HOST=127.0.0.1`, `PLC_API_PORT=8000`. To allow another computer on PLC Wi-Fi to reach it, the supplier's machine must listen on an accessible interface. The manual gives this PowerShell example:

```powershell
$env:PLC_API_HOST = "0.0.0.0"
$env:PLC_API_PORT = "8080"
python plc_api.py
```

`8080` is an example supplier port, separate from this console's port. Obtain the actual API host IP, port and key from the supplier, then configure:

```dotenv
PLC_API_BASE_URL=http://<supplier-api-ip>:<port>
PLC_API_KEY=<key>
PLC_MOCK_MODE=false
```

The command `uvicorn server.app:app --host 0.0.0.0 --port 8080` permits LAN access for monitoring.
Write and test endpoints accept loopback clients only.
Use the browser on the backend host for writes. Alternatively, use a local SSH tunnel.

From the engineer laptop, start `ssh -L 8080:127.0.0.1:8080 user@backend-host`.
Then open `http://localhost:8080`.
Restrict the backend host and `.env` to authorized engineers.
The local UI has no user accounts or TLS. Use a trusted workstation and tunnel.

## Configuration

| Variable | Meaning |
| --- | --- |
| `PLC_API_BASE_URL` | Supplier API origin, e.g. `http://192.168.x.x:8000` |
| `PLC_API_KEY` | Supplier credential. Backend only |
| `PLC_REQUEST_TIMEOUT` | HTTP timeout seconds |
| `PLC_UI_POLL_INTERVAL_MS` | Browser poll interval. Minimum 250 ms |
| `PLC_STALE_AFTER_MS` | Maximum accepted supplier data age |
| `PLC_TIMESTAMP_TIMEZONE` | Confirmed supplier timezone for timestamps without an offset, e.g. `Asia/Hong_Kong`. Blank rejects them |
| `PLC_TIMESTAMP_OFFSET_SECONDS` | Temporary signed whole seconds added for freshness and event-time comparison. Default `0` |
| `PLC_MOCK_MODE` | `true` for the generated mock catalog |

`.env` is ignored by Git. Supplier errors are redacted before logs or browser responses. Logs are written to ignored `logs/events.jsonl` and kept in a bounded in-memory view for export. The latest 10,000 persisted entries are restored into the export view after restart.

## Operating modes and write safety

Each page load starts in **READ-ONLY MODE**. A refresh discards the browser's write token.
A backend restart invalidates all tokens. Each token expires after 30 minutes.
Select **Enable write test mode** beside **Refresh now** to permit writes.
The compact badge distinguishes application authorization from PLC Remote mode.

Each manual single or batch write opens a confirmation dialog. The batch endpoint also requires the exact confirmation text.
Before dispatch, the backend checks live metadata, type, limits, fresh data and `Remote=1`.
It checks the mode token again after network validation, including before configured reset writes.
The UI shows `Local` and `Remote` from the live catalog.
The console records HTTP acceptance separately from physical feedback.

A short command lock protects actual writes. Independent feedback observations can run in parallel.
Conflict checks protect the same command, aliases, opposing doors and shared feedback resources.
Disabling write mode blocks commands that the backend has not dispatched.
It cannot recall a submitted command.

The web app does not infer automatic resets. A configured test can include an explicit `reset_command`. No tests or writes run on page load. Emergency stop remains outside this application. A catalog `W` marker alone is not proof of safe field behavior. The line engineer must confirm each physical test area and equipment state.

Signal browser groups all matching cards by the manual’s Alarms, System and tank sections, with counts and complete descriptions. Search and group/type/permission filters reach every tag. There is no first-120 cutoff.

## 0/1 command checklist

The checklist lists every live writable Bool tag (currently 102), with search,
tank/group filters, **Send 1…** and **Send 0…**. Each send uses one confirmation
popup. A timer runs from Confirm Send 1 to fresh configured completion feedback.
API response time and later 0 readback are shown separately. New attempt leaves
the timer at zero. A two-option end-state control offers manual 0 or Hold at 1. Manual-based Hold hints remain marked unconfirmed. Only the tested Tank 01 rule marks Manual 0 as confirmed.
For non-door Hold, the confirmed choice becomes a visible Keep at 1 record after
accepted 1 and verified later readback, without an additional write. Detailed logs update automatically. Enter physical observations in Notes. **API CYCLE RECORDED** describes command evidence. Only your explicit human result marks a test complete. Nothing automatically clears or retries.
History stays in this browser for the selected API and mode and exports to
CSV/JSON. Refresh always starts with write mode off. Numeric setpoints and all
141 writable tags remain available on the Setpoints & batch page (`#/write`). See the
[user guide](docs/user-guide.md#01-command-checklist) for the procedure and limits. The
[hold/reset findings](docs/signal-test-plan.md#command-hold-and-reset-findings)
distinguish manual descriptions, the tested Tank 01 procedure and unspecified
RemoteStart behavior.

If the API catalogue is unavailable at startup, the UI retries loading it after
communication returns. The Commands page explains loading, unavailable, empty
catalogue and empty-filter states instead of leaving a blank list. Selected
commands show evidence-qualified Hold/Reset guidance. Every write remains manual.

## Command/feedback tests

A feedback wait does not lock unrelated commands. Use **Test run** to select an ongoing or finished run. Each run keeps its own timeout, request timer, API result and human result. Pending commands stay visible. An explicit same-command Send 0 interrupts its observer and does not infer completion. Actual dispatches remain serialized, with fresh Remote data and one confirmation per write.

All 50 bundled feedback tests default to a **15-second observation window**. The Feedback tests wait-limit field accepts 1–300 whole seconds for the next run. The chosen limit appears in the confirmation and audit. A timeout leaves the command state for manual review and clearing.

Feedback uses the Manual 0/1 layout: a searchable pair list and tank/result dropdowns on the left, with selected details and results on the right. The shared Command bits bar is available on all three write pages. The **Your result** dropdown saves **Not checked**, **Pass**, or **Fail** immediately in this browser. API feedback never sets that choice. Manual-based Hold suggestions select the initial Feedback mode. Doors and commands without a clear suggestion start on Manual 0. The confirmation still shows the source and permits a non-door override.

`config/test-cases.json` includes configured door open/close pairs and 36 manual-derived non-door pairs labelled **MAPPING UNDER TEST**. Their `requires_confirmation` flags remain set. The UI permits an explicitly confirmed supervised observation of these proposed pairs. A matching transition returns **OBSERVED**, not PASS. It does not certify the mapping or hold/reset behavior. A configured test checks baseline feedback again before dispatch. It writes one engineering value. PASS requires a newer poll timestamp at or after command acceptance. Poll timestamps use the configured timezone and temporary clock correction. Cyclic poll_count values are not used as a sequence. Each feedback read is bounded by the remaining test deadline, and late feedback cannot pass. Revoked write mode or leaving Remote mode stops verification. No reset is inferred. Results and communication records can be exported as CSV or JSON.

The snapshot contains eight Float tags, all read-only. A physical writable Float test is unavailable until the supplier exposes one as `W` in `/tags/list`. SignedWord represents a signed 16-bit register. Writes accept negative engineering values within live limits. The supplier performs scaling: `Tank01_TempAdj=-5.0` with multiplier `0.1` sends `-5.0`, and `Tank01_TempSV=25.0` sends `25.0`.


The write sidebar separates Feedback tests, Manual 0/1, and Setpoints & batch. Each active command row has its own confirmed **Send 0…** action. It also works after reload without starting a test.

Feedback keeps selected-pair details and **Active test & result** in the right
workspace. Reviewing a pair sends nothing. **Run selected test** opens one write
confirmation. Saved human Pass/Fail marks appear on each row and remain separate
from API outcomes. All 50 pairs use tags listed in the supplier tables. Those
sources do not define the command-to-feedback operating rules. The 14 Local
pairs and 36 mappings under test are application classifications, not supplier
sign-off. Operator Pass records the physical check reported by the tester.
**Send 0…** remains explicit. No automatic reset is sent. See the [user guide](docs/user-guide.md).

## Catalog compatibility and diagnostics

The latest changes are recorded in [signal-test-plan.md](docs/signal-test-plan.md). REAL MODE compares live metadata with the bundled baseline and displays/logs **CATALOG DIFFERENCE** warnings, including added/missing tags, count differences and changed metadata. It uses the live metadata unchanged. Warnings alone do not block monitoring or writes. Existing write protections still apply.

**SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.** Both tags are retained exactly as supplied. Duplicate addresses are warnings. Duplicate tag names remain errors. The historical duplicate `L220` for Tank03/Tank05 fill-water-auto also remains in the latest table.

## First real API smoke test: read only

```bash
export PLC_MOCK_MODE=false
export PLC_API_BASE_URL='http://<supplier-ip>:<port>'
export PLC_API_KEY='<key>'
uvicorn server.app:app --host 127.0.0.1 --port 8080
```

From another terminal on the backend host:

```bash
curl --fail-with-body http://127.0.0.1:8080/api/tags
curl --fail-with-body http://127.0.0.1:8080/api/signals
curl --fail-with-body http://127.0.0.1:8080/api/status
```

If the supplier omits a timestamp offset, confirm its clock timezone first.
Then set `PLC_TIMESTAMP_TIMEZONE=Asia/Hong_Kong` when that timezone applies.
The console honors existing timezone offsets. Timezone configuration does not correct clock drift.

For a measured supplier clock delay of 44 seconds, set `PLC_TIMESTAMP_OFFSET_SECONDS=44` in `.env`.
Restart `./start` after the change. The UI shows the correction separately.
The raw supplier timestamps and 3-second stale-data limit remain unchanged.
An incorrect offset can make data stale or apparently in the future.
Measure the delay again if either clock changes.

After clock synchronization, reset the offset to `0`. Then restart the backend.

`/api/tags` must parse all live supplier tags, including SignedWord, before any write test. Confirm API connected, Remote/Local state, timezone-aware timestamp and freshness, live counts, no parsing errors, and catalog warnings with the supplier. Keep the initial validation read only. Enable write test mode only after the engineer reviews these results and authorizes the physical test.

## Verification

Run `pytest -q` in the activated virtual environment.
Browser tests use an isolated loopback fake API. They run when Firefox and geckodriver are available.
Otherwise, pytest reports them as skipped. These tests do not use the line API.
If the shell inherits unrelated ROS Python plugins, use `env -u PYTHONPATH pytest -q`.

The dated verification notes record their own test results and field conditions.
See [22 October verification](docs/verification-2026-10-22.md) for the first live reads and bug fixes.
See [23 October verification](docs/verification-2026-10-23.md#feature-branch-push-preparation) for its 598-test evidence and stopped field session.
See [26 October results](docs/swagger-second-run-2026-10-26.txt) for the completed direct 141-tag run and later API retest.

For mock fault injection, send `POST /api/mock/fault` from loopback.
The next mock read returns a communication error. This endpoint returns 404 in real mode.
See the [test plan](docs/signal-test-plan.md), [user guide](docs/user-guide.md) and [mock report](docs/mock-verification-report.md) for procedures and evidence.

The Bool engineering-value control uses explicit **0 / 1** choices. Numeric
setpoints keep numeric input. Every write still needs Review and confirmation.
Value and batch histories now support the same autosaved human result vocabulary.
The documented supplier batch response uses `results` and `count`. The console
validates every accepted item. Live field-check evidence and remaining PLC
questions are recorded in the latest verification notes.
