# Line queue with an operator

`tools/human_line_test.py` tests reviewed non-door commands **one at a time**.
Each case uses `0 → 1 → 0`.
The script uses the supplier API and existing `.env` through `PLCClient` and `SignalService`.
It does not require the local web server or its write-mode token.
This guide describes the 63-case human queue, not the separate 141-tag Swagger runner.

Review the exact plan without network requests:

```bash
.venv/bin/python tools/human_line_test.py
```

The editable plan is `config/human-line-test-plan.json`.
It contains 40 non-door command/status cases and 23 distinct Auto bits.
Use `--only Tank01_FilterRemote` to select one case.
Repeat `--only` to select several cases.
The script checks fixed identities against live metadata before execution.
Arbitrary tag names cannot expand this scope.

The queue excludes doors, numeric values, RemoteStart, MainInlet and shared addresses.
Each Auto case checks its own readback. It does not claim equipment operation.
The queue does not cover all simultaneous command combinations.
It does not create prerequisite commands. Supplier documents give no prerequisite truth table.
An optional `operator_note` can record an operator-reported prerequisite.
The script shows that note. It sends no prerequisite enable command.

Before execution, review the printed commands.
Move to a location where you can inspect the selected equipment.
Run the selected case:

```bash
.venv/bin/python tools/human_line_test.py --only Tank01_FilterRemote --execute
```

Omit `--only` for the full reviewed queue.
The script sorts cases by tank number and function.
Within each function, the On/Remote command precedes its Auto bit.
These remain separate tests. The script does not combine commands or set prerequisites.

Before `RUN`, check the printed list.
Stand at the first tank.
Check line readiness and equipment clearance.
Type `RUN` once.
Cases at that tank continue after each verified restoration.
Before the next tank, the queue stops with the preceding command restored to `0`.
The heading shows the next tank and case progress.

Move to that tank.
Press **Enter/R** when ready.
Press **Q** to stop before the queue sends a command for that tank.
The script checks live write guards again after you continue.
Keep other testers and write clients inactive.
Direct supplier requests do not share the web server's command lock.

After `1`, the script waits for later fresh command readback and any configured mapped status.
The case's `wait_seconds` sets this limit. The default is 15 seconds.
The script then holds `1` while you inspect the equipment.
Press one key:

- **P**: Pass. The operation is visible. The script saves human result **Pass**.
- **I**: Incorrect action. The equipment performs a wrong or unexpected action. The script saves **Fail**.
- **N**: No response. The script saves **Not checked** with `retest_required=true` for another observation.
- **Q**: Stop. The script requests `0`, checks restoration and saves **Not checked**.

Each key requests `0`.
The next case starts only after a later fresh read checks command/status restoration.
Your key describes **operation while the command is 1**.
It does not certify physical stopping after the key press.

The export separates `human_observation` and `human_result` from API evidence.
P records an explicit human Pass for observed operation.
`physical_stop_verified=false` means the verdict did not confirm physical stopping.
API restoration to `0` does not change that field.
I records a failed human check. N records an unchecked result that needs another run.
A missing or uncertain response does not establish a physical failure.
Neither observation alone proves an API or PLC fault.

The script requires these conditions:

- Fresh, complete data.
- `Remote=1` and `Local=0`.
- Unchanged metadata and independent addresses.
- A zero baseline.

The script preserves an active state instead of testing it.
It retains the existing timezone, timestamp correction and stale-data limit.
For Auto, related On/status signals must start and return at zero.
The script does not write those related commands to force restoration.

Ctrl+C remains responsive while the script waits for a verdict key.
It restores terminal mode.
After an acknowledged command, cancellation requests the approved cleanup `0` and stops.
Cancellation during a `1` request leaves the outcome uncertain.

A missing or mismatched acknowledgment also leaves the outcome uncertain.
The script never retries `1`.
It asks for `ZERO` before requesting cleanup. It then stops the queue.
A failed clear or unverified restoration stops the queue and names the signal for inspection.

A command may remain active after lost communication, declined cleanup or forced process termination.
Use local machine controls as required.
This tool is not a safety system.

Audit storage failure blocks new `1` requests and stops the queue.
It does not block an approved cleanup `0`.
The same freshness, mode and metadata guards still apply.
The script retains fallback evidence in memory. It includes that evidence if report export succeeds.

If storage remains unavailable, the script prints the audit error and cleanup state.
Memory-only records cannot survive process exit.

The script writes evidence to a new `logs/human-line-test-<UTC>-<id>/` folder.
`--output` can specify another new folder.
The folder contains:

- `events.jsonl`: append-only intents, receipts, full read snapshots and decisions.
- `report.json`: complete API evidence and human observations for each case.
- `results.csv`: concise results for review.

API pass requires valid receipts and complete fresh observations of `1` and restored `0`.
API pass and human observation remain separate.
The script reads the API key from existing settings. Logs redact it.
The script does not update saved web judgments automatically.
Return the report or CSV for review and explicit result reconciliation.
Do not treat old physical results as new checks.
