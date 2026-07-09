#!/usr/bin/env bash
# Deploy dashboard to a remote server.
# Usage: ./scripts/deploy.sh [--export-only]
#
# Requires scripts/deploy.env  (gitignored — copy from deploy.env.example)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$SCRIPT_DIR/deploy.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found."
  echo "Copy scripts/deploy.env.example to scripts/deploy.env and fill in your values."
  exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"
: "${REMOTE_HOST:?deploy.env must set REMOTE_HOST}"
: "${REMOTE_PATH:?deploy.env must set REMOTE_PATH}"
: "${REMOTE_URL:?deploy.env must set REMOTE_URL}"

echo "==> Exporting data..."
python3 "$SCRIPT_DIR/export.py"

if [[ "${1:-}" == "--export-only" ]]; then
  echo "Skipping deploy (--export-only)."
  exit 0
fi

echo "==> Syncing to $REMOTE_HOST:$REMOTE_PATH ..."
ssh "$REMOTE_HOST" "sudo mkdir -p '$REMOTE_PATH' && sudo chown -R \$(whoami) '$REMOTE_PATH'"
scp -r "$PROJECT_DIR/remote_public/"* "$REMOTE_HOST:$REMOTE_PATH/"

echo "==> Done. Live at $REMOTE_URL"
