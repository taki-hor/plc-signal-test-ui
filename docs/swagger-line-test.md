# Tank-ordered Swagger/API tag test

`tools/swagger_line_test.py` previews all 141 writable tags: 102 binary and 39
numeric. Swagger defines the routes; `/api/v1/tags/list` defines the tag names.
Preview is offline and sends no request:

```bash
.venv/bin/python tools/swagger_line_test.py
```

Execute the selected direct supplier tests:

```bash
.venv/bin/python tools/swagger_line_test.py --execute
```

Add `--compare-app` to repeat each tag through the local app server's `/api/write`
path after direct restoration. This does not click browser controls or exercise
the supplier batch route. The app uses live supplier metadata; this comparison
is not an independent PDF implementation. Repeat `--only TAG` to select tags.

## One confirmation

`RUN` is the only confirmation. It approves the printed tag/path list, displayed
known shared addresses and the hold-until-result/restore-original procedure.
Every tested path must match that frozen approval scope before any actuation.
Review the selected procedures and all affected equipment before RUN; do not
include a command whose hold/reset rule is unknown.

There are no HOLD, ALIASES, RESTORE, tank-ready or app-path-ready prompts.
Numeric test values and P/I/N/Q are data entry and remain:

- P records a confirmed equipment/HMI result.
- I records an incorrect result.
- N records an unconfirmed/no-response observation.
- Q restores the current command and stops.

Tanks and paths advance automatically only after verified restoration. There is
no pause before the next tank. Stay ready to observe; Q or Ctrl+C stops the run.
A result key does not verify physical stopping afterward.

Physical order places only the Tank12-named door at physical Tank13. Other
Tank12 signals remain at Tank12. Global MainInlet is listed first.

## Values and validation

Numeric tags require a finite, representable, operator-approved engineering value
that differs from baseline. S skips a numeric input. The script restores the
original value, not zero. Published PDF bounds are a local test envelope; this
does not claim that the API publishes or enforces them.

Binary tags must start at 0. Existing active commands are preserved and block the
test. Doors wait for the operator's result before clearing; latched position
feedback may stay at 1. Already-set feedback is not a new transition. The script
never moves the opposite door to manufacture a starting state.

Known aliases are displayed before RUN and included in its approval. Unexpected
aliases or changed identities block writes. Affected shared-tank outputs must
restore before continuing; shared feedback does not prove independent mapping.

Auto tests verify the mode bit. The manual does not establish an immediate
movement requirement. No movement alone is neither an API failure nor a physical
Pass. Request acceptance, command readback, mapped output, human verdict and
restoration are recorded separately. Status remaining 0 after a successful write
is output unconfirmed, rather than an unresponsive HTTP endpoint.

Fresh complete Remote=1/Local=0 data, unchanged metadata and samples strictly
later than the receipt and final pre-write baseline are required. Stale read-only
observations are rejected and polling continues within the same observation
window. The 3000 ms freshness limit and write guards are unchanged.

Unknown outcomes never retry the test value. RUN authorizes one guarded attempt
to restore the original value only for a potentially dispatched own write, then
the queue stops. Cancellation before dispatch sends no restoration write and
preserves external state. Changed write targets, stale data, Local mode or an
externally changed numeric value can block restoration; inspect the named case
before another test. A logging failure cannot block an otherwise authorized,
guarded restoration, but it stops subsequent tests.

The app option accepts literal HTTP loopback origins only, requires REAL mode
and the same supplier origin, and owns its token. Other write clients must stay
inactive. Baselines and changed process conditions are retained; an observed
path difference does not prove that the HTTP path caused it.

## Resume skipped and unvisited items

```bash
.venv/bin/python tools/swagger_line_test.py --resume-report logs/swagger-line-test-a22b56f0a6/report.json --execute
```

Resume keeps settled P/non-timeout Auto and output-timeout Fail results, and
queues only skipped/unvisited paths. Direct results never hide an untested app
path. Use the report.json produced by the latest relevant run. The completed
26-Oct direct run shown above carries all141 settled paths, so it has no pending
direct work. Use --compare-app only when intentionally adding untested app paths.
Reusing an older resume snapshot requeues work completed by its later follow-up
runs; it does not discover newer reports automatically. The earlier
swagger-resume-reviewed.json still selects its historical58-item queue.

Resume checks the source hash, full inventory/schema, mode and supplier origin.
A legacy source without embedded origin remains explicitly flagged across
chains; verify the printed supplier and source before RUN. Prior settled results
and provenance are carried forward so later resumes do not re-add completed work.

An unresolved prior restoration requires a separate fresh read of the original
value strictly after its source restore acknowledgment/final baseline, before any
new write. This recovery check never sends a corrective write or clears other
current tank states. Source hashes are checked again after RUN.

## Evidence

A new `logs/swagger-line-test-<id>/` contains append-only `events.jsonl`, full
`report.json`, per-path `results.csv` and `comparison.csv`. Reports retain context,
source provenance, baselines, receipts and verification samples. Credentials are
read from existing settings and redacted. Raw source reports and existing web
marks are not rewritten by this runner; importing reviewed marks is separate.
Explicit operator API verdicts stay separate from human Pass/Fail and the raw
automated evidence. For example, an operator API Pass on shared feedback does
not establish an independent feedback mapping or a physical Pass.

The RUN-only flow initially passed17 isolated fake scenarios with real networking
blocked; all seven existing validation methods matched the tested baseline.
Subsequent26-Oct direct runs completed all141 writable tags; their reviewed
operator outcomes and API caveats are in swagger-second-run-2026-10-26.txt.
This does not establish full browser/app-path comparison or batch-route coverage.
A skipped/blocked attempt alone remains untested until a later completed run.
