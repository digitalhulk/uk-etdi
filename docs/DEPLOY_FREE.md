# Deploy for £0 — public URL that opens on any phone

Two moving parts, both free:

| Part | Where | Cost |
|---|---|---|
| Daily pipeline (collect → score → digest) | **GitHub Actions** cron 06:00 UTC, DB stored in the repo's `data` branch | £0 (public repo: unlimited minutes; private: 2,000 min/month, we use ~5 min/day) |
| API + dashboard | **Render free web service** (Docker) — or Fly.io / Koyeb / Oracle Always-Free VM | £0 |

The free Render instance sleeps after 15 min idle and its disk is wiped on restart — that is fine because **the database
lives in GitHub**: on every boot `scripts/boot.sh` downloads the latest `uk_etdi.db` from the `data` branch, and after
every daily run the workflow calls Render's deploy hook so the instance restarts with fresh data.

## Step 1 — GitHub (10 min)
1. Create a repo (public is simplest) and push this folder:
   ```bash
   cd uk-etdi && git init && git add -A && git commit -m "UK-ETDI" && git branch -M main
   git remote add origin https://github.com/OWNER/REPO.git && git push -u origin main
   ```
2. Repo → **Settings → Actions → General → Workflow permissions → Read and write** (the workflow pushes the `data` branch).
3. Optional secrets (Settings → Secrets → Actions): `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TICKETMASTER_API_KEY`.
4. **Actions → Daily pipeline → Run workflow** once. After ~5 min a `data` branch appears containing `uk_etdi.db`.
   Check: `https://raw.githubusercontent.com/OWNER/REPO/data/uk_etdi.db` downloads (~30 MB).

## Step 2 — Render (5 min)
1. https://render.com → sign up with GitHub (no card needed) → **New → Blueprint** → pick the repo. Render reads `render.yaml`.
2. Before clicking Apply, edit env var `DATA_BRANCH_URL` → `https://raw.githubusercontent.com/OWNER/REPO/data/uk_etdi.db`.
3. Apply. First build ≈ 3–4 min. Your URL: `https://uk-etdi.onrender.com` (or `uk-etdi-xxxx`). Opens on any phone.
4. Render → service → **Settings → Deploy Hook** → copy URL → GitHub repo secret **`DEPLOY_HOOK_URL`**. Now each daily
   run redeploys the API with the new DB automatically.
5. `API_ADMIN_TOKEN` was auto-generated (Render → Environment). You need it only for the "Run pipeline now" button,
   source toggles and settings edits; on the free instance prefer running the pipeline from GitHub Actions.

Private repo? Either make only the `data` branch downloadable via a fine-grained PAT
(`DATA_BRANCH_URL=https://TOKEN@raw.githubusercontent.com/...` is **not** supported by GitHub — use
`https://api.github.com/repos/OWNER/REPO/contents/uk_etdi.db?ref=data` with header auth, see boot.sh comments), or simply keep the repo public: the DB
contains only public event metadata and your modelled scores — no secrets.

## Alternative — Fly.io (persistent volume, no redeploy dance)
```bash
fly launch --copy-config --no-deploy      # uses fly.toml
fly volumes create etdi_data -s 1 -r lhr
fly secrets set API_ADMIN_TOKEN=$(openssl rand -hex 24)
fly deploy
```
The volume persists; `SCHEDULER_ENABLED=1` runs the daily pipeline inside the app, so GitHub Actions becomes optional.

## Alternative — Oracle Cloud Always-Free VM (always on, no sleep)
`docker compose up -d` on the VM (see `docker-compose.yml`), open port 8000 in the VCN security list, optional free
Cloudflare Tunnel for HTTPS. Most control, ~20 min setup.

## Limits to know
* Render free: sleeps after 15 min idle → first request takes ~30–50 s to wake. Fine for a daily-check dashboard.
* Nothing here costs money; no card is required for Render free or GitHub Actions on a public repo.
* Keep secrets in Render env / GitHub secrets only — never in the repo (`.env` is git-ignored).
