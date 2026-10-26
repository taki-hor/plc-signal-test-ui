# User guide

Open the dashboard on the backend workstation at `http://localhost:8080`. The header must show **WRITE MODE OFF** after every page load. **MOCK MODE** appears prominently when `PLC_MOCK_MODE=true`.

**Known door-name mismatch:** the operator confirmed that the **Tank12** door
commands and position signals belong to the physical **Tank13** door. The API
and current UI still use Tank12 names. This correction covers the four door
tags only. See the [verified mapping](signal-test-plan.md#physical-tank-13-door-uses-tank12-api-names).

The left sidebar separates the console into pages. **Read signals** keeps three separate sidebar destinations: **Tank monitor** compares one tank’s values by function, **Signal browser** searches the complete catalogue, and **Alarm signals** inspects raw alarm bits. All three only display supplier poll values. **Write signals** lists **Feedback tests**, **Manual 0/1**, and **Setpoints & batch**. These pages hold every control that can send a command; each of these pages shows a write gate listing write test mode, API connection, data freshness and PLC Remote, and stays locked until all four are met. **Records** holds the Tag catalog and Evidence log. The status bar and write-mode banner stay visible on every page. Pages can be bookmarked, e.g. `http://localhost:8080/#/commands`.

Keyboard navigation moves to the new page heading. **Skip to content** bypasses
the sidebar. Catalog Select buttons keep keyboard focus during live updates.
Catalog warnings open from a count on Overview. Their full details remain
available. A failed write-mode request appears above the page on every route.
Feedback tests show the reason when Run is unavailable. See the
[HCI review](hci-review-2026-10-23.md) for review scope and measurements.

The status bar and Overview page distinguish API connection, `Remote` mode, supplier poll timestamp, data age, and tag success/failure counts. A green connection with amber stale data is not ready for writes. Live values and connection status refresh automatically at `PLC_UI_POLL_INTERVAL_MS` (currently 1 second); no button click is needed. **Refresh now** also reloads the catalog, test definitions, and logs. The communication log has its own **Refresh log** button. Failed, malformed or overdue refreshes remove the healthy state and disable write/test controls. The overdue timer uses the stale-data limit; read requests also have a 10-second transport timeout. A temporary clock correction is displayed separately from the raw supplier poll time.

Signal browser (the Live signals route, `#/signals`) groups every matching card in the manual’s order: Alarms, System, then Tank 01 onward, with a count for each group. The previous first-120 limit is removed; all 221 read-only signals, or all 362 tags with All signals selected, remain accessible. Descriptions wrap in full. Search by name/description/address and combine type, permission and group filters. Extra live tags remain included. Choose a tank in Tank monitor’s horizontal tab bar for its catalog-defined signals. The bar scrolls to every live tank; Left/Right and Home/End select tanks without resetting on a poll. R/W labels distinguish read-only values from writable request/setpoint readbacks; Tank01A and Tank01B identities remain visible. Each read view labels stale, disconnected or missing observations instead of presenting cached values as current. The Alarms page shows raw Bool values; the supplier must confirm polarity. In Tag catalog, enable Advanced mode to see PLC addresses, multipliers, and limits. Read-only rows have no write action.

**API limits** shows the bounds supplied by the current API. If a bound is
missing, it says **not published**. Missing metadata does not mean that an
operating value is unlimited. The saved supplier catalog omits the PDF's numeric
limits. The console retains finite/type checks and checks any limits the API
does supply. Confirm the approved engineering value before a write. See the
[PDF/Swagger audit](swagger-alignment-2026-10-23.md) for the exact signal list.

Both type filters include Bool, Word, SignedWord and Float. The current static mock snapshot is 362 tags (141 W, 221 R); real counts come from the live API. For Tank01_TempAdj, Advanced mode shows D4010, SignedWord, W, multiplier 0.1, low −999.0 and high 999.9. Setpoints & batch shows the same allowed range and accepts −5 or −10.5 as engineering values within those limits. No multiplier conversion is applied by this console.

The 29-SEP-2026 supplier baseline also shows Tank07_AmpereSV at D1362 with multiplier 0.1 and 0–200 A limits; Tank07 current/voltage multipliers are 0.1. SwingSV limits for Tank03/05/10/14 are 5–120 CPM. Tank16_Conductivity (D1142, Float, R, multiplier 1.0) replaces Tank16_PH; Tank09_WaterFlow is added at D1036. All eight TempAdj tags use SignedWord with −999.0 to 999.9 limits.

Health warnings display catalog differences without changing the live metadata. Export communication logs for expected/live details and supplier review. **SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.** This warning permits read-only startup. Treat it as unresolved field metadata until the supplier confirms it.

## 0/1 command checklist

Use the **Manual 0/1** page (`#/commands`) for writable Bool commands (currently 102). Search by name,
description or PLC address, filter by tank/group, and choose a command. Numeric
setpoints remain on the **Setpoints & batch** page (`#/write`), which still includes all 141 writable tags.

If the catalogue was unavailable at startup, loading retries when API communication
returns. The page shows its loading/error state and a Retry action. An empty
filter shows **No commands match your filters** and **Clear filters**. A valid
catalogue with no writable Bool tags is shown explicitly without endless retries.

The compact mode control marks a **Hint** on Hold 1 for the manual's Always On
and Remote On descriptions. This is an inference, not a confirmed hold rule.
Auto, RemoteStart and unknown tags have no recommendation. The tested Tank 01
rule marks Manual 0 as **Confirmed**. The console does not replace your selected
mode or change an active attempt. Full procedure and source text remain in
expandable details.

The selected command's guide explains values 1 and 0, the manual evidence and
which rules remain unconfirmed. Tank 01 at its tested M300/M301 addresses has an
operator-confirmed hold-until-complete then manual-clear procedure. Other doors
remain unconfirmed. Always On, Auto and Remote On hold interpretations are
inferred from descriptions; Auto polarity is not certified. RemoteStart and new
names remain unclassified. These guides also appear in the existing confirmation.

1. Enable write test mode when ready. Select the command and choose its end-state
   mode: **Send 1 → manual 0** or **Hold at 1**. Manual 0 is the initial default;
   the manual's inferred descriptions do not select Hold for you. Doors retain
   the manual-0 path. Click the mode's Send 1 action and check the tag, address,
   current value, requested value and selected mode in the single confirmation.
   **Cancel** or Escape sends nothing. The confirmed mode is recorded with the
   attempt; it cannot be changed while that command needs clearing.
2. Watch the equipment. **1 → completion** starts only when you confirm
   **Send 1…**. It stops at **CONFIRMED** when a fresh API poll reports the
   configured opened/closed signal at its expected value. The backend records
   that signal's value in the final read before dispatch. A cached poll or a
   signal already complete before the write cannot prove a new transition.
   API response time for 1 and 0 is displayed separately. Enter physical
   observations or any problem in Notes.
3. For the confirmed Tank 01 door procedure, wait for physical movement to finish,
   then **Send 0…** and confirm the clear. Confirm other doors' rules before applying
   this sequence. The completion timer stays frozen while you do this. Other
   conflicting commands remain locked until a later poll verifies 0. The on-screen
   hint names the pending command; **Send 0…** remains available for clearing it.
4. For a confirmed maintained non-door state, choose **Hold at 1** before sending.
   After the API accepts 1 and a later fresh poll verifies command value 1, the
   UI records **KEPT AT 1** automatically using your confirmed choice. This is a
   local audit update, with no additional write or physical-completion claim.
   The state stays visible in the active-state banner and other tests become
   available. **Send 0…** remains manual when the state should end; clearing a
   previously sent command remains possible while another command is pending.
   The older **Keep at 1 (non-door)** action remains available for a manual
   decision on existing attempts. Door commands cannot use Keep at 1. No pulse,
   retry, automatic clear or repeated enforcement of 1 is performed.
5. Check the physical result. Use **Mark Pass** only after your check.
   Use **Mark Not checked** to remove that mark. **Record Fail** records an issue.
   **API CYCLE RECORDED** means both writes were accepted and a later fresh poll
   verified 0. **KEPT AT 1** records the chosen command state. Neither label marks
   the physical test complete. Your result does not clear commands or release
   pending-command locks. API feedback and timing stay separate.

Keep at 1 records your chosen end state; it does not certify that a tag is a
maintained command. The [hold/reset findings](signal-test-plan.md#command-hold-and-reset-findings)
separate manual descriptions, the operator-confirmed Tank 01 sequence and
unclassified RemoteStart behavior. Sending 0 is not a guaranteed equipment stop
when Auto or other PLC logic remains active.

A new readback must be later than the backend's final pre-write snapshot as
well as the write receipt. A cached snapshot cannot qualify just because the
supplier clock is slightly ahead. If a pending receipt from an older backend
lacks this evidence, the UI leaves it unverified and shows a recovery hint.
Update/restart the backend, check the actual state and use a newly confirmed
manual 0 when required. Historical API evidence is preserved. Human results are never inferred from it.

Notes are saved from the first input, even before any command. Switching tags
or reloading preserves these preparation notes without starting the timer.

**New attempt** prepares a blank record and leaves the timer at 00:00. It does
not send anything. Older attempts retain their original logs; completion timing
not collected by the previous UI is shown as **NOT RECORDED**, never reconstructed
from your later Send 0. An unused blank attempt cannot create more blank attempts.

A rejected request marked **BLOCKED before dispatch** does not require a false
Send 0. Re-enable write test mode and retry; the rejection remains in history.
The console also recovers the old local “write mode disabled or expired” 403
records. A supplier catalog/read failure before dispatch is also marked BLOCKED,
including communication errors; no write was sent. A failure after write
transport begins, or an outcome lost on reload, remains pending for inspection
and manual clearing. Reloading starts with write mode off;
the page checks the backend token's status to detect expiry or a backend restart.
Other clients and the separate Setpoints & batch form are outside the guided sequence.

If Send 0 starts before completion feedback has been observed, the monitor
shows **CLEARING** and cannot award a completion time while that request is
unresolved. An accepted clear records **CLEARED BEFORE COMPLETION**. A clear
proven blocked before dispatch resumes observation; an uncertain clear records
**CLEAR OUTCOME UNKNOWN**. Reloading an unfinished Send 1 or Send 0 similarly
records an unknown outcome, keeps the possible command pending, and sends
nothing automatically.

Leaving or reloading the page while completion feedback is still **WAITING**
records **MONITORING INTERRUPTED**, with no completion time. A later matching
signal cannot resume that interrupted measurement. The accepted command and
its history remain pending so you can re-enable write mode and explicitly
send 0 when ready. Completion timing already confirmed before leaving is
preserved.

Only locally configured mappings provide completion timing. Unknown mappings show **NO
CONFIRMED MAPPING**. An already-set signal, lost monitoring or early clear does not produce a
completion time. The manual checklist observes live feedback until completion
or an interruption; it does not award the configured verification runner’s
PASS result. Use Feedback tests for the configured tests and their deadlines. Network and polling
delay are included; this is **not mechanical travel time**. Expand each event for
UTC time, elapsed time since Send 1, API latency, command/feedback values,
Remote/Local state and raw/normalized supplier timestamps. The full attempt
elapsed time is retained separately for history. Log details remain open through
live updates.

**Export checklist & log CSV** or **Export JSON** includes untested commands and
all attempts. **New attempt** preserves earlier records and becomes available
once a possibly active command has verified 0 readback or the request was
definitively blocked before dispatch. Notes, results and logs are saved
in this browser's local storage, separately for each supplier API and real/mock
mode. They contain no API key or write token and do not enable writes on reload.
They are not shared between browsers and are lost if browser data is cleared;
export your test evidence regularly. Existing backend communication logs remain
separate. No unconfirmed command/feedback mapping is enabled by this checklist.

## Other write and verification controls

For a manual write, select a writable tag, enter an engineering value, then click **Review write**. Confirm the tag, address, current value, and new value in the dialog. A supplier `written=true` response means the API accepted the request; inspect a physical feedback signal or run a configured verification test to prove effect. Escape and Cancel close the review without issuing a command, including after an earlier confirmed write. Batch writes use a JSON array of `{ "tag_name": "...", "value": 0 }` objects and an extra batch confirmation.

The value selector puts **Numeric setpoints** first and **Bool commands** second. All 141 writable tags remain available. A catalogue refresh preserves a valid selected tag.

### Read signals on Setpoints & batch

**Read signals & feedback** shows every live catalog tag marked read-only (221 in
the bundled snapshot). The selected command's mapped feedback and other read
signals in its group appear first. Door commands show both **DoorOpened** and
**DoorClosed** above the table. Search by name, description or address, or choose
**Selected command's group** to narrow the table. Monitoring works in read-only
mode and never sends a command.

Each confirmed manual single or batch write creates a **Write record**. The backend
captures all read-only values in its final validated snapshot before dispatch.
**Before write**, **Recorded after**, and **Live value** distinguish that baseline,
the retained subsequent observation, and the current poll. UTC timestamps identify
the baseline, API receipt and recorded observation. A recorded observation must be
fresh and strictly newer than both the baseline and write acceptance.
For a numeric setpoint test, wait for the desired live reading and use
**Record current read values** to replace the retained after snapshot. This reads
the current telemetry only; it sends no command and does not certify a mapping
or resume interrupted completion monitoring.

For a configured mapping, **EXPECTED FEEDBACK OBSERVED** means a newer API snapshot
reports the expected value, after a baseline that did not already have it. This
records API evidence; observe the physical equipment as well. An already-set signal
stays **ALREADY SET BEFORE WRITE**. Candidate mappings stay **NEEDS CONFIRMATION**,
and no completion mapping is inferred for a manual reset to 0 or a numeric setpoint.
Those writes can still record the surrounding read signals. No automatic reset,
retry or second write is performed.

Feedback history retains the last 50 manual requests in this browser, separately
for each API and mock/real mode, with no credential or write token. Select the
original writable tag and its **Write record** to revisit its evidence, including
batch records containing that tag. Reload, stale or disconnected data, leaving
Remote mode, or a subsequent manual value write interrupts unfinished completion
observation; it cannot resume and claim a transition across that gap. Completed
records remain available. A blocked or uncertain write is retained as such, with
no invented readback. **Export feedback JSON/CSV** saves all retained records and
their read values; these browser records are separate from the backend log and
are lost if browser data is cleared. Export them before clearing browser storage.

The command list above the active test shows writable Bool bits at 1 and commands
that still need a verified 0. Click **Send 0…** beside a command. The single
confirmation identifies that tag, its address and current value. This works
without an active feedback test, including after a reload. Clear results show
API acceptance and later verified 0 separately. Clearing another command does
not replace the current test result or elapsed time. Cleanup records do not
invent a previous Send 1.

All 50 feedback tests default to **15 seconds**. Set **Wait limit (seconds)**
to a whole number from 1 to 300 before a run. The confirmation shows that limit.
Changing the field during a run affects the next test only. The active result
and logs retain the captured limit. Timeout does not stop equipment or clear a command.

Use the same tank dropdown as Manual 0/1. Search by pair, signal or address.
Filter **Your result** by Pass, Fail or Not checked. All 50 pairs remain mounted
and available through the filters. The left list shows saved human marks as
labels, without coloring the card borders.
Select a pair to review its live details on the right. Selection sends nothing.
Use **Run selected test** or its Run shortcut for the explicit confirmation.

Manual 0/1 and Feedback use one page scrollbar. **Choose another command/pair**
returns to the existing search field without changing your saved results.
Keyboard selection moves focus to the selected workspace. Polls and late replies
never steal focus.

You can start a different command while another waits for feedback. Use **Test
run** to select each ongoing or finished run. The selector shows its phase and
command. **Request elapsed** belongs to that selected run. Its captured wait
limit, mode, API result and human result stay separate. A later reply never
changes your selected run or moves focus.

A pending or uncertain command stays visible and blocks conflicting requests,
not unrelated commands. Explicit Send 0 remains available during its wait.
Once that clear is dispatched, the old observer cannot award PASS from later
feedback. A clear blocked before dispatch does not interrupt observation.
No command is cleared or retried automatically. Brief simultaneous dispatches
can be rejected as busy. The console does not queue them for later execution.

After checking the equipment, choose **Not checked**, **Pass**, or **Fail** in
**Your result** on the active card. Each change saves immediately. There is no
Save button or PLC write. You can correct the choice later. Pass marks the
shared checklist record complete. Fail records an issue. Not checked removes
that decision. API PASS, OBSERVED or TIMEOUT and the API timer stay unchanged.
A prior API cycle or clear never becomes a human Pass automatically.

The Feedback confirmation initially selects **Hold 1** only for a manual-based
Hold suggestion. Doors and commands without a clear suggestion start on
**Manual 0**. Review the qualified source and change a non-door choice if needed.
The suggestion does not certify the command rule or trigger a write. The
separate Manual 0/1 page retains its Manual 0 default.

Setpoints & batch uses the same autosaved **Not checked / Pass / Fail** choice
for the selected write or batch record. It changes no API result or read snapshot.
A valid earlier completion timestamp remains Pass. API success alone remains
Not checked. Explicit Fail or Not checked overrides that earlier human choice.

Human decisions stay in this browser for the selected API and real/mock mode.
Both exports include `operator_result` and `operator_result_at`. Checklist
exports include separate `api_result`. Value-feedback exports keep the API
`result` column and add the human result and decision history. Server communication
logs contain API evidence only.

To run a command/feedback case, first enable write test mode, then click **Run selected test** and check its command, expected feedback and end-state choice in the single confirmation. Configured door cases retain their mapping status. The 36 manual-derived non-door pairs are labelled **MAPPING UNDER TEST** and require explicit per-run opt-in through that confirmation. A fresh matching transition returns **OBSERVED**, not a confirmed-mapping PASS; it does not promote the mapping in configuration. A direct API request without this opt-in still blocks an unconfirmed mapping. The runner blocks if feedback already has the expected value, if data is stale, or if `Remote` is not active. Independent feedback tests can wait in parallel. Actual write dispatches stay serialized. The same command, aliased addresses, opposing door commands and shared feedback resources remain protected. Disabling write mode blocks commands still in validation and any configured reset not yet dispatched. PASS requires fresh feedback from a newer snapshot at or after command acceptance; late feedback produces TIMEOUT. Tests never start automatically. No automatic command reset is configured in the initial cases.

The **Active test & result** card stays in the right workspace. After confirmation
it shows RUNNING, the command, expected feedback, current API feedback, freshness and
supplier timestamp. Live values continue updating while the backend test runs;
matching the expected live value does not itself award PASS. The returned backend
result, recorded actual feedback and elapsed time are shown separately. The panel
receives focus when a test starts; completion does not move you away from another
sidebar page or steal its keyboard focus.

A green PASS confirms API feedback, not command clearing or physical safety.
**OBSERVED** retains the manual-derived mapping-under-test status. The card also
shows current command readback. Choose **Hold 1** or **Manual 0** in the compact
**After 1** control in a non-door test's confirmation. A qualified manual Hold
hint selects the initial mode. Doors and absent hints start on Manual 0. For Hold, accepted 1 and a later fresh command
readback of 1 record your local Keep decision, with no repeated write or claim
about physical operation.

For the known Tank 01 procedure, wait for physical movement to finish, then click
**Send 0…** on the same Feedback tests card. Your single confirmation names the
**same command tag**, address and value 0; Cancel sends nothing. Non-door manual-0
tests use your chosen procedure rather than borrowing Tank 01's door rule.
Clearing DoorOpenRemote is different from commanding DoorCloseRemote. Other
procedures remain unconfirmed unless separately established.

Clear acceptance, later verified command 0, and the original test result are
shown separately. Verification requires a poll strictly newer than the browser
baseline, final pre-clear backend snapshot and clear receipt; cached or missing
evidence cannot qualify. The test result and elapsed time stay unchanged. A
failed or uncertain clear stays visible for manual inspection; it does not retry.
No automatic clear or pulse is added.

Use Log & export to choose all, communication, or test entries, then export CSV or JSON. The log includes UTC timestamps and an expandable technical detail for each entry. Do not interpret mock results as real PLC qualification.


## Shared write controls and source limits

Enable or disable application write mode beside **Refresh now**. The compact
badge shows WRITE MODE OFF/ON. MONITORING READY means reads are healthy. READY
TO TEST also requires application write authorization. PLC Remote remains a
separate hardware readback. Disabling application writes does not stop equipment.

The shared **Command bits** bar appears on Feedback, Manual 0/1 and Setpoints &
batch. Recorded Hold 1, Waiting for API, Needs 0 and Untracked 1 describe request
intent. Live readback is shown separately. A changed or missing address stays
visible as Needs review and cannot be cleared to a different current address.
Send 0 confirmation names the captured tag/address, recorded plan and source.
Value 0 does not guarantee that other PLC logic stops equipment.

For Bool values, choose **0** or **1**. Other engineering values keep numeric
input. Review displays the chosen value and signal identity. A changed selection,
address, type, permission, API or real/mock context blocks the old confirmation
and requires review again.

All 50 feedback pairs use command/status tags listed in the supplier manual.
The reviewed manual and OpenAPI do not define a full command-to-feedback truth
table, polarity, deadline or reset sequence. The app's 14 Local pairs and 36
mappings under test are local classifications. A user-marked Pass records an
operator-verified physical result, not supplier document sign-off. The operator
reports all door pairs tested and all marked Pass pairs checked by eye. Failed
pairs remain failures; the program does not guess another mapping or sequence.

Read live values as live values. Recorded API results and timers describe the
saved observation. A later live 0 does not erase an earlier recorded match.
Future backend results and logs include command_readback, Remote and Local from
the same feedback snapshot. Older results without those fields stay unknown.
The supplied batch schema returns `results` and `count`; complete acceptance
requires every requested item to match and explicitly report written=true.

## Saved signal results and API pass

All three write pages show **API pass / API fail / Unchecked**, with an independent
human result. Use the API result filter to find failures, unchecked signals, or
API passes that still need a human check. Automatic API pass requires fresh later
readback and verified restoration, plus mapped status where available. Auto-bit
readback alone does not prove equipment operation.

Use the compact **API result** and **Human result** fields to correct a saved
signal result, even without a new write attempt. Changes save immediately in this
browser and send no command. **Use API evidence** removes a manual API override.
The source and latest automatic result remain visible. A human Pass can backfill
API pass, but an older human Pass does not hide a newer automatic API failure.

**New attempt** starts a new unjudged attempt; it keeps the signal's saved Pass or
Fail. A blank new attempt and a temporary result-refresh failure never reset your
saved judgment. Explicitly choose Not checked or Unchecked to reset it. The
Active test result belongs to that attempt; the compact saved fields belong to
the signal. Export JSON to retain the manual decision audit as well as attempts.

For the 26 October hardware run and outstanding tests, see
[API first-pass notes](api-firstpass-2026-10-26.md). For documented and unknown
conditions, see [prerequisites](api-prerequisites-2026-10-26.md).


Explicit operator-confirmed CLI results can also appear in the saved Human result.
They retain their source, original observation time and metadata. Later browser
corrections take precedence. Refresh the page after an import; no PLC write is
needed. Imported judgments are included in JSON exports. See the
[26 October human-run review](human-run-review-2026-10-26.md).
