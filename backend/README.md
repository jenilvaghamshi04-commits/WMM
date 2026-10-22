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

V2 supports three independent slots. Select Account 1, 2 or 3 in Connections before entering API and phone details. In Compose choose the sender and DM/group mode, select recipients and click Send message. Limits are 15 new DM recipients and 30 group attempts per Telegram identity per IST day. The 10/day target is manual progress, not a scheduler. Sheet checkboxes use the saved template and sender. Preserve DATA_DIR to retain limits and Telegram sessions.

WMM Team v3 adds dashboard login: admin / DASHBOARD_KEY by default, or configure DASHBOARD_USERNAME and DASHBOARD_PASSWORD. Saved data and Sent messages are separate app pages. Follow-ups use the original sender, share its sending delay and remain in delivery history. Repeat DMs do not use additional new-recipient slots. Bot admins are excluded.


Automatic replies (v3.4): deploy the latest commit, then choose a token/exchange and enable automatic yes / no replies in a new Saved data send preview. The gateway must remain online to detect incoming replies. Clear yes replies send the pitch then the demo/call invitation; clear no replies send the free-demo offer once. Edit all five texts in Message templates, pause globally there, or pause a pending contact in Lead / replies. New enrollments snapshot the selected context and texts; older conversations remain unarmed. Failed/uncertain automated deliveries stop for review. Existing Telegram waits and daily recipient limits remain enforced.


## Automatic three-day follow-up and complete message library (v3.5)

Message templates now lists all five messages in one library: introduction, three-day/manual follow-up, yes pitch, yes call invitation, and no free-demo offer. Every card has an editor, default reset and personalized preview; navigation links at the top jump directly to any card. The global three-day-follow-up switch is saved with templates. Deploy this commit on Render to update its dashboard and backend together.

The gateway automatically schedules one follow-up 72 hours after the first confirmed DM, including existing unreplied conversations. It uses the saved follow-up template and the original token/exchange. It does not repeat every three days. Before sending, the original account must finish a fresh reply-history check; incomplete or unavailable history waits. Any detected reply, a progressed lead (Replied/Meeting/Proposal/Client), or an already confirmed follow-up stops the scheduled send. A paused lead reminder also pauses its automatic follow-up. Group posts are excluded.

All follow-ups and automatic yes/no replies use the original Telegram identity. Moving that identity to another account slot is supported; replacing its slot with a different account never authorizes a send. The server checks the parent recipient/sender and first DM sender under its delivery lock. If the original account is disconnected, jobs wait without switching identity. The gateway must remain online; overdue eligible jobs resume after reconnect. Daily quotas, Telegram waits, uncertain-delivery protection and existing duplicate safeguards still apply.

SQLite persists each scheduled job and fixed request ID. A confirmed send survives a restart without being repeated; failed or uncertain attempts stop for review. Saved data and Lead / replies display status, due date and the original sender. `POST /templates` accepts optional `auto_followup_enabled` (default true); older template/config updates preserve it. `/status` advertises `automatic_followups` and `original_sender_lock`, and includes an `auto_followup` summary on DM leads.


Positive reply folder routing: a clear yes (including yeah/yeh) moves the conversation to 🟡 on its original Telegram account and keeps it there after the automatic pitch, call invitation, or later outgoing messages. The shared routing queue enforces this rule. Startup and folder-sync seeding also repair existing positive conversations that an older version moved back to 🔵. Repeated repair checks do not requeue an already-yellow route, and folder updates never resend messages. Other reply routing behavior remains in place.


One-time automatic response: a clear yes sends exactly one pitch and one separate call invitation, then permanently disables that conversation’s automatic reply enrollment. Both messages use the original sender and the chat stays in 🟡. Later yes/no replies, template edits, rescans, restarts, or pause/resume requests cannot restart a completed response. The control endpoint rejects resuming terminal sequences; partial failed/uncertain deliveries retain their review requirement. Existing completed sequences are disabled during upgrade without sending anything. The three-day no-reply follow-up stays stopped after any detected reply. Lead cards show “Sent once · automation stopped” after completion.


## Telegram-style Replies page and workspace reset (v3.6)

The Replies page previews chats with received replies, with a searchable chat list, original-sender account filter, and incoming/outgoing message bubbles. Conversations remain separated by Telegram sender identity and recipient, including duplicate scans. It shows delivery status and errors, original messages, automatic response parts, follow-ups and up to 20 recent received replies from each lead. Newest chat activity and newest messages appear first by default; choose Oldest message first for chronological reading. No message is sent from this preview. Light/dark themes, live refresh and Lead / replies remain available.

Connections → Reset workspace data provides a count preview and requires typing `RESET DATA`. Authenticated `GET /workspace/reset-preview` previews counts; authenticated `POST /workspace/reset` requires `confirmation: "RESET DATA"` and a unique `request_id`. The operation clears saved contacts, outgoing/received-message history, lead settings, quota-reset records, reply sync, app folder queues/cache, and automatic-reply/follow-up queues. Browser activity and selections clear after success. Telegram accounts/sessions, API credentials, message templates/settings, workspace login and Telegram-imposed waits are preserved. App daily usage and duplicate history reset; Telegram chats and connected Google Sheet contents remain unchanged.

