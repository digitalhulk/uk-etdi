#!/usr/bin/env bash
# One-shot publish: push repo to GitHub, seed the `data` branch with the current DB, print the next Render steps.
# Usage:  GH_USER=yourname GH_REPO=uk-etdi bash scripts/publish.sh
set -euo pipefail
: "${GH_USER:?set GH_USER=your-github-username}"; : "${GH_REPO:=uk-etdi}"
cd "$(dirname "$0")/.."
git remote remove origin 2>/dev/null || true
git remote add origin "https://github.com/$GH_USER/$GH_REPO.git"
echo "▶ pushing main…"; git push -u origin main
if [ -f data/uk_etdi.db ]; then
  echo "▶ seeding data branch with current database ($(du -h data/uk_etdi.db | cut -f1))…"
  TMP=$(mktemp -d); cp data/uk_etdi.db "$TMP/"
  git checkout -q --orphan data-seed; git rm -rfq . >/dev/null 2>&1 || true; cp "$TMP/uk_etdi.db" .
  git add uk_etdi.db; git commit -qm "data: seed $(date -u +%FT%TZ)"; git push -f origin data-seed:data
  git checkout -q main; git branch -qD data-seed
fi
cat <<MSG

✅ Pushed. Now:
  1. https://github.com/$GH_USER/$GH_REPO/settings/actions  → Workflow permissions → "Read and write" → Save
  2. https://dashboard.render.com/blueprints → New Blueprint → select $GH_USER/$GH_REPO
     set DATA_BRANCH_URL = https://raw.githubusercontent.com/$GH_USER/$GH_REPO/data/uk_etdi.db  → Apply
  3. Render service → Settings → Deploy Hook → copy → add as GitHub secret DEPLOY_HOOK_URL
     https://github.com/$GH_USER/$GH_REPO/settings/secrets/actions
Your dashboard: https://$GH_REPO.onrender.com  (first load after idle ≈ 40 s)
MSG
