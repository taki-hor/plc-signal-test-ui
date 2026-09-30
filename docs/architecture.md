# Architecture

```
Browser UI
   │ same-origin local API
   ▼
Central Test Backend (FastAPI)
   │ X-API-Key, HTTP only
   ▼
Supplier PLC REST API
   │ Wi-Fi / supplier-owned PLC connection
   ▼
Anodizing PLC
```

`server/plc_client.py` owns the supplier transport contract: `list_tags`, `read_signals`, `read_signal`, `write_signal`, `write_batch`, and `wait_for_signal`. It transmits engineering values unchanged; the supplier performs multiplier conversion. `MockPLCClient` implements the same methods with a generated catalog snapshot. `signal_service.py` parses metadata, checks writable type and limits, requires a fresh timezone-aware supplier timestamp and `Remote=1`, and logs every request. `test_runner.py` records baseline feedback, accepted write, feedback polling and result. `log_service.py` writes redacted JSONL and exports CSV/JSON. `app.py` serves the one-page UI and local endpoints.

The browser gets no supplier credential. The API key is set only in the backend HTTP header and is redacted from logs/errors. The backend serves same-origin static files, does not enable CORS, and accepts write/test/mode POSTs only from a loopback client. Write tokens exist only in memory and expire. A browser refresh discards its token; a backend restart clears the token map.

Supplier `GET /api/v1/tags/read` is one polling snapshot, with flat tag values and `timestamp`, `tags_ok`, `tags_failed`. Connection health is shown separately from supplier data freshness. A successful HTTP call cannot make stale PLC data healthy. Missing or timezone-free timestamps fail closed for writes. The console does not access PLC addresses directly; addresses are display metadata.

The authoritative static source is [HKPU PLC_API_User_Manual, PD-03726, KAL-1600-SG, 29-SEP-2026, v1.0](source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf). The mock snapshot contains 362 tags: 141 `W` and 221 `R`. The old `Tag_catalog.docx` is superseded and retained for history. This count is tested only for the static snapshot; production counts are dynamic.

`Tag.parse` accepts Bool, Word, SignedWord and Float. SignedWord is a signed 16-bit register; Float is an IEEE-754 REAL using two D registers. Numeric writes are finite engineering values checked against supplier limits; Bool accepts only 0/1. Multipliers and optional limits must be finite, multipliers positive, and low/high ordered. No local conversion to raw PLC registers occurs. Negative SignedWord values survive mock write/store/read unchanged.

REAL MODE uses every live `/tags/list` field as authority and refreshes it before each write. `catalog_diagnostics.py` compares that metadata against the bundled baseline for advisory warnings only; it never replaces live addresses, permissions, limits or other metadata. Count, added/missing tag and field differences are logged with expected/live metadata and shown in the health section through `/api/status`. Repeated identical diagnostics are not logged again. No catalog count is hard-coded in the UI.

Tag identity is `tag_name`; duplicate tag names are rejected. Duplicate device addresses are tolerated and warned. **SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.** The source also repeats `L220` for Tank03/Tank05 fill-water-auto and shows `Tank01_TempSV=D4000` in an API example versus `D4020` in the detailed table. No corrections are guessed; report live discrepancies for supplier review.

The REST contract remains `GET /api/v1/tags/list`, `GET /api/v1/tags/read`, `POST /api/v1/tags/write`, `POST /api/v1/tags/write/batch`, authenticated with backend-only `X-API-Key`. The supplier service defaults to `127.0.0.1:8000`; its manual's `0.0.0.0:8080` launch is an example accessible binding. Configure this console with the actual supplier IP, port and key. There is no direct register communication or MC Protocol in the console.

Safety functions, emergency stop, PLC interlocks, and physical commissioning authority remain with the machine and supplier. There is no AGV or robot code here.
