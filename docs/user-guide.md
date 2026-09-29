# User guide

Open the dashboard on the backend workstation at `http://localhost:8080`. The banner must read **READ-ONLY MODE** after every page load. **MOCK MODE** appears prominently when `PLC_MOCK_MODE=true`.

The connection panel distinguishes API connection, `Remote` mode, supplier poll timestamp, data age, and tag success/failure counts. A green connection with amber stale data is not ready for writes. Use **Refresh now** to reload metadata and the latest poll.

Use Live signals for name/description/address search and type or permission filters. Choose a tank for its catalog-defined signals. The Alarm section shows raw Bool values; the supplier must confirm polarity. In Raw tag browser, enable Advanced mode to see PLC addresses, multipliers, and limits. Read-only rows have no write action.

For a manual write, select a writable tag, enter an engineering value, then click **Review write**. Confirm the tag, address, current value, and new value in the dialog. A supplier `written=true` response means the API accepted the request; inspect a physical feedback signal or run a configured verification test to prove effect. Batch writes use a JSON array of `{ "tag_name": "...", "value": 0 }` objects and an extra batch confirmation.

To run a command/feedback case, first enable write test mode, then click **Run test** on a configured case and confirm the command. The runner blocks if feedback already has the expected value, if data is stale, if `Remote` is not active, or if the mapping is marked as unconfirmed. Tests never start automatically. No automatic command reset is configured in the initial cases.

Use Log & export to choose all, communication, or test entries, then export CSV or JSON. The log includes UTC timestamps and an expandable technical detail for each entry. Do not interpret mock results as real PLC qualification.
