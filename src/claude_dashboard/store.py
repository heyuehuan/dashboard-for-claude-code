from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path
from typing import Any


_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path      TEXT    PRIMARY KEY,
    mtime     REAL    NOT NULL,
    size      INTEGER NOT NULL,
    session_id TEXT   NOT NULL,
    parsed_at REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id          TEXT PRIMARY KEY,
    project_path        TEXT,
    project_name        TEXT,
    cwd                 TEXT,
    version             TEXT,
    git_branch          TEXT,
    branches_json       TEXT,
    activity_json       TEXT,
    custom_title        TEXT,
    last_user_prompt    TEXT,
    started_at          TEXT,
    ended_at            TEXT,
    wall_duration_ms    INTEGER,
    api_duration_ms     INTEGER,
    user_rounds         INTEGER,
    assistant_messages  INTEGER,
    code_lines_added    INTEGER,
    code_lines_removed  INTEGER,
    subagent_count      INTEGER,
    error_count         INTEGER,
    tool_errors         INTEGER,
    user_rejections     INTEGER,
    bash_count          INTEGER,
    bash_interrupted    INTEGER,
    git_operations      INTEGER,
    tasks_completed     INTEGER,
    permission_modes_json TEXT,
    skills_json         TEXT,
    tokens_json         TEXT,
    tools_json          TEXT,
    cost_usd            REAL
);

-- AI/user summaries are NOT stored in the DB. They live in
-- data/session_summary.json (the source of truth) and are read directly at
-- query time. Drop the legacy cache table if an older DB still has it.
DROP TABLE IF EXISTS session_summaries;

CREATE TABLE IF NOT EXISTS project_settings (
    project_path TEXT PRIMARY KEY,
    display_name TEXT,
    hidden       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project_path);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at);