Reset waits for active sends and automation workers, clears all scoped tables in one transaction, and uses a persisted request ID so retrying a timed-out reset cannot delete records created after its first success. Stale reply checks cannot recreate cleared reply-sync rows. Deploying this code does not itself reset live data: invoke the authenticated reset action on the live gateway. `/status` advertises `workspace_reset` and `reply_inbox`. The downloadable gateway includes all inbox assets.


## External ten-minute Render keep-alive

`.github/workflows/keep-alive.yml` schedules a lightweight public `/health` request every ten minutes (minutes 7, 17, 27, 37, 47 and 57). GitHub runs the job outside the Render service and independently of any open dashboard. It also supports Run workflow and checks on changes to the health-check configuration/script. No dashboard key, Telegram credentials or message-sending endpoints are used; the job has read-only repository permissions and a five-minute timeout.

Activation requires the exact public WMM Render URL. Set `gateway_url` in `config/keep-alive.json`, for example `https://YOUR-SERVICE.onrender.com`, or add repository Actions variable `WMM_GATEWAY_URL` with that value. The variable takes precedence. The target is intentionally blank until the correct URL is supplied; an unconfigured job logs a setup notice and makes no external health call. Do not use another project's Render URL. Open WMM → Actions → WMM server keep-alive to run/check the workflow. Connections shows the connected gateway's health URL, a copy button and Check server now.

`scripts/ping_gateway.py` accepts only public HTTPS `.onrender.com` service roots or `/health` URLs, rejects embedded credentials/query parameters/other paths, verifies a healthy WMM JSON response, and retries cold starts up to three times within the job's timeout. The health endpoint sends Cache-Control: no-store and returns only service/health/version data. The scheduler never sends Telegram messages or changes application data. A public service URL in the config is not a credential.

GitHub scheduled runs are best-effort and may be delayed or dropped; public-repository schedules can be disabled after 60 days without repository activity. Render's free plan still has restarts and monthly usage limits. This reduces idle spin-down risk; it does not guarantee continuous uptime or make local SQLite/session storage persistent across Render restarts. Official references: https://render.com/docs/free and https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule .

## v3.7: message spacing and imports

Deploy the latest commit, installing `backend/requirements.txt` as usual. No new environment variables are required for uploaded CSV/TSV/XLSX imports. Google Sheets imports reuse `GOOGLE_SERVICE_ACCOUNT_JSON`; share the source sheet with its client email as Viewer. The Google importer reads only a bounded range on the requested tab (or the first tab) and never changes that sheet.

Authenticated endpoints:
- `POST /sending-pace` with `delay_seconds` of 120, 300 or 600. Default 120 seconds; no disabled/zero-delay mode.
- `POST /contacts/import/read` with either `filename` + `content_base64`, or `sheet_url` + optional `worksheet`.
- `POST /contacts/import/preview` with returned rows, chosen zero-based column mapping, `has_header`, and optional `default_kind` (`dm` / `group`). Returns reviewed rows and a batch ID expiring after 30 minutes.
- `POST /contacts/import/confirm` with `batch_id` to add valid unique contacts. Rechecks duplicates at confirmation and consumes the batch once.

A local cooldown responds with HTTP 429 and `detail.code=send_cooldown`, `retry_after`, and `next_available_at`; this is the only send response the dashboard waits and retries automatically. Telegram FloodWait/PeerFlood, daily caps, uncertain delivery, and other errors stop the action. Every send path shares the persisted cooldown keyed to Telegram identity. Reset actions preserve cooldowns. Existing Render free ephemeral-storage limits still apply; keep `DATA_DIR` durable for restart-safe records across host replacement.

## v3.8: five template options per type

`POST /templates` accepts `template_variants`, a dictionary using the existing five template keys (`template`, `followup_template`, `yes_pitch_template`, `yes_demo_template`, `no_reply_template`). Each key has exactly five strings, up to 4,096 characters per slot. Blank slots are skipped; every type needs one non-empty option. Legacy scalar fields remain supported and reflect the first non-empty slot. Legacy edits change option 1 while preserving alternate options. `/settings` Compose edits likewise preserve options 2–5.

`/status` includes the normalized pools and `features.template_variants`. A server-side implicit initial send (including `/sheet-send`) randomly picks from the initial pool. Reviewed manual sends post their chosen text explicitly so the preview is exact. New automatic enrollments independently choose a yes pitch, call invitation and no offer; the dashboard sends `auto_reply_templates` containing those exact previews, and the server verifies they are still configured options before enrolling. These concrete texts are then stored with the conversation. Pending or completed old enrollments stay unchanged. Automatic follow-up workers persist one selected, personalized follow-up body before attempting delivery, so waiting/restarting never rerolls it.

Random selection does not alter sender identity, delay settings, quotas, opt-out handling, duplicate checks or once-only completion. Separate choices may select the same option consecutively. All activation still requires deploying this commit on the Render gateway; start/build commands are unchanged.
