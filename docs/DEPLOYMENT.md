# Deployment (zero-cost first)

## Option A — GitHub Actions + static dashboard (recommended, £0)
1. Push repo to GitHub. Add secrets (all optional): `TICKETMASTER_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `GOOGLE_SHEETS_WEBHOOK`, …
2. `daily-pipeline.yml` runs at 06:00 UTC (cron is always UTC; 07:00 BST in summer). It restores `uk_etdi.db` from the `data` branch, runs the pipeline, pushes the DB + `data/export/*.json` back, sends the Telegram digest, and uploads logs as artifacts.
3. Dashboard read-only hosting: enable GitHub Pages (or Cloudflare Pages/Netlify) on the `frontend/` folder and set `window.UK_ETDI_API_BASE` to the raw `data` branch export URL — or simply run the API anywhere free (below) for full interactivity.

## Option B — Free public URL (Render / Fly / Oracle) — see **docs/DEPLOY_FREE.md** for the step-by-step guide
Any free tier that runs a container/Python app (e.g. Fly.io free allowance, Render free web service, Oracle Cloud Always-Free VM, a Raspberry Pi in the office):
```bash
docker compose up -d          # SQLite volume + SCHEDULER_ENABLED=1 daily run
```
Set `API_ADMIN_TOKEN` to protect pipeline/source/setting mutations.

## Option C — Local / office PC
`python scripts/run_pipeline.py` via Windows Task Scheduler / cron, `uvicorn app.main:app` for the dashboard on the LAN.

## Environment variables
See `.env.example`. Secrets only via env; never committed. `DATABASE_URL` switches SQLite → Postgres.

## Telegram setup
1. @BotFather → `/newbot` → token. 2. Message the bot, get chat id via `https://api.telegram.org/bot<TOKEN>/getUpdates`. 3. Set env vars. Digest is sent by the pipeline; commands via `python scripts/telegram_bot.py` (long-polling; `BOT_MAX_SECONDS=300` to run it as a short cron job).

## Google Sheets (optional)
Deploy an Apps Script web app that accepts `{sheets: {name: rows[]}}` and appends rows; paste its URL into `GOOGLE_SHEETS_WEBHOOK`. Failures never block the pipeline.

## Upgrade path when scale/cost allows
SQLite → Postgres (Neon/Supabase free tiers) · GitHub Actions → dedicated cron · add Redis queue for collectors · CDN for dashboard.

## Phase 2 notes
Pipeline now takes ~2–3 minutes (≈115 polite HTTP fetches; Crawl-delay honoured). `daily-pipeline.yml` timeout (30 min) is ample. Optional
env: `LOG_FORMAT=json`, `RETENTION_*_DAYS`. Add new domains to `allowed_domains` before adding feeds — requests to unlisted hosts are refused.
