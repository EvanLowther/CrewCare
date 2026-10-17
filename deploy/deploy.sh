#!/usr/bin/env bash
# Deploy origin/main on the server if it changed. Run by planit-deploy.timer every minute (as root);
# `sudo /opt/planit/deploy/deploy.sh --force` redeploys even without a new commit.
#
# The site keeps serving the old build while the new one builds, and if a build fails, nothing is swapped.
set -euo pipefail

APP=/opt/planit
LOG_TAG=planit-deploy
as_planit() { runuser -u planit -- "$@"; }
log() { echo "[$LOG_TAG] $*"; }

cd "$APP"
as_planit git fetch -q origin main
old=$(as_planit git rev-parse HEAD)
new=$(as_planit git rev-parse origin/main)
if [[ "$old" == "$new" && "${1:-}" != "--force" ]]; then
  exit 0
fi
log "deploying ${new:0:7} (was ${old:0:7})"

changed=$(as_planit git diff --name-only "$old" "$new" || true)
as_planit git reset -q --hard "$new"   # .env and build output are untracked, so they're kept

if [[ "${1:-}" == "--force" ]] || grep -q '^backend/pyproject.toml' <<<"$changed"; then
  log "installing Python packages"
  as_planit "$APP/.venv/bin/pip" install -q -e "$APP/backend[ml]"
fi

if grep -q '^deploy/systemd/' <<<"$changed"; then
  log "updating services"
  cp "$APP"/deploy/systemd/*.service "$APP"/deploy/systemd/*.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl restart planit-web
fi

if grep -q '^db/migrations/' <<<"$changed"; then
  log "applying migrations"
  (cd "$APP/backend" && as_planit "$APP/.venv/bin/python" scripts/migrate.py)
fi

if [[ "${1:-}" == "--force" ]] || grep -q '^frontend/' <<<"$changed"; then
  log "building the website"
  cd "$APP/frontend"
  as_planit env COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm install --frozen-lockfile
  # Build next to the live one, then swap, so a failed build never takes the site down.
  rm -rf .next-new
  if as_planit env NEXT_DIST_DIR=.next-new COREPACK_ENABLE_DOWNLOAD_PROMPT=0 pnpm build; then
    rm -rf .next-old
    [[ -d .next ]] && mv .next .next-old
    mv .next-new .next
    systemctl restart planit-web
  else
    log "website build FAILED; still serving the previous build"
    rm -rf .next-new
  fi
  cd "$APP"
fi

systemctl restart planit-api planit-worker
log "done: ${new:0:7}"