"""


class Store:
    def __init__(self, db_path: Path):
        db_path = Path(db_path)
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._con = sqlite3.connect(str(db_path), check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        # The connection is shared between the background refresh thread and
        # request handlers. WAL lets readers proceed during writes, and the
        # busy timeout retries instead of raising "database is locked".
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA busy_timeout=5000")
        self._summaries_cache: dict[str, str] = {}
        self._summaries_key: tuple[float, int] | None = None
        self._con.executescript(_SCHEMA)
        self._con.commit()
        self._migrate()
        self._backfill_project_names()

    def close(self):
        self._con.close()

    def _migrate(self):
        """Add columns introduced after the original schema. When new columns are
        added to an existing DB, clear the file-tracking table so the next refresh
        re-parses every session and backfills the new fields."""
        cols = {r["name"] for r in self._con.execute("PRAGMA table_info(sessions)")}
        wanted = {
            "git_branch": "TEXT", "branches_json": "TEXT", "activity_json": "TEXT",
            "custom_title": "TEXT", "last_user_prompt": "TEXT",
            "tool_errors": "INTEGER", "user_rejections": "INTEGER",
            "bash_count": "INTEGER", "bash_interrupted": "INTEGER",
            "git_operations": "INTEGER", "tasks_completed": "INTEGER",
            "permission_modes_json": "TEXT", "skills_json": "TEXT",
        }
        added = False
        for name, typ in wanted.items():
            if name not in cols:
                self._con.execute(f"ALTER TABLE sessions ADD COLUMN {name} {typ}")
                added = True
        if added:
            # Force a full re-parse on the next refresh to populate new columns.
            self._con.execute("DELETE FROM files")
            self._con.commit()

    def _backfill_project_names(self):
        rows = self._con.execute(
            "SELECT session_id, project_path FROM sessions WHERE project_name IS NULL AND project_path IS NOT NULL"
        ).fetchall()
        if not rows:
            return
        updates = [
            (path.rstrip("/").split("/")[-1], sid)
            for sid, path in ((r["session_id"], r["project_path"]) for r in rows)
        ]
        self._con.executemany(
            "UPDATE sessions SET project_name = ? WHERE session_id = ?", updates
        )
        self._con.commit()

    # ── file tracking ──────────────────────────────────────────────────────

    def get_file(self, path: str) -> sqlite3.Row | None:
        return self._con.execute(
            "SELECT * FROM files WHERE path = ?", (path,)
        ).fetchone()

    def upsert_file(self, path: str, session_id: str, mtime: float, size: int):
        self._con.execute(
            """INSERT INTO files (path, mtime, size, session_id, parsed_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(path) DO UPDATE SET
                 mtime=excluded.mtime, size=excluded.size,
                 session_id=excluded.session_id, parsed_at=excluded.parsed_at""",
            (path, mtime, size, session_id, time.time()),
        )
        self._con.commit()

    def list_files(self) -> list[sqlite3.Row]:
        return self._con.execute("SELECT path, session_id FROM files").fetchall()

    def delete_file(self, path: str):
        self._con.execute("DELETE FROM files WHERE path = ?", (path,))
        self._con.commit()

    def delete_session(self, session_id: str):
        self._con.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        self._con.commit()

    # ── AI/user session summaries ────────────────────────────────────────────
    # Summaries live ONLY in data/session_summary.json ({session_id: text}) —
    # edited by hand or by scripts/set_summaries.py. They are read directly from
    # that file (mtime-cached in memory), never stored in the DB. The .jsonl
    # files never carry summaries, so nothing is lost on reparse.

    @property
    def summary_file(self) -> Path:
        """Canonical summary file, next to the DB: data/session_summary.json."""
        return self._db_path.parent / "session_summary.json"

    def get_all_summaries(self) -> dict[str, str]:
        """Read {session_id: text} from session_summary.json (mtime-cached)."""
        path = self.summary_file
        try:
            stat = path.stat()
        except OSError:
            self._summaries_cache, self._summaries_key = {}, None
            return {}
        key = (stat.st_mtime, stat.st_size)
        if key != self._summaries_key:
            try:
                raw = path.read_text().strip()
                data = json.loads(raw) if raw else {}
                self._summaries_cache = {
                    str(k): str(v).strip()
                    for k, v in data.items()
                    if isinstance(data, dict) and str(v).strip()
                }
            except (OSError, ValueError):
                self._summaries_cache = {}
            self._summaries_key = key
        return self._summaries_cache

    def get_summary(self, session_id: str) -> str | None:
        return self.get_all_summaries().get(session_id)

    def sessions_missing_summary(self) -> list[dict]:
        """Sessions with no entry in session_summary.json, most recent first."""
        have = set(self.get_all_summaries())
        rows = self._con.execute(
            """SELECT session_id, project_name, custom_title, started_at
               FROM sessions ORDER BY started_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows if r["session_id"] not in have]

    # ── session upsert ─────────────────────────────────────────────────────

    def upsert_session(self, s: dict[str, Any]):
        self._con.execute(
            """INSERT INTO sessions
               (session_id, project_path, project_name, cwd, version,
                git_branch, branches_json, activity_json,
                custom_title, last_user_prompt,
                started_at, ended_at, wall_duration_ms, api_duration_ms,
                user_rounds, assistant_messages, code_lines_added,
                code_lines_removed, subagent_count, error_count,
                tool_errors, user_rejections, bash_count, bash_interrupted,
                git_operations, tasks_completed,
                permission_modes_json, skills_json,
                tokens_json, tools_json, cost_usd)
               VALUES (?,?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?, ?,?,?,?, ?,?, ?,?, ?,?,?)
               ON CONFLICT(session_id) DO UPDATE SET
                 project_path=excluded.project_path,
                 project_name=excluded.project_name,
                 cwd=excluded.cwd, version=excluded.version,
                 git_branch=excluded.git_branch,
                 branches_json=excluded.branches_json,
                 activity_json=excluded.activity_json,
                 custom_title=excluded.custom_title,
                 last_user_prompt=excluded.last_user_prompt,
                 started_at=excluded.started_at, ended_at=excluded.ended_at,
                 wall_duration_ms=excluded.wall_duration_ms,
                 api_duration_ms=excluded.api_duration_ms,
                 user_rounds=excluded.user_rounds,
                 assistant_messages=excluded.assistant_messages,
                 code_lines_added=excluded.code_lines_added,
                 code_lines_removed=excluded.code_lines_removed,
                 subagent_count=excluded.subagent_count,
                 error_count=excluded.error_count,
                 tool_errors=excluded.tool_errors,
                 user_rejections=excluded.user_rejections,
                 bash_count=excluded.bash_count,
                 bash_interrupted=excluded.bash_interrupted,
                 git_operations=excluded.git_operations,
                 tasks_completed=excluded.tasks_completed,
                 permission_modes_json=excluded.permission_modes_json,
                 skills_json=excluded.skills_json,
                 tokens_json=excluded.tokens_json,
                 tools_json=excluded.tools_json,
                 cost_usd=excluded.cost_usd""",
            (
                s["session_id"], s.get("project_path"), s.get("project_name"),
                s.get("cwd"), s.get("version"),
                s.get("git_branch"), json.dumps(s.get("branch_counts", {})),
                json.dumps(s.get("activity", {})),
                s.get("custom_title"), s.get("last_user_prompt"),
                s.get("started_at"), s.get("ended_at"),
                s.get("wall_duration_ms"), s.get("api_duration_ms"),
                s.get("user_rounds", 0), s.get("assistant_messages", 0),
                s.get("code_lines_added", 0), s.get("code_lines_removed", 0),
                s.get("subagent_count", 0), s.get("error_count", 0),
                s.get("tool_errors", 0), s.get("user_rejections", 0),
                s.get("bash_count", 0), s.get("bash_interrupted", 0),
                s.get("git_operations", 0), s.get("tasks_completed", 0),
                json.dumps(s.get("permission_modes", {})),
                json.dumps(s.get("skills_used", {})),
                json.dumps(s.get("tokens_by_model", {})),
                json.dumps(s.get("tools", {})),
                s.get("cost_usd", 0.0),
            ),
        )
        self._con.commit()

    # ── queries ────────────────────────────────────────────────────────────

    def get_session(self, session_id: str) -> dict | None:
        row = self._con.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        if not row:
            return None
        d = _row_to_dict(row)
        settings = self.get_all_project_settings()
        s = settings.get(d.get("project_path") or "", {})
        if s.get("display_name"):
            d["project_name"] = s["display_name"]
        d["summary"] = self.get_summary(session_id)
        return d

    def list_sessions(self, project_path: str | None = None) -> list[dict]:
        if project_path:
            rows = self._con.execute(
                "SELECT * FROM sessions WHERE project_path = ? ORDER BY started_at DESC",
                (project_path,),
            ).fetchall()
        else:
            rows = self._con.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC"
            ).fetchall()
        settings = self.get_all_project_settings()
        summaries = self.get_all_summaries()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            s = settings.get(d.get("project_path") or "", {})
            if s.get("display_name"):
                d["project_name"] = s["display_name"]
            d["hidden"] = bool(s.get("hidden", False))
            d["summary"] = summaries.get(d["session_id"])
            result.append(d)
        return result

    def list_sessions_for_paths(self, project_paths: list[str]) -> list[dict]:
        """Fetch sessions for multiple project paths (used for merged display-name groups)."""
        if not project_paths:
            return []
        placeholders = ",".join("?" * len(project_paths))
        # {placeholders} expands only to "?,?,..."; the values are bound as parameters.
        rows = self._con.execute(
            f"SELECT * FROM sessions WHERE project_path IN ({placeholders}) ORDER BY started_at DESC",  # nosec
            project_paths,
        ).fetchall()
        settings = self.get_all_project_settings()
        summaries = self.get_all_summaries()
        result = []
        for r in rows:
            d = _row_to_dict(r)
            s = settings.get(d.get("project_path") or "", {})
            if s.get("display_name"):
                d["project_name"] = s["display_name"]
            d["hidden"] = bool(s.get("hidden", False))
            d["summary"] = summaries.get(d["session_id"])
            result.append(d)
        return result

    def get_all_project_settings(self) -> dict[str, dict]:
        rows = self._con.execute(
            "SELECT project_path, display_name, hidden FROM project_settings"
        ).fetchall()
        return {
            r["project_path"]: {
                "display_name": r["display_name"],
                "hidden": bool(r["hidden"]),
            }
            for r in rows
        }

    def upsert_project_setting(
        self, project_path: str, display_name: str | None, hidden: bool
    ):
        self._con.execute(
            """INSERT INTO project_settings (project_path, display_name, hidden)
               VALUES (?, ?, ?)
               ON CONFLICT(project_path) DO UPDATE SET
                 display_name=excluded.display_name,
                 hidden=excluded.hidden""",
            (project_path, display_name or None, 1 if hidden else 0),
        )
        self._con.commit()

    def list_projects(self, include_hidden: bool = False) -> list[dict]:
        rows = self._con.execute(
            """SELECT
                 project_path,
                 project_name,
                 COUNT(*) AS session_count,
                 SUM(user_rounds) AS user_rounds,
                 SUM(assistant_messages) AS assistant_messages,
                 SUM(api_duration_ms) AS api_duration_ms,
                 SUM(wall_duration_ms) AS wall_duration_ms,
                 SUM(code_lines_added) AS code_lines_added,
                 SUM(code_lines_removed) AS code_lines_removed,
                 SUM(cost_usd) AS cost_usd,
                 MAX(ended_at) AS last_active,
                 MIN(started_at) AS first_active,
                 tokens_json,
                 tools_json
               FROM sessions
               WHERE project_path IS NOT NULL
               GROUP BY project_path
               ORDER BY last_active DESC"""
        ).fetchall()
        settings = self.get_all_project_settings()
        result = []
        for r in rows:
            d = dict(r)
            path = d["project_path"]
            s = settings.get(path, {})
            d["hidden"] = s.get("hidden", False)
            if not include_hidden and d["hidden"]:
                continue
            d["original_name"] = d.get("project_name")
            if s.get("display_name"):
                d["project_name"] = s["display_name"]
            all_tok, all_tools = _aggregate_project_tokens_tools(
                self._con, path
            )
            d["tokens_by_model"] = all_tok
            d["tools"] = all_tools
            d.pop("tokens_json", None)
            d.pop("tools_json", None)
            result.append(d)
        return result

    def summary(self) -> dict:
        row = self._con.execute(
            """SELECT
                 COUNT(*) AS total_sessions,
                 SUM(user_rounds) AS total_rounds,
                 SUM(assistant_messages) AS total_assistant_messages,
                 SUM(api_duration_ms) AS total_api_ms,
                 SUM(wall_duration_ms) AS total_wall_ms,
                 SUM(code_lines_added) AS total_lines_added,
                 SUM(code_lines_removed) AS total_lines_removed,
                 SUM(cost_usd) AS total_cost,
                 SUM(subagent_count) AS total_subagents,
                 SUM(tool_errors) AS total_tool_errors,
                 SUM(user_rejections) AS total_rejections,
                 SUM(bash_count) AS total_bash,
                 SUM(bash_interrupted) AS total_bash_interrupted,
                 SUM(git_operations) AS total_git_ops,
                 SUM(tasks_completed) AS total_tasks_completed
               FROM sessions"""
        ).fetchone()
        d = dict(row)

        # aggregate tokens/tools globally
        all_tok, all_tools = _aggregate_all_tokens_tools(self._con)
        d["tokens_by_model"] = all_tok
        d["tools"] = all_tools

        # aggregate autonomy (permission modes) and skills globally
        d["permission_modes"] = _aggregate_json_counts(self._con, "permission_modes_json")
        d["skills"] = _aggregate_json_counts(self._con, "skills_json")

        # activity heatmap: per-message buckets (weekday 0=Sun × hour, local time),
        # nested by metric so the UI can toggle all / turns / prompts
        d["activity"] = _aggregate_activity(self._con)

        # daily cost time series
        daily = self._con.execute(
            """SELECT substr(datetime(started_at, 'localtime'), 1, 10) AS date,
                      SUM(cost_usd) AS cost,
                      COUNT(*) AS sessions
               FROM sessions
               WHERE started_at IS NOT NULL
               GROUP BY date
               ORDER BY date"""
        ).fetchall()
        d["daily"] = [dict(r) for r in daily]

        # top projects by cost (exclude hidden)
        hidden_paths = {
            path
            for path, s in self.get_all_project_settings().items()
            if s.get("hidden")
        }
        top_rows = self._con.execute(
            """SELECT project_path, project_name, SUM(cost_usd) AS cost
               FROM sessions WHERE project_name IS NOT NULL
               GROUP BY project_path ORDER BY cost DESC"""
        ).fetchall()
        settings = self.get_all_project_settings()
        merged_top: dict[str, float] = {}
        top_order: list[str] = []
        for r in top_rows:
            if r["project_path"] in hidden_paths:
                continue
            s = settings.get(r["project_path"], {})
            name = s.get("display_name") or r["project_name"]
            if name not in merged_top:
                merged_top[name] = 0.0
                top_order.append(name)
            merged_top[name] += r["cost"] or 0.0
        d["top_projects"] = sorted(
            [{"project_name": n, "cost": merged_top[n]} for n in top_order],
            key=lambda x: x["cost"],
            reverse=True,
        )

        return d


