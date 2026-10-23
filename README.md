# WMM Team

Private Telegram team discovery and selected outreach dashboard.

Live dashboard: https://teamradar-telegram-desk.jenilvaghamshi04.chatgpt.site

## Run or deploy

The repository is a complete Python app: `backend/app.py` serves both the API and `dist/index.html` on the same origin. The ChatGPT-hosted dashboard can also connect to the deployed Python API.

- Install: `pip install -r backend/requirements.txt`
- Start: `python -m uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}`
- Required environment: `DASHBOARD_KEY` (use a long random secret).
- Optional: `SITE_ORIGIN` (the ChatGPT dashboard origin), `DATA_DIR` (private persistent disk).
- Open the app, choose **Log in → Connections**, enter the deployed gateway URL and dashboard key, then connect.
- Add your **Telegram API ID and API Hash** directly in Connections. Get these from https://my.telegram.org. Then request a phone login code and complete Telegram login. Do not publish these secrets in GitHub or send login codes through chat.
- Alternatively set TELEGRAM_API_ID and TELEGRAM_API_HASH on the server before startup.

`render.yaml` provides a free Render deployment blueprint. It does not deploy automatically just because the files are on GitHub. Deploy it from your connected Render account. The free plan has no persistent disk: it can sleep and its Telegram login, saved API credentials, contacts, and delivery history can disappear on redeploy/restart. For durable use, choose a persistent-disk-capable plan and set DATA_DIR to that disk. Do not scale to multiple workers/instances with this SQLite/session setup.

## Workflow

1. Connect the gateway and Telegram user account.
2. Enter a Telegram group username/link. Enable **Join before scan** if you want your account to join that specific group.
3. Read visible administrators and their exact custom titles. Owner, Admin, CTO, BD and Moderator are only shown when supported by the visible Telegram role/title. Hidden channel administrators cannot be recovered. Join requests may require approval.
4. Save a custom message. Supported placeholders: `{{name}}`, `{{role}}`, `{{group}}`.
5. Select contacts and click Send, or enable **Send saved message when I check a contact** for immediate checkbox sends. One confirmed message per contact/group is enforced; failures are shown. Uncertain deliveries are blocked for manual review.
6. Optional: connect a real Google spreadsheet, sync, and install the included Apps Script for sheet checkbox sending.

Google setup and trigger instructions are in `backend/README.md` and in the app's Connections page. The original supplied Google Doc URL is not a spreadsheet and cannot be used for checkbox rows.

## Files

- `dist/index.html`: responsive dashboard with three real account slots and an empty directory until connected.
- `backend/app.py`: authenticated API, Telegram session, discovery, settings, delivery records and Sheets integration.
- `backend/sheet-trigger.gs`: installable Google Sheets On edit handler.
- `render.yaml`: Render service blueprint.
- `.env.example`: environment variable names with placeholders only.

Secrets and Telegram sessions remain on your own service's private disk. API Hash is never returned by status endpoints, exported or committed. A bot token alone cannot log in as your user account. Telegram privacy, user messaging restrictions and FloodWait limits still apply. Live Telegram and Sheets integration requires your credentials and hosting connection; it is not connected by this repository upload.

## Three-account messaging (v2)

- Connections has three account slots. Choose a slot, save its API ID/hash, request a code for its phone, verify, and repeat for the other two. Each Telegram identity has its own session and usage ledger. Account 1 preserves the previous single-account session and confirmed delivery records.
- Compose provides a sender selector and a DM / Group chat selector. Scan with the selected sender to discover team members and group destinations. Group messaging accepts group chats, not broadcast channels. Sender choice is explicit; the app does not switch accounts when a limit or Telegram restriction is reached.
- Type your message, select recipients, and click **Send message**. This button sends the current text without requiring Save first. Save message sets the template and default sender for Sheet checkbox sends. App checkbox sends use the current selected sender and saved template.
- Each actual Telegram identity has a daily goal of 10 confirmed new DM recipients plus group sends, a hard cap of 15 new DM recipients and a separate hard cap of 30 group attempts. The target is a progress indicator; no unattended daily sending is scheduled.
- Caps apply server-side to all app and Sheet send paths. Each new DM recipient reserves one slot; repeated attempts to that recipient do not reserve another. Group attempts count individually, including failed or uncertain delivery. Counters reset at midnight Asia/Kolkata. Reconnecting or using another slot for the same identity does not reset usage. Logging the same identity into two active slots is blocked.
- Quotas are application limits, not a guarantee that Telegram will permit that many messages. Telegram restrictions stop sending; there is no automatic fallback to another account. Successful DMs are deduplicated across all senders and groups. Identical group messages are deduplicated per destination/day. Restarted in-flight messages are marked Uncertain and require review.
- Activity and CSV exports show the sender slot. Keep DATA_DIR on a persistent disk: losing the database loses counters, duplicate history and sessions. Use a single application instance/worker; this SQLite version is not for horizontally scaled deployment.

