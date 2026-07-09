#!/usr/bin/env bash
# Refresh dashboard data and upload to remote only when content has changed.
# Run via launchd (every 5 min) or manually.
set -euo pipefail

# launchd runs with a stripped PATH; restore common locations
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="$PROJECT_DIR/logs/refresh.log"
HASH_FILE="$PROJECT_DIR/.last_data_hash"
MAX_LOG_LINES=5000

mkdir -p "$PROJECT_DIR/logs"

ENV_FILE="$SCRIPT_DIR/deploy.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found — cannot upload. Copy deploy.env.example." >&2
    exit 1
fi
# shellcheck source=/dev/null
source "$ENV_FILE"
: "${REMOTE_HOST:?deploy.env must set REMOTE_HOST}"
: "${REMOTE_PATH:?deploy.env must set REMOTE_PATH}"
: "${REMOTE_URL:?deploy.env must set REMOTE_URL}"

log() {
    printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" | tee -a "$LOG_FILE"
}

# Rotate log when it exceeds MAX_LOG_LINES (keep the newest half)
if [[ -f "$LOG_FILE" ]] && (( $(wc -l < "$LOG_FILE") > MAX_LOG_LINES )); then
    tail -n $((MAX_LOG_LINES / 2)) "$LOG_FILE" > "$LOG_FILE.tmp" && mv "$LOG_FILE.tmp" "$LOG_FILE"
    log "Log rotated (kept last $((MAX_LOG_LINES / 2)) lines)"
fi

log "--- refresh start ---"

# Export: scan local data → remote_public/
if ! python3 "$SCRIPT_DIR/export.py" >> "$LOG_FILE" 2>&1; then
    log "ERROR: export.py failed (exit $?)"
    exit 1
fi

# Hash everything we deploy (data JSON + the static UI under src/ + index.html),
# excluding meta.json which always updates its timestamp. Hashing the UI files too
# means UI-only changes (app.js/styles.css/index.html) trigger an upload, not just
# data changes.
NEW_HASH=$( { \
    find "$PROJECT_DIR/remote_public/data" -name "*.json" ! -name "meta.json"; \
    find "$PROJECT_DIR/remote_public/src" -type f; \
    echo "$PROJECT_DIR/remote_public/index.html"; \
  } | sort | xargs shasum 2>/dev/null | shasum | awk '{print $1}')

LAST_HASH=""
[[ -f "$HASH_FILE" ]] && LAST_HASH=$(cat "$HASH_FILE")

if [[ "$NEW_HASH" == "$LAST_HASH" ]]; then
    log "No changes — skipping upload"
    exit 0
fi

log "Changes detected (hash $LAST_HASH → $NEW_HASH), uploading..."

# rsync: only transfers files that actually changed, deletes remote orphans
if rsync -az --delete \
        "$PROJECT_DIR/remote_public/" \
        "$REMOTE_HOST:$REMOTE_PATH/" >> "$LOG_FILE" 2>&1; then
    printf '%s' "$NEW_HASH" > "$HASH_FILE"
    log "Upload done — $REMOTE_URL"
else
    log "ERROR: rsync failed (exit $?)"
    exit 1
fi