# ── helpers ────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    json_cols = {
        "tokens_json": "tokens_by_model",
        "tools_json": "tools",
        "permission_modes_json": "permission_modes",
        "skills_json": "skills_used",
        "branches_json": "branches",
        "activity_json": "activity",
    }
    for key, out_key in json_cols.items():
        if key in d:
            try:
                d[out_key] = json.loads(d[key]) if d[key] else {}
            except Exception:
                d[out_key] = {}
            del d[key]
    return d


def _aggregate_project_tokens_tools(con: sqlite3.Connection, project_path: str):
    rows = con.execute(
        "SELECT tokens_json, tools_json FROM sessions WHERE project_path = ?",
        (project_path,),
    ).fetchall()
    return _merge_token_tool_rows(rows)


def _aggregate_activity(con: sqlite3.Connection) -> dict[str, list[dict]]:
    """Sum per-session weekday×hour message buckets across all sessions, returning
    {metric: [{dow, hour, count}, ...]} for metric in all/turns/prompts."""
    cats = ("all", "turns", "prompts")
    merged: dict[str, dict[str, int]] = {c: {} for c in cats}
    for r in con.execute("SELECT activity_json AS j FROM sessions"):
        try:
            obj = json.loads(r["j"] or "{}")
        # Best-effort parse; skip malformed rows.
        except Exception:  # nosec B112
            continue
        for c in cats:
            for k, v in (obj.get(c) or {}).items():
                merged[c][k] = merged[c].get(k, 0) + (v or 0)
    out: dict[str, list[dict]] = {}
    for c in cats:
        rows = []
        for k, count in merged[c].items():
            try:
                dow, hour = k.split("-")
                rows.append({"dow": int(dow), "hour": int(hour), "count": count})
            except (ValueError, AttributeError):
                continue
        out[c] = rows
    return out


