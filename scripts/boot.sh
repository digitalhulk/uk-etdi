#!/usr/bin/env sh
# Container entrypoint for free-tier hosts with an ephemeral filesystem (Render/Koyeb/Fly free).
# 1) If DATA_BRANCH_URL is set, download the latest SQLite DB produced by the GitHub Actions daily pipeline.
# 2) Run migrations (idempotent), 3) start the API + dashboard.
set -e
DB_PATH="${DB_PATH:-/srv/data/uk_etdi.db}"
mkdir -p "$(dirname "$DB_PATH")"
if [ -n "$DATA_BRANCH_URL" ]; then
  echo "boot: fetching database from $DATA_BRANCH_URL"
  if curl -fsSL --retry 3 -o "$DB_PATH.tmp" "$DATA_BRANCH_URL"; then
    mv "$DB_PATH.tmp" "$DB_PATH"; echo "boot: database restored ($(du -h "$DB_PATH" | cut -f1))"
  else
    echo "boot: WARNING could not fetch database — starting with whatever is local"; rm -f "$DB_PATH.tmp"
  fi
fi
export DATABASE_URL="sqlite:///$DB_PATH"
cd /srv/backend
python ../scripts/migrate.py
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
