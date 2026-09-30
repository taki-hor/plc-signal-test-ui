# Anodizing PLC Communication & Signal Test Console

An engineering console for qualifying the supplier REST API and recording command/feedback evidence before AGV or robot integration. It is **not** the production controller or a safety system. Real PLC testing remains pending until the supplier API is reachable and the line engineer authorizes field tests.

## Source and architecture

Latest authoritative static supplier reference: **HKPU PLC_API_User_Manual**, Project **PD-03726**, Model **KAL-1600-SG**, dated **29-SEP-2026**, Version **1.0**. A copy is in [docs/source](docs/source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf). `Tag_catalog.docx` is retained there as a superseded historical reference.

`config/mock-tags.json` is a commissioning/development snapshot: **362 tags, 141 writable, 221 read-only**. Supported data types are **Bool, Word, SignedWord, Float**. REAL MODE always uses `GET /api/v1/tags/list` as runtime authority for names, addresses, types, permissions, multipliers, descriptions and engineering limits. Counts are obtained dynamically. Static addresses are never used to route or authorize real writes. The browser communicates with this local FastAPI backend; only the backend sends `X-API-Key` to the supplier. No PLC register access is performed.

```
Browser HTML/CSS/JS → local FastAPI backend → supplier PLC REST API → Wi-Fi → PLC
```

## Install and run

Requires Python 3.11 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn server.app:app --host 127.0.0.1 --port 8080
```

Open `http://localhost:8080`. For mock mode, leave `PLC_MOCK_MODE=true`; no hardware or API key is needed. For real mode set `PLC_MOCK_MODE=false`, the actual supplier `PLC_API_BASE_URL`, and `PLC_API_KEY` in `.env`, then restart the backend. The manual's `Tank01_TempSV=D4000` API example differs from its detailed table (`D4020`); record the live `/tags/list` metadata and refer discrepancies to the supplier.

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

The user-requested command `uvicorn server.app:app --host 0.0.0.0 --port 8080` permits LAN access to monitoring. Write and test endpoints accept only loopback clients, so use the browser on the backend host or a local SSH tunnel for writes. For example, from the engineer laptop: `ssh -L 8080:127.0.0.1:8080 user@backend-host`, then open `http://localhost:8080`. Keep the backend host and `.env` restricted to authorized engineers. The local UI has no user accounts or TLS; use a trusted workstation and tunnel.

## Configuration

| Variable | Meaning |
| --- | --- |
| `PLC_API_BASE_URL` | Supplier API origin, e.g. `http://192.168.x.x:8000` |
| `PLC_API_KEY` | Supplier credential; backend only |
| `PLC_REQUEST_TIMEOUT` | HTTP timeout seconds |
| `PLC_UI_POLL_INTERVAL_MS` | Browser poll interval; minimum 250 ms |
| `PLC_STALE_AFTER_MS` | Maximum accepted supplier data age |
| `PLC_MOCK_MODE` | `true` for the generated mock catalog |

`.env` is ignored by Git. Supplier errors are redacted before logs or browser responses. Logs are written to ignored `logs/events.jsonl` and kept in a bounded in-memory view for export. The latest 10,000 persisted entries are restored into the export view after restart.

## Operating modes and write safety

The page starts in **READ-ONLY MODE** on every load. Refresh loses the in-memory write token; backend restart invalidates all tokens. To write, use **Enable write test mode**. A token expires after 30 minutes. Every manual single or batch write opens a confirmation dialog. The batch endpoint also requires the exact confirmation text. Writes check current `/tags/list` metadata, type/limits, a fresh `/tags/read` snapshot, and `Remote=1` before the supplier API is called. `Local` and `Remote` are displayed from catalog tags. Supplier HTTP write acceptance is recorded separately from physical feedback.

The console does not pulse, clear, toggle, or reset commands unless an explicit `reset_command` is placed in a configured test case. No tests or writes run on page load. Emergency stop remains outside this application. A catalog `W` marker alone is not proof of safe field behavior; the line engineer must confirm each physical test area and equipment state.

## Command/feedback tests

`config/test-cases.json` includes door open/close pairs whose names and descriptions explicitly identify command and actual door position. Other plausible pairs are visible as **NEEDS CONFIRMATION** and blocked until a supplier/engineer reviews their semantics and sets `requires_confirmation` to `false`. A configured test checks baseline feedback, writes one engineering value, then polls until feedback changes to the expected value or timeout. No reset is inferred. Results and communication records can be exported as CSV or JSON.

The snapshot contains eight Float tags, all read-only. A physical writable Float test is unavailable until the supplier exposes one as `W` in `/tags/list`. SignedWord represents a signed 16-bit register; writes accept negative engineering values within live limits. The supplier performs scaling: `Tank01_TempAdj=-5.0` with multiplier `0.1` sends `-5.0`, and `Tank01_TempSV=25.0` sends `25.0`.

## Catalog compatibility and diagnostics

The latest changes are recorded in [signal-test-plan.md](docs/signal-test-plan.md). REAL MODE compares live metadata with the bundled baseline and displays/logs **CATALOG DIFFERENCE** warnings, including added/missing tags, count differences and changed metadata. It uses the live metadata unchanged; warnings alone do not block monitoring or writes. Existing write protections still apply.

**SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.** Both tags are retained exactly as supplied. Duplicate addresses are warnings; duplicate tag names remain errors. The historical duplicate `L220` for Tank03/Tank05 fill-water-auto also remains in the latest table.

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

`/api/tags` must parse all live supplier tags, including SignedWord, before any write test. Confirm API connected, Remote/Local state, timezone-aware timestamp and freshness, live counts, no parsing errors, and catalog warnings with the supplier. Keep the initial validation read only. Enable write test mode only after the engineer reviews these results and authorizes the physical test.

## Verification

Run `pytest -q` in the activated virtual environment. If the shell inherits ROS's unrelated Python plugins, use `env -u PYTHONPATH pytest -q`. A mock-only failure can be injected through `POST /api/mock/fault` from loopback; the next read returns a mock communication error. This endpoint returns 404 in real mode. See [signal-test-plan.md](docs/signal-test-plan.md) for the commissioning sequence, [user-guide.md](docs/user-guide.md) for UI use, and [mock-verification-report.md](docs/mock-verification-report.md) for observed mock evidence.