def _aggregate_json_counts(con: sqlite3.Connection, column: str) -> dict[str, int]:
    """Sum a per-session JSON object of {key: count} across all sessions."""
    merged: dict[str, int] = {}
    # column is an internal literal (permission_modes_json/skills_json), never user input.
    for r in con.execute(f"SELECT {column} AS j FROM sessions"):  # nosec
        try:
            obj = json.loads(r["j"] or "{}")
        # Best-effort parse; skip malformed rows.
        except Exception:  # nosec B112
            continue
        for k, v in obj.items():
            merged[k] = merged.get(k, 0) + (v or 0)
    return merged


def _aggregate_all_tokens_tools(con: sqlite3.Connection):
    rows = con.execute("SELECT tokens_json, tools_json FROM sessions").fetchall()
    return _merge_token_tool_rows(rows)


def _merge_token_tool_rows(rows) -> tuple[dict, dict]:
    merged_tok: dict[str, dict] = {}
    merged_tools: dict[str, int] = {}
    for r in rows:
        try:
            tok = json.loads(r["tokens_json"] or "{}")
        except Exception:
            tok = {}
        for model, counts in tok.items():
            if model not in merged_tok:
                merged_tok[model] = {"input": 0, "output": 0, "cache_read": 0,
                                     "cache_write_5m": 0, "cache_write_1h": 0}
            for k, v in counts.items():
                merged_tok[model][k] = merged_tok[model].get(k, 0) + (v or 0)
        try:
            tools = json.loads(r["tools_json"] or "{}")
        except Exception:
            tools = {}
        for name, cnt in tools.items():
            merged_tools[name] = merged_tools.get(name, 0) + (cnt or 0)
    return merged_tok, merged_tools
