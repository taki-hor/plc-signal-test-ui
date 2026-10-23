# Supplier reference documents

Current static authority: [HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf](HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf), Project PD-03726, Model KAL-1600-SG, dated 29-SEP-2026, Version 1.0. This is a byte-for-byte copy of `docs/HKPU PLC_API_User_Manual (PD-03726).pdf` supplied in the development workspace.

`Tag_catalog.docx` is superseded and retained only as a historical reference. It must not override the current PDF or the live `/api/v1/tags/list` metadata. The live supplier list remains runtime authority in REAL MODE.

SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual. No address corrections have been inferred.

## Saved Swagger and catalog evidence

The initial audit used local historical captures at the user's request. After
reconnection, a GET-only recheck at 20:05:19 Hong Kong time on 23 October 2026
confirmed the live schema and all 362 tags match those captures. The original
source files are preserved; live provenance is recorded in the manifest. The
source records are:

- [supplier-openapi-2026-10-23.json](supplier-openapi-2026-10-23.json): saved Swagger schema.
- [supplier-tags-2026-10-23.json](supplier-tags-2026-10-23.json): full saved 362-tag response.
- [supplier-api-capture-2026-10-23.json](supplier-api-capture-2026-10-23.json): provenance, recorded-file timestamps and SHA256 hashes.

See the [complete audit](../swagger-alignment-2026-10-23.md) and
[all 47 differing signal rows](../swagger-signal-differences-2026-10-23.csv).
The API limits are omitted, not explicit null or proof of no operating limits.
The mock tag fixture remains the PDF-based validation fixture. The mock batch
response follows the documented results/count schema. Production still fetches
current metadata from the live API and does not fall back to these captures.
No API key, bearer token or operating-value snapshot is included in this source
evidence. The supplier PDF and historical DOCX remain unchanged.