Validation: `python -W ignore -m unittest discover -s tests -q` covers three slots, sender routing, both caps, concurrent requests, date rollover, restart persistence, legacy migration, duplicate identities, Telegram pauses and Sheet sending.

## Leave after scan

The optional **Leave group after successful scan** checkbox is off by default. When enabled, only the selected scanning account leaves, after at least one visible human admin record and the group record are saved. Failed scans and scans with zero collected admins do not leave. Leaving failures are returned separately from the successful scan, so saved records remain accessible. Both basic groups and supergroups/channels use their respective Telegram leave methods. Group messages from an account marked as left are blocked until it rejoins and scans with leaving switched off. Other accounts are unaffected. DMs remain subject to Telegram privacy and messaging restrictions.

## Manual daily-limit reset

Each account card has **Reset limits**. Choose DMs, group messages, or both in the confirmation dialog. The authenticated backend requires that account to be logged in and moves its quota baseline to the current delivery ledger position. Limits remain 15 DMs / 30 group attempts, with restored remaining allowance since the manual reset. The daily target also reflects confirmed sends since the applicable reset. Other accounts and unselected message types are unchanged. Midnight IST resets still apply. Resets are stored in an audit table and shown in Activity; delivery history, cross-account duplicate protection and Telegram-imposed pauses are never erased. Repeated requests with the same request ID are idempotent. A persistent DATA_DIR and one application worker are still required.

## Live workspace display

The dashboard contains no sample contacts or demo labels. Three real account slots are available; each shows Not connected until Telegram login succeeds. Only the connected gateway supplies contacts, delivery history and usage. Offline counters are marked unavailable, and messaging requires an authorized selected account.

## WMM Team login, saved data and follow-ups (v3)

- The app is branded WMM Team and includes a native SVG favicon. Its existing hosted URL and Google Sheet tab name `TeamRadar` remain compatible.
- Log in using the deployed server URL, username `admin`, and your existing DASHBOARD_KEY. Optionally set DASHBOARD_USERNAME and DASHBOARD_PASSWORD in your hosting environment to use a different login. No password is committed to source control. Dashboard login is separate from the three Telegram logins.
- The server issues a 12-hour bearer session; only its SHA-256 hash is stored. Passwords and tokens are not saved in browser storage. Log out revokes the session without disconnecting Telegram. Failed logins are rate-limited. The original DASHBOARD_KEY remains supported for the Sheet trigger and existing integrations.
- **Find team** scans groups and composes messages. **Saved data** stores and lists real contacts/groups. Choose recipients there, then return to Compose. Bot admins are skipped during scanning and flagged bots cannot be messaged.
- **Sent messages** shows recipient, username, original sender account, message text, delivery time and status. New sends store these details durably. Earlier records are preserved; their message text cannot be reconstructed and is labeled unavailable.
- A **Send follow-up** button appears for confirmed sent records. It sends the custom follow-up from the original Telegram identity, checks its current quota and Telegram restrictions, and records a linked delivery. Swapping another identity into the old account slot does not authorize it to follow up. Repeated requests with the same ID do not send twice. Identical previously sent text is blocked; uncertain deliveries need review. Follow-ups are manual, not scheduled.
- Deploy the latest GitHub commit on Render before using the new login endpoint. A persistent DATA_DIR is required to keep contacts, history, sessions and quotas across Render restarts.

## Direct messaging on Saved data and account health

Saved data now has per-row Send message, Send follow-up and Preview / history actions. Initial message dialogs include their own sender selector, editable text and personalized preview. Follow-up dialogs preview the text and use the original sender. Both actions refresh statuses on the current page without navigating away; Sent messages keeps the same follow-up action. Rows show the latest status, sender/time, total confirmed sends and confirmed follow-up count. Recipient history is matched by Telegram identity across scanned groups, so an existing send is visible on duplicate contact rows too. Uncertain deliveries block more sends until reviewed. DM and group lists can be selected directly on Saved data.

