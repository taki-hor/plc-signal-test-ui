# Tank-ordered Swagger/API tag test

`tools/swagger_line_test.py` previews all 141 writable tags: 102 binary and 39 numeric.
Swagger defines the routes. `/api/v1/tags/list` defines the tag names.
Preview runs offline and sends no request:

```bash
.venv/bin/python tools/swagger_line_test.py
```

Execute the selected direct supplier tests:

```bash
.venv/bin/python tools/swagger_line_test.py --execute
```

Add `--compare-app` to repeat each tag through the local app's `/api/write` route after direct restoration.
This option does not click browser controls or test the supplier batch route.
The app uses live supplier metadata. It is not an independent PDF implementation.
Repeat `--only TAG` to select tags.

## One confirmation

`RUN` is the only confirmation.
It approves the printed tags, paths, known shared addresses and procedure.
The procedure holds binary 1 until the verdict, then restores the original value.
Each tested path must match that fixed approval before actuation.

Review the selected procedures before RUN.
Check all affected equipment.
Exclude commands with unknown hold/reset rules.

There are no HOLD, ALIASES, RESTORE, tank-ready or app-path-ready prompts.
Numeric values and P/I/N/Q remain data entry:

- P records a confirmed equipment/HMI result.
- I records an incorrect result.
- N records an unconfirmed or no-response observation.
- Q restores the current command and stops.

Tanks and paths continue automatically only after verified restoration.
The queue does not pause before the next tank.
Stay ready to observe.
Q or Ctrl+C stops the run.
A result key does not confirm physical stopping afterward.

Physical order places only the Tank12-named door at physical Tank13.
Other Tank12 signals remain at Tank12. Global MainInlet appears first.

## Values and validation

Numeric tests require a finite, representable engineering value approved by the operator.
The value must differ from the baseline. S skips numeric entry.
The script restores the original value, not zero.
The local test limits come from the PDF.
This does not mean the API publishes or enforces those limits.

Binary tags must start at 0. An active command blocks its test without changing that state.
Door tests wait for the operator's result before clearing.
Position feedback may stay at 1.
Feedback already at 1 is not a new transition.
The script never moves the opposite door to create a starting state.

The script shows known aliases before RUN. RUN includes those aliases in its approval.
Unexpected aliases or changed identities block writes.
Outputs in affected tanks must restore before the queue continues.
Shared feedback does not prove an independent mapping.

Auto tests check the mode bit.
The manual does not require immediate movement.
No movement alone proves neither API failure nor physical Pass.
The script records request acceptance, command readback, mapped output, human verdict and restoration separately.
Status 0 after a successful write means output unconfirmed. It does not mean an unresponsive HTTP endpoint.

The script requires fresh, complete Remote=1/Local=0 data and unchanged metadata.
Samples must be strictly later than the receipt and final baseline before the write.
The script rejects stale read-only samples. It continues polling within the same observation window.
The 3000 ms freshness limit and write guards remain unchanged.

An unknown outcome never causes a retry of the test value.
For a potentially dispatched own write, RUN permits one guarded attempt to restore the original value.
The queue then stops.
Cancellation before dispatch sends no restoration write and preserves external state.

Changed targets, stale data, Local mode or an externally changed numeric value can block restoration.
Inspect the named case before another test.
A logging failure cannot block an authorized, guarded restoration.
It stops later tests.

The app option accepts literal HTTP loopback origins only.
It requires REAL mode and the same supplier origin. It owns its write token.
Keep other write clients inactive.
The report retains baselines and changed process conditions.
A difference between paths does not prove that the HTTP path caused it.

## Resume skipped and unvisited items

```bash
.venv/bin/python tools/swagger_line_test.py --resume-report logs/swagger-line-test-a22b56f0a6/report.json --execute
```

Resume retains settled P, Auto results without a timeout and output-timeout Fail results.
It queues only skipped or unvisited paths.
Direct results never hide an untested app path.
Use the latest relevant run's report.json.
The completed 26-Oct direct run above carries all 141 settled paths. It has no pending direct work.

Use `--compare-app` only when you intend to add untested app paths.
An older resume snapshot queues work completed in its later runs again.
It does not discover newer reports automatically.
The earlier swagger-resume-reviewed.json still selects its historical 58-item queue.

Resume checks the source hash, full inventory/schema, mode and supplier origin.
A legacy source without an origin keeps its warning across resume chains.
Check the printed supplier and source before RUN.
Resume retains settled results and their sources. Later resumes therefore do not add completed work again.

An unresolved restoration requires a separate fresh read of the original value before new writes.
That sample must follow the source restore acknowledgment and final baseline strictly.
The recovery check sends no corrective write. It does not clear other current tank states.
The script checks source hashes again after RUN.

## Evidence

A new `logs/swagger-line-test-<id>/` contains append-only `events.jsonl` and the full `report.json`.
It also contains per-path `results.csv` and `comparison.csv`.
Reports retain context, sources, baselines, receipts and verification samples.
The script reads credentials from existing settings. Logs redact them.

The runner does not rewrite raw source reports or existing web marks.
Import of reviewed marks is separate.
Explicit API verdicts remain separate from human Pass/Fail and raw automated evidence.
An operator API Pass on shared feedback does not prove an independent mapping or physical Pass.

The RUN-only flow initially passed 17 isolated scenarios with fake suppliers and real networking blocked.
All seven validation methods matched the tested baseline.
Later 26-Oct direct runs completed all 141 writable tags.
The reviewed results and API limits are in swagger-second-run-2026-10-26.txt.
This does not establish full browser/app comparison or batch-route coverage.
A skipped or blocked attempt remains untested until a later completed run.
