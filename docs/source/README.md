# Supplier reference documents

The current static reference is the supplier PDF:
[HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf](HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf).
Its identifiers are:

- Project: PD-03726.
- Model: KAL-1600-SG.
- Date: 29-SEP-2026.
- Version: 1.0.

This file is a byte-for-byte copy of `docs/HKPU PLC_API_User_Manual (PD-03726).pdf`
from the development workspace.

The current PDF replaces `Tag_catalog.docx`. The repository retains the DOCX
only as a historical reference. It must not override the current PDF or live
`/api/v1/tags/list` metadata. The live supplier list remains the runtime
reference in REAL MODE.

SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use
D1036 in the latest manual. We did not infer an address correction.

## Saved Swagger and catalog evidence

The first audit used local historical captures at the user's request.
After reconnection, a GET-only check ran at 20:05:19 Hong Kong time on
23 October 2026. It confirmed that the live schema and all 362 tags match the
captures. The repository preserves the original source files.
The manifest records the live check and source details.

The source records are:

- [supplier-openapi-2026-10-23.json](supplier-openapi-2026-10-23.json): saved Swagger schema.
- [supplier-tags-2026-10-23.json](supplier-tags-2026-10-23.json): full saved 362-tag response.
- [supplier-api-capture-2026-10-23.json](supplier-api-capture-2026-10-23.json): source details, recorded-file timestamps and SHA256 hashes.

See the [complete audit](../swagger-alignment-2026-10-23.md) and
[all 47 differing signal rows](../swagger-signal-differences-2026-10-23.csv).

The API omits its numeric limits. It does not return explicit null limits or
establish that operating limits do not exist.
The mock tag fixture uses the PDF for validation.
The mock batch response follows the documented results/count schema.
Production gets current metadata from the live API. It does not use these
captures as a runtime fallback.

This source evidence contains no API key, bearer token or operating-value
snapshot. The supplier PDF and historical DOCX remain unchanged.