Account health displays the three accounts' API configuration, Telegram connection and login status, DM/group allowances, actual confirmed sends today, failed attempts, unresolved uncertain deliveries, last successful send, latest recorded error and known pause expiry. Refresh health checks the current sessions and stored records. It is not an external Telegram ban/reputation diagnosis. Quota resets do not erase actual delivery/error history.

Additional frontend state checks: `node tests/test_message_model.cjs`.

## Recipient-based DM counting and token introductions (v3.1)

Sent messages now groups the original message and all follow-ups into one conversation row per Telegram recipient and message type. The original message, latest follow-up and counts are shown together; full delivery history remains in Preview / history. Saved data still switches its primary action from Send message to Send follow-up after a confirmed send.

The WMM introduction preset uses the supplied wording with automatic `@username` and a Token name / symbol field. `LF` or `$LF` produces `$LF`. If no public username exists, the greeting uses the saved display name. `{{name}}`, `{{role}}`, `{{group}}`, `{{username}}` and `{{token}}` are supported too. Token placeholders require a valid token symbol before sending. The exact personalized text and token symbol are saved with each delivery; follow-ups inherit the conversation's token but can edit it. The backend validates and performs the same substitutions as the preview. The browser blocks token/username placeholders when connected to an older backend without that capability.

The 15-per-day DM allowance now counts new recipient identities per sender, not message attempts. Initial failed/uncertain attempts reserve one new-recipient slot; retries to that same target use the same slot. Once a recipient has a confirmed DM from that sender, subsequent messages/follow-ups do not consume new-recipient slots, including on later days and when the new-recipient allowance is full. New recipients remain capped; duplicate protections, uncertain-delivery checks and recorded Telegram pauses are still enforced. The 30-per-day group attempt cap is unchanged. Daily target progress counts confirmed new DM recipients plus confirmed group sends; Account health retains the separate actual sent-message total. Manual quota resets and IST rollover remain supported.

## Editable message templates and separate delivery statuses

Message templates lets you view, edit and preview both the initial message and the supplied WMM follow-up. Save both to persist them on the gateway; Saved data and Sent messages also link to this option. Initial-message dialogs load the saved initial text by default, with the built-in WMM introduction and current Compose text available as alternatives. Follow-up dialogs load the saved follow-up automatically. All text remains editable before sending, with username and token personalization in the preview.

Authenticated `POST /templates` updates both texts without changing spreadsheet, token or sender settings. Existing `/settings` saves preserve the follow-up template. Saved data and Sent messages show separate Message and Follow-up badges: Sent only after confirmed delivery, otherwise Not sent. Failed, sending and uncertain attempts appear alongside their applicable badge; a later failed follow-up never hides an earlier confirmed introduction or follow-up. Historical delivery text is unchanged by template edits. Deploy the latest gateway commit on Render to enable saving both templates.

## Newest activity first

Saved contacts and CSV exports sort by the latest scan or message/follow-up attempt for the recipient. Sent conversations and their history sort newest first. Activity merges local events, server deliveries and quota resets by their original timestamps before formatting dates. Account cards in the workspace and Account health sort by their latest scan, send, error or quota reset; routine health polling does not change their order. Connection selectors retain stable account numbers. Gateway contact responses and Google Sheets scans are newest first, with legacy undated rows last.

## Light and dark themes

Use the Light/Dark switch on the login screen or workspace header. The workspace follows the device theme until a choice is saved, then remembers the selection in this browser and synchronizes it across open tabs. All pages, forms, dialogs, previews and status colors share the theme palette. Theme preference is separate from login and Telegram account data.

## Reply detection, reminders and lead pipeline (v3.2)

Lead pipeline groups canonical Telegram recipients into New, Contacted, Replied, Meeting, Proposal and Client. A confirmed send advances New to Contacted; a detected incoming DM advances New/Contacted to Replied. Later stages stay under your control. Saved data and Sent messages also show reply/stage/due badges and a Lead / replies dialog. Mark reply reviewed clears the attention flag; another reply raises it again. Duplicate scans of one person share the same lead settings and replies.

Incoming private messages are recorded only for recipients with a confirmed DM from the same Telegram identity, after the initial send. Outgoing messages, service messages, older chat history, uncontacted senders and group chatter do not count as replies. Reply bodies (up to 4096 characters), message IDs and timestamps are stored privately with the gateway database; the UI shows the latest 20 replies. Event listeners cover connected sessions. Background history checks catch missed messages while the gateway is online, checking one conversation every 15 seconds and revisiting completed checks after five minutes. Pagination processes up to 100 messages per conversation at a time; partial checks, unavailable accounts and Telegram waits remain visible and are never described as successfully checked. The server must remain running for live detection; history catch-up resumes when it is available.

