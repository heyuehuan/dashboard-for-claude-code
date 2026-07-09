# scripts/

Helper scripts for remote deployment and background refresh.

## Setup

1. Copy the deploy config template and fill in your values:

```bash
cp scripts/deploy.env.example scripts/deploy.env
# edit scripts/deploy.env
```

2. *(macOS — optional)* Set up the launchd agent for automatic refresh every 5 min:

```bash
cp scripts/com.claude-dashboard.plist.example ~/Library/LaunchAgents/com.claude-dashboard.plist
# Replace __PROJECT_DIR__ in the plist with the absolute path to this repo
launchctl load ~/Library/LaunchAgents/com.claude-dashboard.plist
```

It runs once immediately on load, then every 5 minutes. Survives reboots.

## Deactivate launchd agent

```bash
launchctl unload ~/Library/LaunchAgents/com.claude-dashboard.plist
```

## Useful commands

```bash
# Check status and last exit code
launchctl list | grep claude-dashboard

# Watch the refresh log
tail -f logs/refresh.log

# Trigger a manual run immediately
launchctl kickstart -k gui/$(id -u)/com.claude-dashboard
```

## Scripts

- `deploy.sh` — export data + push full `remote_public/` to the server
- `refresh.sh` — export data + rsync only when content changes (used by launchd)
- `export.py` — scan `~/.claude/projects/`, write `remote_public/data/` and static assets
- `demo_data.py` — generate an isolated database of **synthetic** placeholder data
  (never reads `~/.claude`), used for screenshots and trying out the UI

See `scripts/SECURITY.md` for notes on access control and nginx hardening.

## Optional: session summaries

Two scripts support adding one/two-sentence summaries to sessions, shown in the dashboard alongside each session:

- `session_digest.py` — prints compact digests (first prompt, last response, cost, tools used) for sessions that are missing a summary, most recent first. Useful for reviewing what each session was about before writing summaries.
- `set_summaries.py` — merges a `{session_id: summary_text}` JSON object into `data/session_summary.json`, which the dashboard ingests on next refresh. Input can come from any source.

```bash
# See which sessions need a summary (default: 8 at a time)
python scripts/session_digest.py [N] [--offset M]

# Write summaries manually or pipe from any tool, then merge
echo '{"abc123": "Refactored auth middleware to fix token storage.", ...}' | python scripts/set_summaries.py

# Or pass a JSON file
python scripts/set_summaries.py summaries.json
```

One workflow: run `session_digest.py`, have an AI tool read the output and produce a JSON blob of summaries, then pipe that into `set_summaries.py`. No server restart required — the dashboard picks up `data/session_summary.json` on its next refresh.

## Demo data & screenshots

Screenshots in `docs/` use synthetic data — no real project names, paths, or costs:

```bash
# Generate a demo DB (writes nothing to ~/.claude)
python scripts/demo_data.py /tmp/demo.db

# Serve it without touching your real logs
DASHBOARD_DB=/tmp/demo.db DASHBOARD_NO_SCAN=1 uv run python -m claude_dashboard
```

Then open http://localhost:8042 and take screenshots.
