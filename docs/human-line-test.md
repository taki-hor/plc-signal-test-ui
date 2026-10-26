# Human-in-the-loop line queue

`tools/human_line_test.py` tests the reviewed non-door commands **one at a time**.
Each case uses `0 → 1 → 0`. It talks directly to the supplier API from the existing
`.env`, through the project's `PLCClient` and `SignalService`. It does not require
the local web server to run, and it does not use its write-mode token.

Review the exact plan without any network request:

```bash
.venv/bin/python tools/human_line_test.py
```

The editable plan is `config/human-line-test-plan.json`: 40 non-door command/status
cases and 23 distinct Auto bits. Use `--only Tank01_FilterRemote` to select one;
repeat `--only` to select several. Its frozen identities are checked against live
metadata before execution. The scope cannot be expanded by adding arbitrary tag
names. Doors, numeric values, RemoteStart, MainInlet and shared-address cases are
excluded. Each Auto case verifies its own readback; it does not claim that its
associated equipment ran. This is not an exhaustive set of simultaneous command
combinations, and no prerequisite commands are synthesized. Supplier documentation gives no
prerequisite truth table. An optional case `operator_note` can record an
operator-reported prerequisite; the script displays it and sends no enable command.

To operate the line, review the printed commands, stand where you can inspect the
selected equipment, and run:

```bash
.venv/bin/python tools/human_line_test.py --only Tank01_FilterRemote --execute
```

For the full reviewed queue, omit `--only`. The script sorts cases by tank number
and related function. Within each function, the On/Remote command precedes its
Auto bit. These remain separate tests; the script does not combine commands or
set prerequisites.

Type `RUN` once after checking the printed list, standing at the first tank, and
checking line readiness and equipment clearance. Cases at that tank advance after
each restoration is verified. Before moving to the next tank, the queue stops
with the preceding command restored to `0`. The heading shows the next tank and
case progress. Walk to that tank, then press **Enter/R** when ready, or **Q** to
stop before any command for that tank is sent. Live write guards are checked again
after you continue. Keep other testers and write clients inactive: direct
supplier requests do not share the web server's command lock.

After sending `1`, the script waits up to the case's `wait_seconds` (default 15)
for a fresh later command readback and, where configured, its mapped status. It
then holds the command at `1` while you inspect the equipment. Press one key:

- **P**: Pass. The requested operation is visible; saves human result **Pass**.
- **I**: Incorrect action. The equipment performs an unexpected or wrong action; saves **Fail**.
- **N**: No response. Saves **Not checked** with `retest_required=true` for another observation.
- **Q**: Stop after requesting `0` and checking restoration; saves **Not checked**.

Each key requests `0`; the next case starts only after a later fresh read verifies
command/status restoration. Your key describes **operation while the command is
1**. It does not certify physical stopping, which happens afterward. The export
keeps `human_observation` and `human_result` separately from API evidence. A P
verdict is an explicit human Pass for the observed operation.
`physical_stop_verified=false` records that the verdict did not confirm physical
stopping. API restoration to `0` does not change that field. I and N remain
distinct: I explicitly records a failed human check; N stays unchecked and needs
a rerun, because a missing or uncertain response does not establish a failed
physical check. Neither observation alone proves that the API or PLC is faulty.

The script requires fresh complete data, `Remote=1`, `Local=0`, unchanged metadata,
independent addresses and a zero baseline. It preserves an already active state.
It uses the existing timezone, timestamp correction and stale limit unchanged.
For Auto, related On/status signals must start at zero and return to zero; the
script does not write those related commands to manufacture a restoration.

Ctrl+C stays responsive while a verdict key is awaited and restores the terminal
mode. After an acknowledged command, cancellation requests the already-approved
`0` cleanup and stops. Cancellation while the `1` request is in flight leaves its
outcome uncertain.

A missing or mismatched write acknowledgment is an uncertain outcome. The script
never retries `1`. It asks you to type `ZERO` before requesting cleanup, then stops
the queue. A failed clear or unverified restoration also stops the queue and names
the signal needing inspection. A command may remain active if communication is
lost, cleanup is declined, or the process is killed. Use the local machine
controls as required; this tool is not a safety system.

An audit storage failure blocks any new `1` and stops the queue. It does not
block an already-authorized cleanup `0`: the same freshness, mode and metadata
guards still apply. The script retains fallback evidence in memory and includes
it in the report if export succeeds. If storage remains unavailable, it prints
the audit error and cleanup state; those in-memory records cannot survive process
exit.

Evidence is written to a new `logs/human-line-test-<UTC>-<id>/` folder, or the new
folder given by `--output`:

- `events.jsonl`: append-only intent, receipt, full read snapshots and decisions.
- `report.json`: complete per-case API evidence and human observations.
- `results.csv`: concise results for review.

API pass requires the complete fresh `1` and restored `0` observations and valid
receipts. API pass and a human observation remain separate. The script reads the
API key only from existing settings; logs redact it. It does not update saved web
UI judgments automatically. Return the report/CSV for review and explicit result
reconciliation rather than treating old physical results as newly checked.