Each lead can use a 3-, 5- or 7-day reminder, enabled by default at three days after the latest confirmed DM. A received reply, Client stage, a paused reminder, or an uncertain outgoing delivery suppresses the reminder. Follow-ups reset the next reminder's date only after confirmed delivery. Review due follow-up checks reply history first, then opens the editable message preview; it never sends automatically. Recipients who have replied are excluded from follow-up actions; their conversation history remains available. Reminder checks do not consume DM quota or alter existing send protection.

Authenticated endpoints: `POST /leads/update` (stage, reminder settings and review acknowledgement), `POST /replies/sync` (a lead key or a small batch). `/status` includes lead summaries and the `lead_management` capability. The dashboard refreshes records every 30 seconds while visible, preserving the current page and skipping open dialogs. All CRM UI supports the shared light/dark palette. Deploy the latest commit on Render to enable these server features. Existing contacts and message history are preserved through additive SQLite tables.

## Telegram folder routing (v3.3)

Confirmed DMs are queued for the sending Telegram account's **🔵** folder. A new incoming DM after the latest confirmed outgoing message queues that chat for **🟡** and removes it from **🔵**. Another confirmed outgoing message returns it to **🔵**, until the next reply. Telegram message IDs distinguish new replies from older history, including messages in the same second. Existing lead stages, reminder suppression and send quotas remain independent.

The gateway reuses folders with those exact emoji names, creating them when first needed. It preserves other chats, pins, folder settings and all unrelated folders; automatic source-folder rules receive only the relevant user's exclusion. Ambiguous duplicate names and shared folders produce a visible error instead of choosing an arbitrary folder. If Telegram refuses an empty explicit-only source folder, its exact settings are retained privately before removing only that empty folder; it is restored when a chat needs it again. Chats are never deleted, archived, marked read or moved out of unrelated folders.

Routing is a persistent queue, processed while the gateway runs, with sender-identity validation, per-account Telegram wait handling and restart recovery. Existing confirmed DM conversations are queued once when upgrading. A folder failure never changes a confirmed delivery, consumes another DM slot or resends a message. Saved data, Sent messages, the pipeline and Lead / replies show Pending, Synced or Needs attention, plus **Retry folder sync** in the lead dialog. Authenticated `POST /folders/sync` retries only folder changes; Telegram waits remain enforced. Deploy the latest gateway commit on Render to activate routing in the connected accounts.

## Telegram sign-in recovery

Telegram login now verifies the code before the two-step password. The password field is revealed only after Telegram accepts the code and requests 2FA; even older clients sending both values cannot skip code verification. Pending logins are isolated by account and phone, expire after ten minutes and require a fresh code after a gateway restart. Incorrect codes/passwords have specific retry messages; expired codes or rejected sessions ask for a new code without logging out of the dashboard. A rejected transport key during code requests is renewed only for that account slot, preserving API settings, contacts, messages and quotas.

In Connections, select the account, request a code, verify the latest code, then enter the Telegram two-step password only when prompted. Never paste your code or password into chat. Deploy the latest gateway commit on Render for the server fix and refresh the dashboard for the updated controls.

## Follow-up view excludes replied contacts

Sent messages defaults to **Follow-ups · no reply**, showing confirmed DM conversations eligible for a follow-up. People with a detected reply, received-reply history or a Replied stage are excluded. Use **All conversations** or **Replied** to review their original message and history. Replied recipients have no follow-up button on Saved data or Sent messages. The preview refuses to open for a replied recipient, and the dashboard refreshes reply status before confirming a follow-up; a newly detected reply closes the preview without sending. Existing conversation records remain intact.


## Exchange selection and automatic reply templates (v3.4)

Saved data → Send message now includes all 14 requested exchanges. Choose the token and exchange, review the introduction and both reply paths, and leave automatic replies enabled to arm this new DM. A clear affirmative (including yes, yeah or yeh) sends the personalized pitch followed by a separate free-demo/call message. A clear no sends the supplied free-demo offer once. Ambiguous replies do not trigger a response. Explicit stop, unsubscribe, no-thanks or not-interested replies disable the enrollment and cancel pending parts. Forwarded or pre-introduction replies cannot trigger a sequence.

