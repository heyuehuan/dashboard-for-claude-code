#!/usr/bin/env python3
"""Print compact digests for sessions that still need an AI summary.

Used by the summarization workflow: Claude reads these digests and writes a
one/two-sentence "[Claude Summary] ..." for each, then feeds them to
scripts/set_summaries.py, which merges them into data/session_summary.json.

Usage:
  python scripts/session_digest.py [N] [--offset M]

Prints up to N (default 8) sessions missing a summary, most recent first.
Each digest is delimited so it's easy to read and attribute back to a session_id.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from claude_dashboard.store import Store  # noqa: E402

DB = Path(os.environ.get("DASHBOARD_DB") or ROOT / "data" / "usage.db")


def _clip(s: str, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[:n] + "…"


def _main_file(con, session_id: str) -> str | None:
    for r in con.execute(
        "SELECT path FROM files WHERE session_id = ?", (session_id,)
    ):
        if r["path"].endswith(f"{session_id}.jsonl"):
            return r["path"]
    return None


def _text_of(content) -> str | None:
    """Pull human-readable text from a message content (string or block list)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip():
                parts.append(b["text"])
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(parts) if parts else None
    return None


def _is_noise(text: str) -> bool:
    s = text.lstrip()
    return s.startswith("<local-command-caveat") or s.startswith("<command-name") \
        or s.startswith("<system-reminder") or s.startswith("Caveat:")


def extract(path: str) -> dict:
    first_prompt = None      # first real typed prompt (promptId + string)
    first_user_any = None    # fallback: first non-noise user text of any shape
    last_assistant = None
    compact = None
    for line in open(path, encoding="utf-8", errors="replace"):
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = o.get("message") or {}
        if o.get("isCompactSummary"):
            compact = _text_of(msg.get("content"))
            continue
        t = o.get("type")
        if t == "user":
            txt = _text_of(msg.get("content"))
            if not txt or _is_noise(txt) or "tool_result" in str(msg.get("content"))[:40]:
                continue
            if first_user_any is None:
                first_user_any = txt
            if first_prompt is None and o.get("promptId") and isinstance(msg.get("content"), str):
                first_prompt = txt
        elif t == "assistant":
            txt = _text_of(msg.get("content"))
            if txt and txt.strip():
                last_assistant = txt
    return {
        "first_prompt": first_prompt or first_user_any,
        "last_assistant": last_assistant,
        "compact": compact,
    }


def main():
    args = [a for a in sys.argv[1:]]
    n = 8
    offset = 0
    if args and args[0].isdigit():
        n = int(args[0])
    if "--offset" in args:
        offset = int(args[args.index("--offset") + 1])

    store = Store(DB)
    con = store._con
    missing = store.sessions_missing_summary()
    total = len(missing)
    batch = missing[offset:offset + n]
    print(f"### {total} sessions missing a summary; showing {len(batch)} (offset {offset})\n")
    for m in batch:
        sid = m["session_id"]
        row = con.execute(
            """SELECT project_name, git_branch, custom_title, started_at,
                      wall_duration_ms, cost_usd, code_lines_added, code_lines_removed,
                      user_rounds, tools_json, last_user_prompt
               FROM sessions WHERE session_id = ?""",
            (sid,),
        ).fetchone()
        d = dict(row) if row else {}
        tools = {}
        try:
            tools = json.loads(d.get("tools_json") or "{}")
        # Best-effort parse; an empty tools dict is an acceptable fallback.
        except Exception:  # nosec B110
            pass
        top_tools = ", ".join(
            f"{k}×{v}" for k, v in sorted(tools.items(), key=lambda x: -x[1])[:6]
        )
        path = _main_file(con, sid)
        ext = extract(path) if path else {"first_prompt": None, "last_assistant": None, "compact": None}

        print("=" * 78)
        print(f"SESSION_ID: {sid}")
        print(f"project={d.get('project_name')}  branch={d.get('git_branch')}  "
              f"title={d.get('custom_title')}")
        print(f"started={d.get('started_at')}  dur_ms={d.get('wall_duration_ms')}  "
              f"cost=${(d.get('cost_usd') or 0):.2f}  rounds={d.get('user_rounds')}  "
              f"lines=+{d.get('code_lines_added')}/-{d.get('code_lines_removed')}")
        print(f"tools: {top_tools}")
        if ext["compact"]:
            print(f"COMPACT_SUMMARY: {_clip(ext['compact'], 1400)}")
        if ext["first_prompt"]:
            print(f"FIRST_PROMPT: {_clip(ext['first_prompt'], 600)}")
        if ext["last_assistant"]:
            print(f"LAST_ASSISTANT: {_clip(ext['last_assistant'], 800)}")
        if not ext["compact"] and not ext["first_prompt"] and d.get("last_user_prompt"):
            print(f"LAST_USER_PROMPT: {_clip(d['last_user_prompt'], 400)}")
        print()
    store.close()


if __name__ == "__main__":
    main()
