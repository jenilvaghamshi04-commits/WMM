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

WMM Team v3 adds dashboard login: admin / DASHBOARD_KEY by default, or configure DASHBOARD_USERNAME and DASHBOARD_PASSWORD. Saved data and Sent messages are separate app pages. Follow-ups use the original sender, count against its daily limits and remain in delivery history. Bot admins are excluded.


Automatic replies (v3.4): deploy the latest commit, then choose a token/exchange and enable automatic yes / no replies in a new Saved data send preview. The gateway must remain online to detect incoming replies. Clear yes replies send the pitch then the demo/call invitation; clear no replies send the free-demo offer once. Edit all five texts in Message templates, pause globally there, or pause a pending contact in Lead / replies. New enrollments snapshot the selected context and texts; older conversations remain unarmed. Failed/uncertain automated deliveries stop for review. Existing Telegram waits and daily recipient limits remain enforced.


## Automatic three-day follow-up and complete message library (v3.5)

Message templates now lists all five messages in one library: introduction, three-day/manual follow-up, yes pitch, yes call invitation, and no free-demo offer. Every card has an editor, default reset and personalized preview; navigation links at the top jump directly to any card. The global three-day-follow-up switch is saved with templates. Deploy this commit on Render to update its dashboard and backend together.

The gateway automatically schedules one follow-up 72 hours after the first confirmed DM, including existing unreplied conversations. It uses the saved follow-up template and the original token/exchange. It does not repeat every three days. Before sending, the original account must finish a fresh reply-history check; incomplete or unavailable history waits. Any detected reply, a progressed lead (Replied/Meeting/Proposal/Client), or an already confirmed follow-up stops the scheduled send. A paused lead reminder also pauses its automatic follow-up. Group posts are excluded.

All follow-ups and automatic yes/no replies use the original Telegram identity. Moving that identity to another account slot is supported; replacing its slot with a different account never authorizes a send. The server checks the parent recipient/sender and first DM sender under its delivery lock. If the original account is disconnected, jobs wait without switching identity. The gateway must remain online; overdue eligible jobs resume after reconnect. Daily quotas, Telegram waits, uncertain-delivery protection and existing duplicate safeguards still apply.

SQLite persists each scheduled job and fixed request ID. A confirmed send survives a restart without being repeated; failed or uncertain attempts stop for review. Saved data and Lead / replies display status, due date and the original sender. `POST /templates` accepts optional `auto_followup_enabled` (default true); older template/config updates preserve it. `/status` advertises `automatic_followups` and `original_sender_lock`, and includes an `auto_followup` summary on DM leads.


Positive reply folder routing: a clear yes (including yeah/yeh) moves the conversation to 🟡 on its original Telegram account and keeps it there after the automatic pitch, call invitation, or later outgoing messages. The shared routing queue enforces this rule. Startup and folder-sync seeding also repair existing positive conversations that an older version moved back to 🔵. Repeated repair checks do not requeue an already-yellow route, and folder updates never resend messages. Other reply routing behavior remains in place.
