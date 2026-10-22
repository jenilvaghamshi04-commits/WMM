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
