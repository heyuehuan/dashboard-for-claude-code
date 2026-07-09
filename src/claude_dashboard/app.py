from __future__ import annotations
import hmac
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from claude_dashboard.store import Store
from claude_dashboard.scanner import refresh, RefreshReport

# DB location. DASHBOARD_DB lets tests, demos, and the screenshot generator
# point at an isolated database so a run never has to touch (or scan) your
# real ~/.claude data.
def _default_db() -> Path:
    # Source checkout (repo root has pyproject.toml): keep the DB in-tree at
    # data/usage.db, as documented. Installed package (pipx/uvx/pip): the tree
    # location would land inside site-packages and be wiped on reinstall, so
    # use a per-user data dir instead.
    root = Path(__file__).resolve().parent.parent.parent
    if (root / "pyproject.toml").is_file():
        return root / "data" / "usage.db"
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "dashboard-for-claude-code" / "usage.db"


_DB_PATH = Path(os.environ.get("DASHBOARD_DB") or _default_db())
_STATIC = Path(__file__).parent / "static"

# Optional token auth — active only when DASHBOARD_AUTH_TOKEN is set.
# Accepts: Authorization: Bearer <token>  OR  cookie dashboard_auth=<token>
_AUTH_TOKEN: str | None = os.environ.get("DASHBOARD_AUTH_TOKEN") or None

# Loopback detection — used for DNS-rebinding protection (M3) and cookie
# secure flag (M5). True when bound to a loopback address (the default).
_HOST = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
_LOOPBACK_ADDRS = {"127.0.0.1", "::1", "0:0:0:0:0:0:0:1"}
_IS_LOCALHOST = _HOST in _LOOPBACK_ADDRS
_LOOPBACK_HOST_NAMES = {"localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1"}

_store: Store | None = None
_refresh_lock = threading.Lock()


def _host_name(raw_host: str) -> str:
    """Extract the hostname from a Host header value.

    Handles bracketed IPv6 literals ("[::1]:8042" → "::1"); a naive
    split(":") would mangle them into "" and skip the loopback check.
    """
    raw_host = raw_host.strip()
    if raw_host.startswith("["):
        end = raw_host.find("]")
        return raw_host[1:end] if end != -1 else ""
    return raw_host.split(":")[0]


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global _store
    _store = Store(_DB_PATH)
    # Initial scan in background so startup is fast. DASHBOARD_NO_SCAN=1 disables
    # it entirely (used by tests and the screenshot generator, which supply their
    # own pre-populated DB and must never read ~/.claude).
    if not os.environ.get("DASHBOARD_NO_SCAN"):
        threading.Thread(target=_do_refresh, daemon=True).start()
    try:
        yield
    finally:
        if _store:
            _store.close()


app = FastAPI(title="Claude Code Usage Dashboard", lifespan=_lifespan)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # ── DNS-rebinding protection (M3) ────────────────────────────────────────
    # When bound to a loopback address, reject requests whose Host header
    # isn't a recognized localhost name. This blocks a malicious page from
    # reaching the unauthenticated API via a rebound hostname.
    if _IS_LOCALHOST:
        host_name = _host_name(request.headers.get("host", ""))
        # An absent/empty Host is rejected too: every legitimate client
        # (HTTP/1.1 requires Host) sends one, and allowing it would let
        # malformed requests skip the check.
        if host_name not in _LOOPBACK_HOST_NAMES:
            return JSONResponse({"detail": "Forbidden"}, status_code=403)

    # ── Optional token auth ──────────────────────────────────────────────────
    if _AUTH_TOKEN:
        # Allow the login page (GET /) and static assets even without auth,
        # so the browser can render the 401 page gracefully.
        skip = request.url.path in ("/", "/overview", "/projects", "/sessions", "/settings",
                                    "/api/login") \
               or request.url.path.startswith("/static/")
        if not skip:
            bearer = request.headers.get("Authorization", "")
            token = bearer.removeprefix("Bearer ").strip() if bearer.startswith("Bearer ") else ""
            if not token:
                token = request.cookies.get("dashboard_auth", "")
            if not hmac.compare_digest(token, _AUTH_TOKEN):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    # ── No-cache for static assets (local mode) ──────────────────────────────
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


def _do_refresh(prune: bool = False) -> RefreshReport:
    with _refresh_lock:
        return refresh(_store, prune=prune)


# ── API ────────────────────────────────────────────────────────────────────

@app.get("/api/summary")
def api_summary():
    return _store.summary()


@app.get("/api/projects")
def api_projects(include_hidden: bool = Query(False)):
    return _store.list_projects(include_hidden=include_hidden)


