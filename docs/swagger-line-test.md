# Tank-ordered Swagger/API tag test

`tools/swagger_line_test.py` lists **all141 writable catalog tags** (102 binary,
39 numeric). Swagger defines generic HTTP routes; actual tag names come from the
saved `/api/v1/tags/list` response. Preview is offline and sends no request:

```bash
.venv/bin/python tools/swagger_line_test.py
```

To run directly against the supplier API, from the repository:

```bash
.venv/bin/python tools/swagger_line_test.py --execute
```

Add `--compare-app` to repeat each tag through the local web app's `/api/write`
backend, after the direct path restores its value. This is the write endpoint
used by the UI; **it does not automate browser clicks or test frontend controls**.
The current app also uses live supplier metadata, so this is a path comparison,
not an independent PDF-to-PLC implementation. The supplier batch-write route is
not exercised. Use `--only Tank01_FilterRemote` to select tags; repeat for several.
`--wait-seconds 15` is the default observation window (1–300 seconds).

Type `RUN` only after reviewing the exact list and standing at its first
location. Tests follow physical tank order. Global MainInlet is listed first;
only the Tank12-named door commands are placed at physical Tank13. Other Tank12
signals stay at Tank12. Each next tank requires Enter/R readiness; Q stops.
When comparing paths, Enter/R is also required before the app repetition.

For each test, P records a confirmed equipment/HMI result, I an incorrect action,
N an unconfirmed/no-response observation, and Q restores then stops. The key
requests restoration; the next command requires fresh verified restoration.
These observations do not prove physical stopping after restoration.

No setting or reset procedure is guessed:

- Numeric tags require an operator-approved engineering value, different from
  the original value. The script restores the original value, not zero. Type,
  multiplier/register representation and the published PDF safety envelope are
  checked. These PDF bounds are a local test restriction, not a claim that the
  supplier API publishes or enforces them.
- Binary commands require an initial0. An active command is preserved and blocks
  the run. Door, RemoteStart and MainInlet tests require an explicit known
  hold1/until-finished/restore0 rule. Enter S if that rule is not established.
- Known shared addresses require ALIASES confirmation for all affected equipment.
  Unexpected aliases block testing. Shared feedback cannot prove an independent
  command-to-output mapping.
- Auto's own mode-bit readback is tested. Immediate movement is not established
  by the manual. No movement alone is neither an API failure nor physical Pass.
- Door position feedback may remain latched when command0 is verified. If the
  requested position was already set, the result is Already set, with no new
  transition proof. The script does not operate the opposite door command to
  manufacture a starting position. The operator must restore a comparable
  physical starting state if a movement comparison is needed.

Results keep request acknowledgment, command readback, mapped output/status,
human verdict and restoration separate. A successful write/readback with status0
is **output unconfirmed**, not a dead HTTP endpoint. Each path saves its baseline;
changed process/mode/door conditions are flagged and do not prove a path defect.

The app option accepts literal HTTP loopback origins only (default
`http://127.0.0.1:8080`), requires REAL mode and the same supplier origin, and owns
its write token. It never disables another client's token. Keep other write
clients inactive. Numeric/user-entered values and reset rules can be skipped;
skipped cases remain visible in the report.

Fresh complete Remote1/Local0 data, unchanged write-target metadata and later-than-receipt /
final-baseline samples are required. Unknown write outcomes never retry the test
value; explicit RESTORE is required, followed by a stopped queue. Cancellation
or audit/storage errors stop subsequent testing. Authorized guarded restoration
is still attempted after logging failure. Read-only status metadata drift does
not block clearing an unchanged reviewed write target, but invalidates output
proof and stops the queue. A changed write-target address/type still blocks that
unsafe restoration. Failed restoration needs equipment
inspection before any other test.

Evidence goes to a new `logs/swagger-line-test-<id>/`: append-only `events.jsonl`,
`report.json`, a `results.csv` row per tag/path, and side-by-side
`comparison.csv` results. HTTP error status and the local app reason are retained;
write-token echoes are redacted. Credentials are read from existing
settings and are not logged. Old reports, browser marks and the33 confirmed P
imports are not replaced. This runner does not automatically import new marks.

The new runner has been tested with fake PLCs/HTTP transports and previewed
without a network connection. It has not been executed on the production line.
