# TeamRadar Telegram gateway

This service connects the private hosted dashboard to your own Telegram user account. The hosted dashboard alone cannot join groups, scan admins, write Sheets or send messages. It requires this persistent Python service, Telegram credentials and phone verification. Telegram and Google connections require your own credentials.

1. Create your API ID and API hash at https://my.telegram.org (not a BotFather token).
2. Deploy the repository as a Python web service on Render or a VPS. Install `pip install -r backend/requirements.txt`. Start `python -m uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}`. Use a single worker/instance.
3. Set environment variables: DASHBOARD_KEY (a long random secret), SITE_ORIGIN (exact dashboard origin). Set DATA_DIR to a persistent private disk path. Telegram session files grant account access: protect the disk. Free services without persistent storage lose login and records on restart.
4. Open Connections in the dashboard. Enter your HTTPS gateway URL and dashboard key. Connect, add your Telegram API ID and API Hash with Save Telegram API, request a phone code, enter it and complete 2FA if required. Keys are held only in browser session memory; reconnect after reloading.
5. For Sheets, create an actual Google spreadsheet. Enable the Google Sheets and Drive APIs in a Google Cloud project, create a service account and set GOOGLE_SERVICE_ACCOUNT_JSON to its JSON credentials on the server. Share the spreadsheet with the JSON client_email as Editor. Paste its URL in Connections and save. Sync writes to a dedicated TeamRadar tab; it replaces that tab's content and preserves existing checkbox state by Contact ID.
6. To send from sheet checkboxes, paste sheet-trigger.gs into Extensions > Apps Script in that spreadsheet. Add script properties GATEWAY_URL and DASHBOARD_KEY. Create an installable On edit trigger for teamRadarOnEdit and authorize it. Clicking a checkbox in column G sends the saved custom message to that contact. Script and API edits do not fire this trigger; manual single-cell edits do. Programmatic changes never trigger a bulk send.

Titles are read from Telegram, never inferred from names or biographies. Hidden channel admins and anonymous identities cannot be recovered. Join approval can be pending. No bypass of visibility, paid-message restrictions, or Telegram limits. Contact failures remain visible; FloodWait pauses require manual retry. One successful message per Contact ID is enforced. An uncertain send is blocked until reviewed in Telegram. Delivery scope is per contact per group. Do not run several gateway workers against the same database/session. Use a dedicated private service, TLS and a unique strong key; there is no multi-user tenancy.

Dashboard sample data is fictional and clearly labeled. Demo selections never contact Telegram. Real sends require a saved template and an authorized user session.

API ID and API Hash can now be entered directly in Connections after connecting your gateway. They are saved on the private server disk and never returned by the status API. Replacing API credentials requires disconnecting an existing Telegram login first. Environment variables remain an optional alternative.

The gateway download is a self-contained copy: app.py can serve its included dist/ folder. Run `python -m uvicorn app:app` from the extracted folder and install `requirements.txt`. For the GitHub repository layout use `python -m uvicorn backend.app:app` instead.

V2 supports three independent slots. Select Account 1, 2 or 3 in Connections before entering API and phone details. In Compose choose the sender and DM/group mode, select recipients and click Send message. Limits are 15 DM attempts and 30 group attempts per Telegram identity per IST day. The 10/day target is manual progress, not a scheduler. Sheet checkboxes use the saved template and sender. Preserve DATA_DIR to retain limits and Telegram sessions.
