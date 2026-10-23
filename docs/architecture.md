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

The browser gets no supplier credential. The API key is set only in the backend HTTP header and is redacted from logs/errors. The backend serves same-origin static files, does not enable CORS, and accepts write/test/mode POSTs only from a loopback client. Write tokens exist only in memory and expire. A browser refresh discards its token; a backend restart clears the token map. Authorization callbacks recheck the token after awaited validation immediately before supplier single, batch and configured reset writes. A service command lock is shared by the write routes and the complete test runner to reject interfering local commands.

Supplier `GET /api/v1/tags/read` is one polling snapshot, with flat tag values and `timestamp`, `tags_ok`, `tags_failed`. Connection health is shown separately from supplier data freshness. A successful HTTP call cannot make stale PLC data healthy. Missing timestamps fail closed for writes. Timestamps without an offset also fail closed unless the confirmed supplier timezone is explicitly set with `PLC_TIMESTAMP_TIMEZONE`. Offset-aware timestamps retain their supplied timezone. `PLC_TIMESTAMP_OFFSET_SECONDS` is a temporary signed correction applied to freshness and event-time comparisons; it defaults to zero and is exposed in status and the UI. Raw supplier timestamps remain unchanged and frozen snapshots still exceed the stale-data limit. Reset the correction after synchronizing the supplier host clock. The console does not access PLC addresses directly; addresses are display metadata.

The authoritative static source is [HKPU PLC_API_User_Manual, PD-03726, KAL-1600-SG, 29-SEP-2026, v1.0](source/HKPU_PLC_API_User_Manual_PD-03726_2026-09-29.pdf). The mock snapshot contains 362 tags: 141 `W` and 221 `R`. The old `Tag_catalog.docx` is superseded and retained for history. This count is tested only for the static snapshot; production counts are dynamic.

`Tag.parse` accepts Bool, Word, SignedWord and Float. SignedWord is a signed 16-bit register; Float is an IEEE-754 REAL using two D registers. Numeric writes are finite engineering values checked against supplier limits; Bool accepts only 0/1. Multipliers and optional limits must be finite, multipliers positive, and low/high ordered. No local conversion to raw PLC registers occurs. Negative SignedWord values survive mock write/store/read unchanged.

REAL MODE uses every live `/tags/list` field as authority and refreshes it before each write. `catalog_diagnostics.py` compares that metadata against the bundled baseline for advisory warnings only; it never replaces live addresses, permissions, limits or other metadata. Count, added/missing tag and field differences are logged with expected/live metadata and shown in the health section through `/api/status`. Repeated identical diagnostics are not logged again. No catalog count is hard-coded in the UI.

Tag identity is `tag_name`; duplicate tag names are rejected. Duplicate device addresses are tolerated and warned. **SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.** The source also repeats `L220` for Tank03/Tank05 fill-water-auto and shows `Tank01_TempSV=D4000` in an API example versus `D4020` in the detailed table. No corrections are guessed; report live discrepancies for supplier review.

The REST contract remains `GET /api/v1/tags/list`, `GET /api/v1/tags/read`, `POST /api/v1/tags/write`, `POST /api/v1/tags/write/batch`, authenticated with backend-only `X-API-Key`. The supplier service defaults to `127.0.0.1:8000`; its manual's `0.0.0.0:8080` launch is an example accessible binding. Configure this console with the actual supplier IP, port and key. There is no direct register communication or MC Protocol in the console.

Safety functions, emergency stop, PLC interlocks, and physical commissioning authority remain with the machine and supplier. There is no AGV or robot code here. The test runner rechecks baseline feedback at final write validation, requires a later timestamp at or after command acceptance, and bounds feedback reads by the remaining monotonic deadline. Source timestamp comparison uses the same timezone and clock correction as freshness. It records timing evidence but cannot attribute effects from external PLC clients to its own command. The frontend invalidates cached health on failed or overdue refreshes and rejects invalid JSON responses.

