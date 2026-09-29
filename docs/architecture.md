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

The initial mock catalog was derived from the only available `Tag_catalog.docx`. It has 361 tags and 141 `W` tags. Real mode does not use that snapshot for write authorization. The detailed table's `Tank01_TempSV=D4020` conflicts with an API example showing `D4000`; the live supplier list must settle it. The source also repeats address `L220` for Tank03 and Tank05 fill-water-auto entries; no address correction was guessed.

Safety functions, emergency stop, PLC interlocks, and physical commissioning authority remain with the machine and supplier. There is no AGV or robot code here.
