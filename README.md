# Anodizing PLC Communication & Signal Test Console

An engineering console for qualifying the supplier REST API and recording command/feedback evidence before AGV or robot integration. It is **not** the production controller or a safety system. Real PLC testing remains pending until the supplier API is reachable and the line engineer authorizes field tests.

## Source and architecture

The only available catalog in this workspace was `docs/source/Tag_catalog.docx` (copied from `/home/europa/development/anodizing_line/Tag_catalog.docx`); `Tag_catalog(2).docx` was not present. `config/mock-tags.json` is a generated snapshot of its detailed 361-row table. Real mode always discovers metadata from `GET /api/v1/tags/list` at runtime. The browser communicates with this local FastAPI backend; only the backend sends `X-API-Key` to the supplier. No PLC register access is performed.

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

Open `http://localhost:8080`. For mock mode, leave `PLC_MOCK_MODE=true`; no hardware or API key is needed. For real mode set `PLC_MOCK_MODE=false`, the actual supplier `PLC_API_BASE_URL`, and `PLC_API_KEY` in `.env`, then restart the backend. The source manual's `D4000` example conflicts with its detailed `Tank01_TempSV` row (`D4020`); confirm the live `/tags/list` address with the supplier before acting.

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

The supplied catalog contains seven Float tags, all read-only. The application supports Float validation in the reusable write layer, but a physical writable Float test is unavailable until the supplier exposes one as `W` in `/tags/list`.

## Verification

Run `pytest -q`. A mock-only failure can be injected through `POST /api/mock/fault` from loopback; the next read returns a mock communication error. This endpoint is absent in real mode. See [signal-test-plan.md](docs/signal-test-plan.md) for the commissioning sequence, [user-guide.md](docs/user-guide.md) for UI use, and [mock-verification-report.md](docs/mock-verification-report.md) for observed mock evidence.