The 0/1 checklist uses the existing guarded single-write endpoint and confirmation
dialog. Its browser-local records are scoped by supplier API and real/mock mode;
they store no credentials, write token or automatic actions. A possibly active 1 blocks other guided commands until verified 0 or an
explicit, verified non-door Keep at 1 decision. Local pre-dispatch rejections do
not create a false clear requirement; uncertain transport failures do. The backend adds a UTC
`console_accepted_at` receipt and `console_command_baseline_utc` from the final
validated pre-dispatch snapshot to every single write, including unmapped tags
and value 0. Status includes normalized `supplier_timestamp_utc`. A checklist clear is verified only when the
current poll matches status, is fresh, contains 0, and its corrected timestamp
is strictly later than the receipt, the browser snapshot recorded before
the clear request, and the backend's final pre-dispatch snapshot. Keep at 1
uses the equivalent checks for its accepted 1. Missing or legacy backend
baseline fields cannot qualify a new readback; the UI explains the recovery. API acceptance, readback, operator notes
and physical effect are kept distinct. The completion timer includes API and polling delay and is not a mechanical timing instrument.

Single-write receipts also include the confirmed feedback mapping and its value
and normalized timestamp from final pre-dispatch validation. The browser times
Confirm Send 1 to its first fresh matching completion poll, requiring a source
timestamp later than both this baseline and write acceptance. Clear timing and
API request latency remain separate. Preexisting,
interrupted, unknown and early-cleared feedback cannot become confirmed. The
manual monitor does not award the configured test runner’s PASS result or change
that runner’s deadlines.

`/api/status` checks the requesting browser's in-memory token and reports
`write_mode_enabled`. The browser sends its token only to write routes and this
status route, clears stale authorization, and ignores an older status response
that predates a newer token. Write guard errors and supplier failures during catalog/read validation
explicitly report `write_dispatched=false`. Once supplier write transport begins,
transport failures remain uncertain and do not make that claim.

A pending early clear moves completion monitoring to CLEARING before transport,
so feedback arriving during that request cannot be counted as completion of an
uninterrupted command. A definite pre-dispatch rejection resumes observation;
acceptance invalidates completion timing and an uncertain clear stays unknown.
Reloaded in-flight operations become unknown without replay. Preparation notes
create an audit record on first input; the completion timer still starts only
at Confirm Send 1.


## Feedback visibility, catalogue recovery and card design

The Feedback tests module receives the latest poll alongside status. A stable
result panel precedes the 50 case cards and displays the active test, expected
and live values, source freshness and current command readback. Backend results
alone determine PASS. Case cards no longer rebuild on every poll, preserving
keyboard focus; the live status region changes only when its phase changes.
Technical transport details use disclosure. Completed feedback never changes
another page's route or keyboard focus.

`controls.prepareWrite` validates and fills the Value write form for raw-tag
selection without dispatching. Feedback tests' manual-zero action instead uses
the existing confirmation dialog and write API in place, with current
mode/freshness/Remote and captured identity checks. Its accepted receipt and
strictly later command-zero observation are separate from the original test
result. Value write observation history also retains the clear receipt. The existing Review/confirmation and backend guards remain
the sole write path. `command-guidance.js` owns source-qualified value/procedure
descriptions for the selected Bool command, with an exact manual family whitelist
and address-qualified Tank 01 evidence. It does not authorize resets or mappings.

Catalogue recovery tracks successful loading separately from an empty catalogue.
After an initial failure, healthy communication starts a deduplicated background
retry. A successful empty list stops retries. Explicit empty/error/filter messages
and manual Retry/Clear filters actions prevent the Commands page appearing broken.