@app.get("/api/project")
def api_project(path: str = Query(None), name: str = Query(None)):
    if not path and not name:
        raise HTTPException(400, "path or name required")
    # include_hidden: hidden projects are excluded from listings, but their
    # detail page must stay reachable via a direct link.
    projects = _store.list_projects(include_hidden=True)
    if path:
        matched = [p for p in projects if p.get("project_path") == path]
    else:
        # Match by display name (project_name after rename applied)
        matched = [p for p in projects if p.get("project_name") == name]
    if not matched:
        raise HTTPException(404, "Project not found")

    if len(matched) == 1:
        proj = matched[0]
        proj["project_paths"] = [proj["project_path"]]
        proj["sessions"] = _store.list_sessions(proj["project_path"])
        return proj

    # Multiple paths share the same display name — merge on the fly
    all_paths = [p["project_path"] for p in matched]
    base = dict(matched[0])
    base["project_paths"] = all_paths
    for p in matched[1:]:
        for f in ("session_count", "user_rounds", "assistant_messages",
                  "api_duration_ms", "wall_duration_ms", "code_lines_added",
                  "code_lines_removed", "cost_usd"):
            base[f] = (base.get(f) or 0) + (p.get(f) or 0)
        base["last_active"] = max(base.get("last_active") or "", p.get("last_active") or "") or None
        base["first_active"] = min(
            base.get("first_active") or "\xff", p.get("first_active") or "\xff"
        ).replace("\xff", "") or None
        # merge tokens_by_model
        for model, counts in (p.get("tokens_by_model") or {}).items():
            if model not in base["tokens_by_model"]:
                base["tokens_by_model"][model] = {"input": 0, "output": 0, "cache_read": 0,
                                                   "cache_write_5m": 0, "cache_write_1h": 0}
            for k, v in counts.items():
                base["tokens_by_model"][model][k] = base["tokens_by_model"][model].get(k, 0) + (v or 0)
        for tool, cnt in (p.get("tools") or {}).items():
            base["tools"][tool] = base["tools"].get(tool, 0) + cnt
    base["sessions"] = _store.list_sessions_for_paths(all_paths)
    return base


@app.get("/api/sessions")
def api_sessions():
    return _store.list_sessions()


@app.get("/api/sessions/{session_id}")
def api_session(session_id: str):
    s = _store.get_session(session_id)
    if not s:
        raise HTTPException(404, "Session not found")
    return s


@app.get("/api/settings")
def api_get_settings():
    return _store.get_all_project_settings()


@app.put("/api/settings")
async def api_put_setting(body: dict[str, Any]):
    project_path = body.get("project_path")
    if not project_path:
        raise HTTPException(400, "project_path required")
    _store.upsert_project_setting(
        project_path,
        body.get("display_name") or None,
        bool(body.get("hidden", False)),
    )
    return {"ok": True}


@app.post("/api/login")
async def api_login(body: dict[str, Any], response: Response):
    if not _AUTH_TOKEN:
        raise HTTPException(404, "Auth not enabled")
    token = body.get("token", "")
    if not isinstance(token, str) or not hmac.compare_digest(token, _AUTH_TOKEN):
        raise HTTPException(401, "Invalid token")
    # secure=True on non-localhost so the cookie is HTTPS-only when hosted remotely.
    response.set_cookie("dashboard_auth", token, httponly=True, samesite="strict",
                        secure=not _IS_LOCALHOST)
    return {"ok": True}


@app.get("/api/summaries/missing")
def api_summaries_missing():
    """Sessions that still need an AI summary, most recent first."""
    return _store.sessions_missing_summary()


# Summaries are not stored in the DB: scripts/set_summaries.py writes
# data/session_summary.json (the source of truth) and Store reads it directly
# at query time. See Store.get_all_summaries.


@app.post("/api/refresh")
def api_refresh(prune: bool = Query(False)):
    """Re-scan transcripts. prune=true also drops sessions whose transcript
    file no longer exists on disk (by default deleted transcripts stay in the
    cache so history survives Claude Code's own cleanup)."""
    report = _do_refresh(prune=prune)
    return {
        "added": report.added,
        "updated": report.updated,
        "skipped": report.skipped,
        "pruned": report.pruned,
        "errors": report.errors[:20],
    }


# ── Static files ───────────────────────────────────────────────────────────

app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.get("/")
@app.get("/overview")
@app.get("/projects")
@app.get("/sessions")
@app.get("/settings")
def index():
    return FileResponse(str(_STATIC / "index.html"))
