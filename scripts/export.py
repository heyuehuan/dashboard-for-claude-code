#!/usr/bin/env python3
"""
Export dashboard data to remote_public/ for static deployment.

Runs the local scanner, then writes:
  remote_public/data/meta.json
  remote_public/data/summary.json
  remote_public/data/projects.json
  remote_public/data/projects-all.json
  remote_public/data/sessions.json
  remote_public/data/sessions/<id>.json
  remote_public/data/settings.json
  remote_public/src/   (copy of static assets)
  remote_public/index.html  (with DASHBOARD_REMOTE flag injected)
"""

from __future__ import annotations
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from claude_dashboard.store import Store
from claude_dashboard.scanner import refresh

DB_PATH     = ROOT / "data" / "usage.db"
STATIC_IN   = ROOT / "src" / "claude_dashboard" / "static"
PUB         = ROOT / "remote_public"
DATA_OUT    = PUB / "data"
SRC_OUT     = PUB / "src"

# Replace home-dir prefix with ~ in exported paths by default.
# Set DASHBOARD_REDACT_HOME=0 to disable (e.g. for debugging).
_REDACT_HOME = os.environ.get("DASHBOARD_REDACT_HOME", "1") != "0"
_HOME_STR    = str(Path.home())

_SAFE_SID = re.compile(r'^[A-Za-z0-9_-]+$')


def main() -> None:
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    sessions_dir = DATA_OUT / "sessions"
    sessions_dir.mkdir(exist_ok=True)

    store = Store(DB_PATH)
    try:
        report = refresh(store)
        print(f"Scan: +{report.added} added, {report.updated} updated, {report.skipped} skipped")
        if report.errors:
            for e in report.errors[:5]:
                print(f"  warn: {e}")

        # ── Data files ────────────────────────────────────────────────────
        summary = store.summary()
        _write(DATA_OUT / "summary.json", _redact(summary))

        projects = store.list_projects(include_hidden=False)
        _write(DATA_OUT / "projects.json", _redact(projects))

        projects_all = store.list_projects(include_hidden=True)
        _write(DATA_OUT / "projects-all.json", _redact(projects_all))

        settings = store.get_all_project_settings()
        _write(DATA_OUT / "settings.json", _redact(settings))

        sessions = store.list_sessions()
        _write(DATA_OUT / "sessions.json", _redact(_strip_private(sessions)))

        for s in sessions:
            sid = s.get("session_id")
            if not sid:
                continue
            if not _SAFE_SID.match(sid):
                print(f"  warn: skipping session with unsafe id: {sid!r}")
                continue
            detail = store.get_session(sid)
            if detail:
                _write(sessions_dir / f"{sid}.json", _redact(_strip_private(detail)))

        _write(DATA_OUT / "meta.json", {"updated_at": datetime.now(timezone.utc).isoformat()})

        print(f"Data: {len(sessions)} sessions, {len(projects)} projects")

    finally:
        store.close()

    # ── Static assets ─────────────────────────────────────────────────────
    if SRC_OUT.exists():
        shutil.rmtree(SRC_OUT)
    shutil.copytree(STATIC_IN, SRC_OUT)

    # Remove index.html from src/ — it lives at remote_public/index.html
    (SRC_OUT / "index.html").unlink(missing_ok=True)

    # ── index.html — inject remote mode flag + rewrite asset paths ────────
    src_html = (STATIC_IN / "index.html").read_text()

    # Rewrite /static/ references to /src/
    src_html = src_html.replace('href="/static/', 'href="/src/')
    src_html = src_html.replace('src="/static/', 'src="/src/')

    # Stamp content-hash versions so browsers (especially iOS Safari) always
    # pick up the latest file after a deploy, regardless of what they cached.
    def _hash(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:8]

    js_hash  = _hash(STATIC_IN / 'app.js')
    css_hash = _hash(STATIC_IN / 'styles.css')
    src_html = re.sub(r'src="/src/app\.js(?:\?[^"]*)?',  f'src="/src/app.js?v={js_hash}',  src_html)
    src_html = re.sub(r'href="/src/styles\.css(?:\?[^"]*)?', f'href="/src/styles.css?v={css_hash}', src_html)

    # Inject DASHBOARD_REMOTE before app.js
    src_html = src_html.replace(
        f'<script src="/src/app.js?v={js_hash}"',
        f'<script>window.DASHBOARD_REMOTE=true;</script>\n  <script src="/src/app.js?v={js_hash}"',
    )

    (PUB / "index.html").write_text(src_html)

    print(f"Exported to {PUB}/")


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, default=str))


# Raw chat content that must never reach the public export. The session summary
# (summary) is the only session text meant to be published.
_PRIVATE_FIELDS = ("last_user_prompt",)


def _strip_private(obj):
    """Drop raw chat fields from a session dict or list of session dicts."""
    if isinstance(obj, list):
        return [_strip_private(v) for v in obj]
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if k not in _PRIVATE_FIELDS}
    return obj


def _redact(obj):
    """Recursively replace home-dir prefix in strings when DASHBOARD_REDACT_HOME=1.

    Dict keys are redacted too: settings.json is keyed by absolute project
    paths, which would otherwise leak the home directory even when every
    value is redacted.
    """
    if not _REDACT_HOME:
        return obj
    if isinstance(obj, str):
        return obj.replace(_HOME_STR, "~") if _HOME_STR and obj.startswith(_HOME_STR) else obj
    if isinstance(obj, dict):
        return {_redact(k): _redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


if __name__ == "__main__":
    main()
