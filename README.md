# WMM TeamRadar

Private Telegram team discovery and selected outreach dashboard.

Live dashboard: https://teamradar-telegram-desk.jenilvaghamshi04.chatgpt.site

## Run or deploy

The repository is a complete Python app: `backend/app.py` serves both the API and `dist/index.html` on the same origin. The ChatGPT-hosted dashboard can also connect to the deployed Python API.

- Install: `pip install -r backend/requirements.txt`
- Start: `python -m uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}`
- Required environment: `DASHBOARD_KEY` (use a long random secret).
- Optional: `SITE_ORIGIN` (the ChatGPT dashboard origin), `DATA_DIR` (private persistent disk).
- Open the app, choose **Add API → Connections**, enter the deployed gateway URL and dashboard key, then connect.
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

- `dist/index.html`: responsive dashboard, clearly labeled fictional sample data until connected.
- `backend/app.py`: authenticated API, Telegram session, discovery, settings, delivery records and Sheets integration.
- `backend/sheet-trigger.gs`: installable Google Sheets On edit handler.
- `render.yaml`: Render service blueprint.
- `.env.example`: environment variable names with placeholders only.

Secrets and Telegram sessions remain on your own service's private disk. API Hash is never returned by status endpoints, exported or committed. A bot token alone cannot log in as your user account. Telegram privacy, user messaging restrictions and FloodWait limits still apply. Live Telegram and Sheets integration requires your credentials and hosting connection; it is not connected by this repository upload.

## Three-account messaging (v2)

- Connections has three account slots. Choose a slot, save its API ID/hash, request a code for its phone, verify, and repeat for the other two. Each Telegram identity has its own session and usage ledger. Account 1 preserves the previous single-account session and confirmed delivery records.
- Compose provides a sender selector and a DM / Group chat selector. Scan with the selected sender to discover team members and group destinations. Group messaging accepts group chats, not broadcast channels. Sender choice is explicit; the app does not switch accounts when a limit or Telegram restriction is reached.
- Type your message, select recipients, and click **Send message**. This button sends the current text without requiring Save first. Save message sets the template and default sender for Sheet checkbox sends. App checkbox sends use the current selected sender and saved template.
- Each actual Telegram identity has a daily goal of 10 confirmed messages (DMs plus group messages), a hard cap of 15 DM attempts and a separate hard cap of 30 group attempts. The target is a progress indicator; no unattended daily sending is scheduled.
- Caps apply server-side to all app and Sheet send paths. Every dispatched attempt counts, including failed and uncertain delivery. Counters reset at midnight Asia/Kolkata. Reconnecting or using another slot for the same identity does not reset usage. Logging the same identity into two active slots is blocked.
- Quotas are application limits, not a guarantee that Telegram will permit that many messages. Telegram restrictions stop sending; there is no automatic fallback to another account. Successful DMs are deduplicated across all senders and groups. Identical group messages are deduplicated per destination/day. Restarted in-flight messages are marked Uncertain and require review.
- Activity and CSV exports show the sender slot. Keep DATA_DIR on a persistent disk: losing the database loses counters, duplicate history and sessions. Use a single application instance/worker; this SQLite version is not for horizontally scaled deployment.

Validation: `python -W ignore -m unittest discover -s tests -q` covers three slots, sender routing, both caps, concurrent requests, date rollover, restart persistence, legacy migration, duplicate identities, Telegram pauses and Sheet sending.

## Leave after scan

The optional **Leave group after successful scan** checkbox is off by default. When enabled, only the selected scanning account leaves, after at least one visible human admin record and the group record are saved. Failed scans and scans with zero collected admins do not leave. Leaving failures are returned separately from the successful scan, so saved records remain accessible. Both basic groups and supergroups/channels use their respective Telegram leave methods. Group messages from an account marked as left are blocked until it rejoins and scans with leaving switched off. Other accounts are unaffected. DMs remain subject to Telegram privacy and messaging restrictions.

## Manual daily-limit reset

Each account card has **Reset limits**. Choose DMs, group messages, or both in the confirmation dialog. The authenticated backend requires that account to be logged in and moves its quota baseline to the current delivery ledger position. Limits remain 15 DMs / 30 group attempts, with restored remaining allowance since the manual reset. The daily target also reflects confirmed sends since the applicable reset. Other accounts and unselected message types are unchanged. Midnight IST resets still apply. Resets are stored in an audit table and shown in Activity; delivery history, cross-account duplicate protection and Telegram-imposed pauses are never erased. Repeated requests with the same request ID are idempotent. A persistent DATA_DIR and one application worker are still required.
