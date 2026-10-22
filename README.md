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