Message templates contains five editable texts: introduction, manual follow-up, yes pitch, yes call invitation and no free-demo offer. `@username` uses the saved recipient handle (display-name fallback), `@TOKEN` / `$TOKEN` become the selected `$ticker`, and `{{exchange}}` becomes the selected exchange in both occurrences. Enrollments snapshot the token, exchange and templates at the initial send; later template edits affect new enrollments only. Existing conversations are never enrolled retrospectively.

One reply branch can run once per sender/recipient identity. Persistent jobs and fixed request IDs reuse confirmed deliveries after restart, and stop for failed or uncertain attempts instead of resending. Both yes parts use the original sender even if it moves to another account slot. Telegram waits, duplicate checks and the existing quota rules still apply; repeat DMs do not consume additional new-recipient slots. Lead / replies shows selected exchange, branch, sent-parts progress and errors, and allows pausing pending sequences. Message templates also has a global automatic-reply pause. Automatic detection and sending require the gateway to remain running.

`POST /send` accepts `exchange` (supported exchange key) and `auto_yes` (default false). Automatic enrollment requires a new DM with an exchange and token. `POST /templates` accepts optional `yes_pitch_template`, `yes_demo_template`, `no_reply_template` and `auto_yes_enabled`, preserving these fields for older clients. Authenticated `POST /auto-yes/update` accepts a lead `key` and `enabled`; it only updates an existing enrollment. `/status` advertises `features.automatic_yes_sequence` and includes per-lead automation summaries and each delivery's exchange/automation step. SQLite migrations preserve existing records. Deploy the latest commit on Render to enable these backend features; publishing the hosted dashboard alone does not deploy the Python gateway.


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

### Sending delay and sheet imports (v3.7)

Connections → **Message sending delay** sets a minimum gap of 2 minutes (default), 5 minutes or 10 minutes per Telegram identity. The server enforces this for all messages, including group messages, manual/automatic follow-ups, sheet checkbox sends and the two separate yes-response messages. Delays and Telegram pauses survive quota resets, workspace resets and slot changes while the data directory is retained. Telegram restrictions take priority; the app never switches senders or retries an uncertain delivery. The browser shows a countdown for reviewed sends and a **Stop pending sends** button; keep the page open for a manual batch to continue. Closing the browser stops that manual batch. A delay cannot guarantee that Telegram will not restrict an account.

Saved data → **Import sheet** accepts UTF-8 CSV/TSV and XLSX files (5 MB, 1,000 rows, 30 columns), or a Google Sheets URL. Google Sheets requires the existing gateway service account and Viewer access to the source sheet; it reads the named tab or the first tab without changing it. Reading and previewing an import never connects to Telegram or sends a message. Choose the Telegram, name, role, community and optional type columns; preview invalid/bot/duplicate rows; then confirm. New rows appear at the top of Saved data. Existing contacts and message history are preserved. Imports are deduplicated case-insensitively by public username; the real numeric Telegram ID and target type are checked when sending so aliases cannot bypass delivery duplicate checks. Imported roles remain unverified. Group links can be saved as Group chats; finding their admins still uses **Find team**. Private invite links and message links are not imported as people.

Deploy the latest GitHub commit on Render to activate v3.7 backend behavior. The dashboard blocks sends to an older backend until server pacing is available. Start/build commands remain unchanged. Source imports use `openpyxl` from `backend/requirements.txt` for Excel support.

### Five options per message type (v3.8)

Message templates has five numbered option slots for each of the five types: initial message, follow-up, yes pitch, yes call invitation, and no offer. Existing messages remain in option 1 after upgrading; the other four slots start blank. Save at least one non-empty option per type. Filled slots are selected randomly within their own type; random selection can repeat an option on consecutive contacts.

Saved-data and manual follow-up dialogs select an option once and show the exact personalized preview. You may edit it or explicitly pick another option before sending. Each automatic yes/no response part also gets its own randomly selected text, shown in the initial-send preview and saved with that conversation. The original Telegram sender, exchange and token remain attached. Existing enrolled conversations retain their previously selected texts.

Compose defaults to random saved initial options, choosing separately for each selected recipient. Preview lists the choices for the batch and keeps them fixed until the selection or saved options change. Custom Compose remains available for a deliberate shared message. Checkbox sends and sheet sends also use the initial-message options. An automatic three-day follow-up selects from the follow-up options once, stores the rendered body, and retains it through cooldowns/restarts. Existing spacing, daily limits, duplicate protection and once-only rules continue to apply.

Deploy the latest backend on Render to advertise `template_variants` and save/run all five-option settings. Changes to the template library do not rewrite delivery history or already captured automatic replies.


