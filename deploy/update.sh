#!/usr/bin/env bash
# Run on the EC2 host to pull latest main and restart the bot.
# Invoked by GitHub Actions over SSH. Preserves local .env.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/portfolio-bot}"
BRANCH="${DEPLOY_BRANCH:-main}"

cd "$APP_DIR"

if [[ ! -d .git ]]; then
  echo "ERROR: $APP_DIR is not a git checkout. Clone the repo first (see deploy/README.md)." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "ERROR: $APP_DIR/.env is missing. Create it before deploying." >&2
  exit 1
fi

echo "==> Fetching origin/$BRANCH"
git fetch --prune origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

echo "==> Restarting portfolio-bot (rebuilds image via systemd ExecStartPre)"
sudo systemctl restart portfolio-bot

echo "==> Waiting for service to become active"
for _ in $(seq 1 30); do
  if systemctl is-active --quiet portfolio-bot; then
    break
  fi
  sleep 2
done

sudo systemctl --no-pager --full status portfolio-bot || true
echo "==> Recent logs"
sudo journalctl -u portfolio-bot -n 40 --no-pager || true

if ! systemctl is-active --quiet portfolio-bot; then
  echo "ERROR: portfolio-bot is not active after deploy." >&2
  exit 1
fi

echo "==> Deploy OK"