The card design follows [NN/g's visibility of system status](https://www.nngroup.com/articles/visibility-system-status/)
and [Carbon's inline feedback guidance](https://www.carbondesignsystem.com/building-blocks/core/components/notification/guidelines):
results stay near the task and persist, with the next action beside the evidence.
Configured is neutral, running and OBSERVED are blue, backend PASS is green, attention is amber
and failure is red. Status words accompany color, following [WCAG use of color](https://www.w3.org/WAI/WCAG22/Understanding/use-of-color.html).
The status region supports [WCAG status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html)
without repeated phase announcements on unchanged polls.

| Card status | Foreground / background | Calculated text contrast |
| --- | --- | ---: |
| Configured | #334155 / #f1f5f9 | 9.45:1 |
| Running | #155d7a / #eaf4f8 | 6.53:1 |
| PASS | #167653 / #e8f5f0 | 5.00:1 |
| Attention | #7a4b00 / #fff4d6 | 6.76:1 |
| Failure | #a52c32 / #fff0ee | 6.30:1 |

These checked card pairs exceed [WCAG's 4.5:1 normal-text minimum](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html).
Blue focus indicators exceed the [3:1 non-text threshold](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html)
against white. This is a scoped palette check, not a whole-application accessibility
certification or a screen-reader usability study.


The checklist's end-state toggle captures explicit operator intent with the
existing Send 1 confirmation. Manual 0 is the initial default; doors cannot
select Hold. Hold records a local Keep decision only after accepted 1 and a
fresh command readback strictly newer than browser, final pre-write and receipt
timestamps. It dispatches no extra request. The record-aware guard uses the
attempt's tag and address, so changing selection cannot apply another command's
intent. Clear intent prevents a later automatic Keep decision. Existing
unclassified mappings and physical-procedure warnings remain unchanged.


Manual-derived cases retain `requires_confirmation=true`. The test endpoint
accepts an explicit `mapping_under_test` Boolean for a supervised run and an
`end_mode` choice of `manual0` or `hold`; default requests remain conservative.
Both paths share baseline, fresh Remote, authorization, command-lock and deadline
checks. A candidate match is OBSERVED, while a configured mapping can PASS.
The result and audit retain the selected mode and mapping status. Write receipts
include acceptance and final command-baseline timestamps for later command-bit
observations. Neither the runtime opt-in nor an observed value certifies a
physical outcome, changes configuration, or infers an automatic reset.


Feedback tests share the existing checklist attempt records for pending commands,
Hold intent and manual clears. A request is recorded before dispatch so reloading
an unfinished run leaves an unknown pending outcome rather than replaying it.
Accepted test receipts feed the same record-aware Hold and zero-readback checks.
Candidate OBSERVED never becomes a confirmed completion timer. A live list of
configured command bits currently at 1 keeps active values visible across case
changes; stale observations remain labelled as such. It does not infer that every
1 is an operator-approved Hold request.


The command inventory uses the same manual-clear path as the active test. Stable
rows retain keyboard focus during polls. Each clear captures its own tag, address
and API context; it does not replace the active test. Untracked command bits get
zero-only cleanup records in the existing checklist store, without invented
write-1 evidence. A later clear intent invalidates earlier receipt fields.
Verification follows the matching shared record, so an uncertain retry cannot
reuse an older acknowledgement.

Write validation reports dispatch provenance explicitly. The runner marks the
transport boundary through the service's callback. A malformed response after
that boundary remains uncertain, even when no accepted receipt exists. The
browser treats only explicit `write_dispatched=false` as proof of pre-dispatch
rejection. Single-write receipts include `console_command_address` from the
final validated tag. Manual 0/1 checks that identity before recording acceptance
for either value. A missing or mismatched receipt stays unknown and pending. It
cannot qualify as Hold at 1 or a verified clear. Older receipts can use the
matching legacy `device_address` field when the trusted field is absent.

Manual hints are distinct from selected modes and confirmed rules. Always On
and Remote On descriptions supply 47 Hold hints in the bundled catalogue.
Auto polarity and RemoteStart behavior supply no recommendation. The exact
operator-confirmed Tank 01 addresses supply two confirmed Manual 0 rules.
The marker never changes a confirmed active attempt or dispatches a write.