## Recipient timezones and affirmative-only replies (v3.9)

Automatic responses now require a clear affirmative reply such as yes, yeah or yeh. No and other replies receive no automatic response. A later non-affirmative reply cancels a pending affirmative sequence, including its second message. The negative free-demo template is removed from the current message library; the four remaining template types retain five variants each. Legacy queued negative responses are cancelled on startup, while delivery history is retained.

Saved data, Sent messages, leads and reply previews show a country when available, its source and the recipient timezone. Telegram phone-country metadata and visible phone numbers identify a phone country, not verified residence. The gateway checks one contact at most every 30 seconds and respects account restrictions without switching identity. Unknown countries remain unknown; names and language are never used to guess. Optional country and IANA timezone columns are accepted during spreadsheet import. Country and timezone can be corrected per recipient. A single-timezone country supplies an inferred zone; countries with several zones require a timezone selection.

Automatic follow-ups wait at least 72 hours after the first confirmed DM, then use the next 10:00 a.m. in the recipient timezone. Existing per-account spacing can place delivery within the 10–11 a.m. window; a missed window waits until the next local morning. IANA timezone rules handle daylight saving changes. An unknown timezone holds the job until one is supplied. The original sender, reply checks, daily limits, Telegram waits and uncertain-delivery protections still apply. Any reply cancels an automatic follow-up. The explicit Send follow-up now action remains a reviewed manual send. Deploy this backend on Render as well as publishing the dashboard to activate the new scheduler and country lookups.


## Login-code recovery (v3.9.1)

Repeated Request login code clicks reuse the active code or password step instead of triggering implicit Telegram resends. Fresh logins clear only an expired/stale Telethon code hash for that number. Delivery-unavailable responses show recovery guidance and pause requests for that phone for 15 minutes across account slots and server restarts; this is an app retry pause, not a promise that Telegram will deliver after 15 minutes. Telegram FloodWait durations are respected. Check Telegram’s service chat on an already signed-in device for codes. Deploy the updated Python gateway on Render to apply the server fix.


## Telegram QR login (v3.10)

Connections now offers Connect with QR code for accounts whose phone login code does not arrive. On an already signed-in phone, open Telegram → Settings → Devices → Link Desktop Device and approve the QR login. Two-step passwords are still required when enabled. Tokens are generated by Telegram, rendered by the gateway without an external QR service, returned only through authenticated login requests, and excluded from general account/status data. The gateway waits for approval before authorizing the selected account slot, rejects duplicate identities, and requires a manual refresh after QR expiry or network failure. The original code flow and Telegram-imposed waits remain supported. Deploy this backend on Render before using the QR button; the feature is unavailable on older gateways.


## Background sends, shuffled template cycles and inbox replies (v3.11)

When a reviewed send encounters the per-account delay, the dashboard saves it to the authenticated server queue and closes the send dialog. Pending sends on Saved data, Sent messages and Replies show the recipient, original account, message preview and earliest send time. You may close the browser tab after queue confirmation; the server worker sends when the account becomes available. Cancel an individual pending message or stop all pending sends from the same panel. An attempt already in flight may finish. A running gateway is required: a sleeping/offline gateway resumes work after waking. Use durable DATA_DIR storage on Render to preserve SQLite jobs across container replacement.

Queued messages keep their reviewed text, selected template options, token, exchange and original Telegram identity. Account changes never switch the sender. Daily quotas, Telegram waits, duplicate protection and delivery uncertainty checks remain enforced. Queued follow-ups recheck reply history and stop after a reply. Failed or uncertain attempts require review rather than automatic retry. Queue IDs link to delivery records; startup reconciles confirmed attempts without sending twice.

The four message types now rotate through distinct filled options without repeating an option until the current shuffled cycle is used. Duplicate option texts count as one. Each type has its own server-persisted rotation, shared across accounts; reviewed/queued choices are reserved atomically. Batch previews also use non-repeating cycles, and a new cycle avoids repeating its previous final option immediately. Old previews whose option was used elsewhere must be refreshed. Template edits affect future selections while queued previews remain fixed.

Replies now includes a draft, message preview and Send reply action in the selected conversation. The server derives the sender from the confirmed original DM rather than accepting a different account. Replies can also be queued during a cooldown. Manual replies appear as replies in the chat and are not counted as follow-ups. Drafts are retained while switching chats in the current session and cleared on logout/reset. Deploy this backend and refresh the dashboard to activate these features.
