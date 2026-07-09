"""API smoke tests via FastAPI's TestClient.

The app is pointed at an isolated tmp DB and DASHBOARD_NO_SCAN disables the
startup scan, so these tests never read ~/.claude or the real data/usage.db.
"""
from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from claude_dashboard import scanner
from claude_dashboard.store import Store

AUTH_TOKEN = "s3cr3t-test-token"


def _seed(db_path):
    store = Store(db_path)
    store.upsert_session({
        "session_id": "A", "project_path": "/p/alpha", "project_name": "alpha",
        "cwd": "/p/alpha", "version": "2.1.0", "git_branch": "main",
        "branch_counts": {"main": 1}, "activity": {"all": {"1-9": 3}, "turns": {}, "prompts": {}},
        "started_at": "2026-05-10T09:00:00.000Z", "ended_at": "2026-05-10T09:30:00.000Z",
        "wall_duration_ms": 1_800_000, "api_duration_ms": 600_000,
        "user_rounds": 3, "assistant_messages": 5,
        "code_lines_added": 100, "code_lines_removed": 20,
        "permission_modes": {"default": 2}, "skills_used": {"code-review": 1},
        "tokens_by_model": {"claude-sonnet-4-6": {
            "input": 1_000_000, "output": 1_000_000,
            "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}},
        "tools": {"Bash": 2, "Edit": 1}, "cost_usd": 18.0,
    })
    store.upsert_session({
        "session_id": "B", "project_path": "/p/beta", "project_name": "beta",
        "cwd": "/p/beta", "version": "2.1.0", "git_branch": "main",
        "branch_counts": {"main": 1}, "activity": {"all": {}, "turns": {}, "prompts": {}},
        "started_at": "2026-05-11T09:00:00.000Z", "ended_at": "2026-05-11T09:30:00.000Z",
        "wall_duration_ms": 1_800_000, "api_duration_ms": 600_000,
        "user_rounds": 2, "assistant_messages": 3,
        "code_lines_added": 40, "code_lines_removed": 5,
        "permission_modes": {"acceptEdits": 3}, "skills_used": {},
        "tokens_by_model": {"claude-opus-4-8": {
            "input": 100_000, "output": 50_000,
            "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}},
        "tools": {"Read": 4}, "cost_usd": 25.0,
    })
    store.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    db = tmp_path / "demo.db"
    _seed(db)
    monkeypatch.setenv("DASHBOARD_DB", str(db))
    monkeypatch.setenv("DASHBOARD_NO_SCAN", "1")
    monkeypatch.delenv("DASHBOARD_AUTH_TOKEN", raising=False)
    import claude_dashboard.app as app_mod
    importlib.reload(app_mod)  # re-read env into module-level config
    with TestClient(app_mod.app, base_url="http://localhost") as c:
        yield c


def test_index_serves_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<title>" in r.text.lower()


def test_summary(client):
    r = client.get("/api/summary")
    assert r.status_code == 200
    d = r.json()
    assert d["total_sessions"] == 2
    assert abs(d["total_cost"] - 43.0) < 1e-9
    assert [p["project_name"] for p in d["top_projects"]] == ["beta", "alpha"]


def test_projects(client):
    r = client.get("/api/projects")
    assert r.status_code == 200
    names = {p["project_name"] for p in r.json()}
    assert names == {"alpha", "beta"}


def test_sessions_list_and_detail(client):
    r = client.get("/api/sessions")
    assert r.status_code == 200
    assert len(r.json()) == 2

    r = client.get("/api/sessions/A")
    assert r.status_code == 200
    assert r.json()["tokens_by_model"]["claude-sonnet-4-6"]["input"] == 1_000_000


def test_unknown_session_404(client):
    assert client.get("/api/sessions/does-not-exist").status_code == 404


def test_unknown_project_404(client):
    assert client.get("/api/project?name=nope").status_code == 404


def test_rename_via_settings_reflects_in_projects(client):
    r = client.put("/api/settings", json={
        "project_path": "/p/alpha", "display_name": "Alpha (renamed)", "hidden": False})
    assert r.status_code == 200
    names = {p["project_name"] for p in client.get("/api/projects").json()}
    assert "Alpha (renamed)" in names


def test_hidden_project_detail_stays_reachable(client):
    r = client.put("/api/settings", json={"project_path": "/p/alpha", "hidden": True})
    assert r.status_code == 200
    # Hidden projects drop out of the listing …
    names = {p["project_name"] for p in client.get("/api/projects").json()}
    assert "alpha" not in names
    # … but a direct link to the detail still works.
    r = client.get("/api/project", params={"path": "/p/alpha"})
    assert r.status_code == 200
    assert r.json()["session_count"] == 1


# ── Host-header guard (DNS-rebinding protection, loopback mode) ─────────────

def test_host_guard_rejects_foreign_host(client):
    r = client.get("/api/summary", headers={"host": "evil.example.com"})
    assert r.status_code == 403


def test_host_guard_rejects_empty_host(client):
    r = client.get("/api/summary", headers={"host": ""})
    assert r.status_code == 403


@pytest.mark.parametrize("host", [
    "localhost", "localhost:8042", "127.0.0.1:8042", "[::1]:8042", "[::1]",
])
def test_host_guard_allows_loopback_forms(client, host):
    r = client.get("/api/summary", headers={"host": host})
    assert r.status_code == 200


# ── Token auth (DASHBOARD_AUTH_TOKEN) ───────────────────────────────────────
# The security-critical remote-hosting path: when the token is set every /api/*
# call must present it (bearer header or cookie), while the SPA shell and static
# assets stay reachable so the browser can render the login page.

@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    db = tmp_path / "demo.db"
    _seed(db)
    monkeypatch.setenv("DASHBOARD_DB", str(db))
    monkeypatch.setenv("DASHBOARD_NO_SCAN", "1")
    monkeypatch.setenv("DASHBOARD_AUTH_TOKEN", AUTH_TOKEN)
    import claude_dashboard.app as app_mod
    importlib.reload(app_mod)  # re-read env into module-level config
    with TestClient(app_mod.app, base_url="http://localhost") as c:
        yield c
    # Restore the unauthenticated module state for any later import.
    monkeypatch.delenv("DASHBOARD_AUTH_TOKEN", raising=False)
    importlib.reload(app_mod)


def test_auth_api_requires_token(auth_client):
    assert auth_client.get("/api/summary").status_code == 401


def test_auth_api_rejects_wrong_token(auth_client):
    r = auth_client.get("/api/summary", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_auth_api_accepts_bearer_token(auth_client):
    r = auth_client.get("/api/summary",
                        headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
    assert r.status_code == 200


def test_auth_api_accepts_cookie_token(auth_client):
    auth_client.cookies.set("dashboard_auth", AUTH_TOKEN)
    assert auth_client.get("/api/summary").status_code == 200


def test_auth_shell_and_static_reachable_without_token(auth_client):
    # Login page, SPA routes, and static assets must load unauthenticated.
    assert auth_client.get("/").status_code == 200
    assert auth_client.get("/overview").status_code == 200
    assert auth_client.get("/static/app.js").status_code == 200


def test_login_rejects_bad_token(auth_client):
    r = auth_client.post("/api/login", json={"token": "wrong"})
    assert r.status_code == 401


def test_login_sets_cookie_and_authorizes(auth_client):
    r = auth_client.post("/api/login", json={"token": AUTH_TOKEN})
    assert r.status_code == 200
    assert "dashboard_auth" in r.cookies
    # The client now carries the cookie, so a protected call succeeds.
    assert auth_client.get("/api/summary").status_code == 200


def test_login_404_when_auth_disabled(client):
    # No DASHBOARD_AUTH_TOKEN set → the endpoint reports it's not enabled.
    assert client.post("/api/login", json={"token": "anything"}).status_code == 404


# ── Remaining endpoints ─────────────────────────────────────────────────────

def test_summaries_missing_lists_unsummarized(client):
    r = client.get("/api/summaries/missing")
    assert r.status_code == 200
    ids = {s["session_id"] for s in r.json()}
    assert ids == {"A", "B"}  # neither seeded session has a summary


def test_refresh_endpoint_reports_shape(client, tmp_path, monkeypatch):
    # Point the scanner at an empty projects tree so the endpoint never reads
    # the real ~/.claude, then confirm the report shape.
    empty = tmp_path / "empty_projects"
    empty.mkdir()
    monkeypatch.setattr(scanner, "_CLAUDE_PROJECTS", empty)
    r = client.post("/api/refresh")
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"added", "updated", "skipped", "pruned", "errors"}
    assert body["added"] == 0


def test_put_setting_requires_project_path(client):
    assert client.put("/api/settings", json={}).status_code == 400


def test_project_merges_multiple_paths_under_one_display_name(client):
    # Rename beta so it shares alpha's display name → /api/project must merge
    # the two distinct paths on the fly.
    client.put("/api/settings",
               json={"project_path": "/p/beta", "display_name": "alpha"})
    r = client.get("/api/project", params={"name": "alpha"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["project_paths"]) == {"/p/alpha", "/p/beta"}
    assert body["session_count"] == 2
    assert body["cost_usd"] == 43.0  # 18 + 25
    # Tokens and tools from both paths are combined.
    assert {"claude-sonnet-4-6", "claude-opus-4-8"} <= set(body["tokens_by_model"])
    assert body["tools"].get("Bash") == 2 and body["tools"].get("Read") == 4
    assert len(body["sessions"]) == 2
