"""Store aggregation tests. Every test uses an isolated tmp_path DB — the real
~/.claude data and data/usage.db are never touched."""
from __future__ import annotations

from claude_dashboard.store import Store


def _session(**over):
    base = {
        "session_id": "s",
        "project_path": "/p/alpha",
        "project_name": "alpha",
        "cwd": "/p/alpha",
        "version": "2.1.0",
        "git_branch": "main",
        "branch_counts": {"main": 1},
        "activity": {"all": {}, "turns": {}, "prompts": {}},
        "last_user_prompt": "do the thing",
        "started_at": "2026-05-10T09:00:00.000Z",
        "ended_at": "2026-05-10T09:30:00.000Z",
        "wall_duration_ms": 1_800_000,
        "api_duration_ms": 600_000,
        "user_rounds": 3,
        "assistant_messages": 5,
        "code_lines_added": 100,
        "code_lines_removed": 20,
        "subagent_count": 1,
        "tool_errors": 0,
        "user_rejections": 0,
        "bash_count": 2,
        "git_operations": 1,
        "tasks_completed": 2,
        "permission_modes": {"default": 2},
        "skills_used": {},
        "tokens_by_model": {},
        "tools": {},
        "cost_usd": 0.0,
    }
    base.update(over)
    return base


def _store(tmp_path):
    store = Store(tmp_path / "usage.db")
    store.upsert_session(_session(
        session_id="A", project_path="/p/alpha", project_name="alpha",
        cost_usd=18.0, user_rounds=3, assistant_messages=5,
        code_lines_added=100, code_lines_removed=20,
        tokens_by_model={"claude-sonnet-4-6": {
            "input": 1_000_000, "output": 1_000_000,
            "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}},
        tools={"Bash": 2, "Edit": 1},
        activity={"all": {"1-9": 4}, "turns": {"1-9": 2}, "prompts": {"1-9": 1}},
        skills_used={"code-review": 1},
        started_at="2026-05-10T09:00:00.000Z", ended_at="2026-05-10T09:30:00.000Z",
    ))
    store.upsert_session(_session(
        session_id="B", project_path="/p/alpha", project_name="alpha",
        cost_usd=1.0, user_rounds=2, assistant_messages=3,
        code_lines_added=50, code_lines_removed=0,
        tokens_by_model={"claude-haiku-4-5": {
            "input": 1_000_000, "output": 0,
            "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}},
        tools={"Bash": 1, "Read": 3},
        activity={"all": {"1-9": 2, "2-10": 1}, "turns": {}, "prompts": {}},
        permission_modes={"acceptEdits": 4},
        started_at="2026-05-11T09:15:00.000Z", ended_at="2026-05-11T09:45:00.000Z",
    ))
    store.upsert_session(_session(
        session_id="C", project_path="/p/beta", project_name="beta",
        cost_usd=25.0, user_rounds=4, assistant_messages=6,
        code_lines_added=200, code_lines_removed=40,
        tokens_by_model={"claude-opus-4-8": {
            "input": 500_000, "output": 200_000,
            "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}},
        tools={"Bash": 5},
        started_at="2026-05-11T14:00:00.000Z", ended_at="2026-05-11T15:00:00.000Z",
    ))
    return store


def test_summary_totals(tmp_path):
    s = _store(tmp_path).summary()
    assert s["total_sessions"] == 3
    assert s["total_rounds"] == 3 + 2 + 4
    assert s["total_assistant_messages"] == 5 + 3 + 6
    assert abs(s["total_cost"] - 44.0) < 1e-9
    assert s["total_lines_added"] == 350
    assert s["total_lines_removed"] == 60


def test_summary_tokens_and_tools_merge(tmp_path):
    s = _store(tmp_path).summary()
    assert set(s["tokens_by_model"]) == {
        "claude-sonnet-4-6", "claude-haiku-4-5", "claude-opus-4-8"}
    # Bash appears in all three sessions: 2 + 1 + 5
    assert s["tools"]["Bash"] == 8
    assert s["tools"]["Edit"] == 1
    assert s["tools"]["Read"] == 3


def test_summary_activity_merges_cells(tmp_path):
    s = _store(tmp_path).summary()
    cells = {(a["dow"], a["hour"]): a["count"] for a in s["activity"]["all"]}
    assert cells[(1, 9)] == 6  # 4 from A + 2 from B
    assert cells[(2, 10)] == 1


def test_top_projects_sorted_by_cost(tmp_path):
    s = _store(tmp_path).summary()
    tp = s["top_projects"]
    assert [p["project_name"] for p in tp] == ["beta", "alpha"]
    assert abs(tp[0]["cost"] - 25.0) < 1e-9
    assert abs(tp[1]["cost"] - 19.0) < 1e-9  # alpha = 18 + 1


def test_list_projects_grouping(tmp_path):
    projects = {p["project_name"]: p for p in _store(tmp_path).list_projects()}
    assert projects["alpha"]["session_count"] == 2
    assert abs(projects["alpha"]["cost_usd"] - 19.0) < 1e-9
    assert projects["beta"]["session_count"] == 1


def test_rename_and_hide(tmp_path):
    store = _store(tmp_path)
    store.upsert_project_setting("/p/alpha", "Alpha (renamed)", hidden=False)
    store.upsert_project_setting("/p/beta", None, hidden=True)

    names = {p["project_name"] for p in store.list_projects(include_hidden=False)}
    assert "Alpha (renamed)" in names
    assert "beta" not in names  # hidden

    all_names = {p["project_name"] for p in store.list_projects(include_hidden=True)}
    assert "beta" in all_names

    # Hidden project drops out of the cost leaderboard too.
    assert [p["project_name"] for p in store.summary()["top_projects"]] == ["Alpha (renamed)"]


def test_get_session_roundtrip(tmp_path):
    d = _store(tmp_path).get_session("A")
    assert d["session_id"] == "A"
    assert d["tokens_by_model"]["claude-sonnet-4-6"]["input"] == 1_000_000
    assert d["tools"]["Bash"] == 2
    assert d["project_name"] == "alpha"


def test_daily_series(tmp_path):
    # Buckets are grouped by local date, so exact dates are timezone-dependent;
    # assert the tz-independent invariants instead (totals across all days).
    daily = _store(tmp_path).summary()["daily"]
    assert sum(d["sessions"] for d in daily) == 3
    assert abs(sum(d["cost"] for d in daily) - 44.0) < 1e-9
    # Rows are ordered by date ascending.
    assert [d["date"] for d in daily] == sorted(d["date"] for d in daily)


# ── Session summaries (read from session_summary.json, not the DB) ──────────

import json  # noqa: E402


def _write_summaries(store, mapping):
    store.summary_file.write_text(json.dumps(mapping))


def test_summaries_missing_file_returns_empty(tmp_path):
    store = _store(tmp_path)
    assert store.get_all_summaries() == {}
    assert store.get_summary("A") is None


def test_summaries_read_and_surface_in_sessions(tmp_path):
    store = _store(tmp_path)
    _write_summaries(store, {"A": "Fixed the parser.", "B": "  "})  # blank dropped
    assert store.get_summary("A") == "Fixed the parser."
    assert store.get_summary("B") is None  # whitespace-only value is ignored
    # Summary flows into detail and list views.
    assert store.get_session("A")["summary"] == "Fixed the parser."
    by_id = {s["session_id"]: s for s in store.list_sessions()}
    assert by_id["A"]["summary"] == "Fixed the parser."
    assert by_id["C"]["summary"] is None


def test_summaries_cache_invalidates_on_change(tmp_path):
    store = _store(tmp_path)
    _write_summaries(store, {"A": "first"})
    assert store.get_summary("A") == "first"
    # Rewrite with different content *and* size so the (mtime, size) key changes
    # even if the filesystem mtime resolution is coarse.
    _write_summaries(store, {"A": "second version, longer"})
    assert store.get_summary("A") == "second version, longer"


def test_summaries_malformed_json_falls_back_to_empty(tmp_path):
    store = _store(tmp_path)
    store.summary_file.write_text("{ not valid json")
    assert store.get_all_summaries() == {}


def test_sessions_missing_summary_excludes_summarized(tmp_path):
    store = _store(tmp_path)
    _write_summaries(store, {"A": "done"})
    missing = {s["session_id"] for s in store.sessions_missing_summary()}
    assert missing == {"B", "C"}  # A has a summary now
