# User guide

Open the dashboard on the backend workstation at `http://localhost:8080`. The banner must read **READ-ONLY MODE** after every page load. **MOCK MODE** appears prominently when `PLC_MOCK_MODE=true`.

The connection panel distinguishes API connection, `Remote` mode, supplier poll timestamp, data age, and tag success/failure counts. A green connection with amber stale data is not ready for writes. Use **Refresh now** to reload metadata and the latest poll.

Use Live signals for name/description/address search and type or permission filters. Choose a tank for its catalog-defined signals. The Alarm section shows raw Bool values; the supplier must confirm polarity. In Raw tag browser, enable Advanced mode to see PLC addresses, multipliers, and limits. Read-only rows have no write action.

Both type filters include Bool, Word, SignedWord and Float. The current static mock snapshot is 362 tags (141 W, 221 R); real counts come from the live API. For Tank01_TempAdj, Advanced mode shows D4010, SignedWord, W, multiplier 0.1, low −999.0 and high 999.9. Manual write shows the same allowed range and accepts −5 or −10.5 as engineering values within those limits. No multiplier conversion is applied by this console.

The 29-SEP-2026 supplier baseline also shows Tank07_AmpereSV at D1362 with multiplier 0.1 and 0–200 A limits; Tank07 current/voltage multipliers are 0.1. SwingSV limits for Tank03/05/10/14 are 5–120 CPM. Tank16_Conductivity (D1142, Float, R, multiplier 1.0) replaces Tank16_PH; Tank09_WaterFlow is added at D1036. All eight TempAdj tags use SignedWord with −999.0 to 999.9 limits.

Health warnings display catalog differences without changing the live metadata. Export communication logs for expected/live details and supplier review. **SUPPLIER CONFIRMATION REQUIRED: Tank08_WaterFlow and Tank09_WaterFlow both use D1036 in the latest manual.** This warning permits read-only startup. Treat it as unresolved field metadata until the supplier confirms it.

For a manual write, select a writable tag, enter an engineering value, then click **Review write**. Confirm the tag, address, current value, and new value in the dialog. A supplier `written=true` response means the API accepted the request; inspect a physical feedback signal or run a configured verification test to prove effect. Batch writes use a JSON array of `{ "tag_name": "...", "value": 0 }` objects and an extra batch confirmation.

To run a command/feedback case, first enable write test mode, then click **Run test** on a configured case and confirm the command. The runner blocks if feedback already has the expected value, if data is stale, if `Remote` is not active, or if the mapping is marked as unconfirmed. Tests never start automatically. No automatic command reset is configured in the initial cases.

Use Log & export to choose all, communication, or test entries, then export CSV or JSON. The log includes UTC timestamps and an expandable technical detail for each entry. Do not interpret mock results as real PLC qualification.
