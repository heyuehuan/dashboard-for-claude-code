from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_file(path: str | Path) -> dict[str, Any]:
    """
    Stream a session .jsonl file line-by-line and return a SessionStats dict.
    Never loads the entire file into memory.
    """
    stats: dict[str, Any] = {
        "session_id": None,
        "project_path": None,
        "project_name": None,
        "cwd": None,
        "version": None,
        "git_branch": None,      # primary (most-active) branch, derived at end
        "branch_counts": {},     # branch -> activity (lines tagged with it)
        # weekday×hour message buckets (local time), nested all ⊇ turns ⊇ prompts
        "activity": {"all": {}, "turns": {}, "prompts": {}},
        "custom_title": None,
        "last_user_prompt": None,
        "started_at": None,
        "ended_at": None,
        "wall_duration_ms": None,
        "api_duration_ms": 0,
        "user_rounds": 0,
        "assistant_messages": 0,
        "code_lines_added": 0,
        "code_lines_removed": 0,
        "subagent_count": 0,
        "error_count": 0,
        # reliability / activity signals
        "tool_errors": 0,
        "user_rejections": 0,
        "bash_count": 0,
        "bash_interrupted": 0,
        "git_operations": 0,
        "tasks_completed": 0,
        "permission_modes": {},
        "skills_used": {},
        "tokens_by_model": {},
        "tools": {},
        "_req_prev": {},
    }

    first_ts: str | None = None
    last_ts: str | None = None

    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue

            ltype = line.get("type")

            # Track timestamps from any line that carries one
            ts = line.get("timestamp")
            if ts:
                if first_ts is None or ts < first_ts:
                    first_ts = ts
                if last_ts is None or ts > last_ts:
                    last_ts = ts
                _bucket_activity(stats, ts, ltype, line)

            # Pull session metadata from first user line
            if stats["session_id"] is None and line.get("sessionId"):
                stats["session_id"] = line["sessionId"]
            if stats["cwd"] is None and line.get("cwd"):
                stats["cwd"] = line["cwd"]
            if stats["version"] is None and line.get("version"):
                stats["version"] = line["version"]
            # Track activity per branch (a session can switch branches); the
            # most-active branch becomes the primary, derived after the stream.
            gb = line.get("gitBranch")
            if gb:
                stats["branch_counts"][gb] = stats["branch_counts"].get(gb, 0) + 1
            if line.get("customTitle"):
                stats["custom_title"] = line["customTitle"]

            # Permission mode in effect (autonomy profile)
            pm = line.get("permissionMode")
            if pm:
                stats["permission_modes"][pm] = stats["permission_modes"].get(pm, 0) + 1

            # Tool results (on user lines) carry the authoritative diff/exec data
            tur = line.get("toolUseResult")
            if isinstance(tur, dict):
                _handle_tool_result(tur, stats)

            if ltype == "user":
                _handle_user(line, stats)

            elif ltype == "assistant":
                _handle_assistant(line, stats)

            elif ltype == "system":
                _handle_system(line, stats)

            elif ltype == "custom-title":
                if line.get("customTitle"):
                    stats["custom_title"] = line["customTitle"]

            elif ltype == "attachment":
                _handle_attachment(line, stats)

    _derive_primary_branch(stats)

    stats["started_at"] = first_ts
    stats["ended_at"] = last_ts
    if first_ts and last_ts:
        try:
            # fromisoformat tolerates timestamps with or without fractional
            # seconds; strptime with a fixed "%...%fZ" format would silently
            # drop the duration for any timestamp lacking microseconds.
            t0 = datetime.fromisoformat(first_ts.replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(last_ts.replace("Z", "+00:00"))
            stats["wall_duration_ms"] = int((t1 - t0).total_seconds() * 1000)
        # Best-effort duration; skip when timestamps are unparseable.
        except Exception:  # nosec B110
            pass

    return stats


def _handle_user(line: dict, stats: dict):
    msg = line.get("message", {})
    content = msg.get("content", "")
    # Real user input: has promptId and string content (not a tool result list)
    if line.get("promptId") and isinstance(content, str):
        stats["user_rounds"] += 1
        text = content.strip()
        if text:
            stats["last_user_prompt"] = text[:280]
    elif isinstance(content, list):
        # list content with tool_result items → tool result, not a round.
        # Count failed / rejected tool results for the reliability metric.
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_result" and block.get("is_error"):
                c = block.get("content", "")
                text = c if isinstance(c, str) else json.dumps(c)
                if "doesn't want to proceed" in text or "tool use was rejected" in text:
                    stats["user_rejections"] += 1
                else:
                    stats["tool_errors"] += 1


def _bucket_activity(stats: dict, ts: str, ltype: str, line: dict):
    """Bucket one message into a weekday×hour cell (local time) for the heatmap.
    Three nested series so the UI can toggle the metric:
      all     – every timestamped message
      turns   – user prompts + assistant replies (conversation turns)
      prompts – real user prompts only (promptId + string content)."""
    try:
        lt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
    except Exception:
        return
    key = f"{(lt.weekday() + 1) % 7}-{lt.hour}"  # %w convention: 0=Sun..6=Sat
    act = stats["activity"]
    act["all"][key] = act["all"].get(key, 0) + 1
    if ltype == "assistant":
        act["turns"][key] = act["turns"].get(key, 0) + 1
    elif ltype == "user":
        msg = line.get("message") or {}
        if line.get("promptId") and isinstance(msg.get("content"), str):
            act["turns"][key] = act["turns"].get(key, 0) + 1
            act["prompts"][key] = act["prompts"].get(key, 0) + 1


def _derive_primary_branch(stats: dict):
    """Pick the most-active branch as primary. Ties break toward the longer name
    (feature branches over 'main'/'master', which sessions tend to end on)."""
    bc = stats.get("branch_counts") or {}
    if bc:
        stats["git_branch"] = max(bc.items(), key=lambda kv: (kv[1], len(kv[0])))[0]


def _handle_attachment(line: dict, stats: dict):
    att = line.get("attachment") or {}
    if att.get("type") == "invoked_skills":
        for sk in att.get("skills") or []:
            name = sk.get("name") or "unknown"
            stats["skills_used"][name] = stats["skills_used"].get(name, 0) + 1


def _handle_tool_result(tur: dict, stats: dict):
    # Accurate code churn from the actual diff (covers Edit, MultiEdit, Write/create)
    sp = tur.get("structuredPatch")
    if isinstance(sp, list):
        for hunk in sp:
            for ln in (hunk.get("lines") or []):
                if ln.startswith("+"):
                    stats["code_lines_added"] += 1
                elif ln.startswith("-"):
                    stats["code_lines_removed"] += 1

    # Bash command execution (stdout/stderr/interrupted are Bash-specific)
    if "stdout" in tur or "stderr" in tur:
        stats["bash_count"] += 1
        if tur.get("interrupted"):
            stats["bash_interrupted"] += 1

    if tur.get("gitOperation"):
        stats["git_operations"] += 1

    sc = tur.get("statusChange")
    if isinstance(sc, dict) and sc.get("to") == "completed":
        stats["tasks_completed"] += 1


def _handle_assistant(line: dict, stats: dict):
    msg = line.get("message", {})
    if line.get("isApiErrorMessage"):
        stats["error_count"] += 1
        return

    model = msg.get("model", "")
    usage = msg.get("usage") or {}

    # tool_use blocks in this line's content
    line_tools: dict[str, int] = {}
    content = msg.get("content") or []
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                name = block.get("name", "unknown")
                line_tools[name] = line_tools.get(name, 0) + 1

    if model and model != "<synthetic>":
        request_id = line.get("requestId")
        if request_id:
            # The JSONL records each API call multiple times (different UUIDs, same
            # requestId). Streaming events duplicate with incomplete output_tokens;
            # the last entry has the final values. Roll back the previous
            # accumulation (tokens AND tool_use counts) so we always end up with
            # the last-seen values for each API call — otherwise a tool_use that
            # appears in N duplicate entries gets counted N times.
            prev = stats["_req_prev"].get(request_id)
            if prev:
                _subtract_tokens(stats["tokens_by_model"], prev["model"], prev["usage"])
                for name, cnt in (prev.get("tools") or {}).items():
                    stats["tools"][name] = stats["tools"].get(name, 0) - cnt
            else:
                stats["assistant_messages"] += 1
            stats["_req_prev"][request_id] = {
                "model": model, "usage": usage, "tools": line_tools,
            }
        else:
            stats["assistant_messages"] += 1
        _accumulate_tokens(stats["tokens_by_model"], model, usage)

    # Apply this line's tool counts. For lines with a requestId we rolled back any
    # earlier duplicate above, so this yields last-entry-wins per API call.
    for name, cnt in line_tools.items():
        stats["tools"][name] = stats["tools"].get(name, 0) + cnt


def _handle_system(line: dict, stats: dict):
    if line.get("subtype") == "turn_duration":
        stats["api_duration_ms"] += line.get("durationMs", 0)


def _subtract_tokens(tokens_by_model: dict, model: str, usage: dict):
    if model not in tokens_by_model:
        return
    t = tokens_by_model[model]
    t["input"]         -= usage.get("input_tokens", 0) or 0
    t["output"]        -= usage.get("output_tokens", 0) or 0
    t["cache_read"]    -= usage.get("cache_read_input_tokens", 0) or 0
    cc = usage.get("cache_creation") or {}
    write_5m = cc.get("ephemeral_5m_input_tokens", 0) or 0
    write_1h = cc.get("ephemeral_1h_input_tokens", 0) or 0
    if write_5m == 0 and write_1h == 0:
        write_5m = usage.get("cache_creation_input_tokens", 0) or 0
    t["cache_write_5m"] -= write_5m
    t["cache_write_1h"] -= write_1h


def _accumulate_tokens(tokens_by_model: dict, model: str, usage: dict):
    if model not in tokens_by_model:
        tokens_by_model[model] = {
            "input": 0, "output": 0, "cache_read": 0,
            "cache_write_5m": 0, "cache_write_1h": 0,
        }
    t = tokens_by_model[model]
    t["input"]  += usage.get("input_tokens", 0) or 0
    t["output"] += usage.get("output_tokens", 0) or 0
    t["cache_read"] += usage.get("cache_read_input_tokens", 0) or 0

    # cache_creation breakdown: prefer ephemeral sub-keys, fall back to total
    cc = usage.get("cache_creation") or {}
    write_5m = cc.get("ephemeral_5m_input_tokens", 0) or 0
    write_1h = cc.get("ephemeral_1h_input_tokens", 0) or 0
    # If sub-keys are both 0 but cache_creation_input_tokens is set, put in 5m bucket
    if write_5m == 0 and write_1h == 0:
        write_5m = usage.get("cache_creation_input_tokens", 0) or 0
    t["cache_write_5m"] += write_5m
    t["cache_write_1h"] += write_1h


def merge_stats(base: dict, extra: dict) -> dict:
    """Merge subagent stats into a parent session stats dict in-place."""
    base["api_duration_ms"] = (base.get("api_duration_ms") or 0) + (extra.get("api_duration_ms") or 0)
    base["user_rounds"]     = (base.get("user_rounds") or 0)     + (extra.get("user_rounds") or 0)
    base["assistant_messages"] = (base.get("assistant_messages") or 0) + (extra.get("assistant_messages") or 0)
    base["code_lines_added"]   = (base.get("code_lines_added") or 0)   + (extra.get("code_lines_added") or 0)
    base["code_lines_removed"] = (base.get("code_lines_removed") or 0) + (extra.get("code_lines_removed") or 0)
    base["error_count"] = (base.get("error_count") or 0) + (extra.get("error_count") or 0)
    base["subagent_count"] = (base.get("subagent_count") or 0) + 1

    for f in ("tool_errors", "user_rejections", "bash_count", "bash_interrupted",
              "git_operations", "tasks_completed"):
        base[f] = (base.get(f) or 0) + (extra.get(f) or 0)

    # Merge permission modes, skills, and per-branch activity
    for d in ("permission_modes", "skills_used", "branch_counts"):
        base.setdefault(d, {})
        for k, v in (extra.get(d) or {}).items():
            base[d][k] = base[d].get(k, 0) + (v or 0)
    _derive_primary_branch(base)  # re-pick primary after merging subagent activity

    # Merge weekday×hour activity buckets (nested by metric)
    base.setdefault("activity", {"all": {}, "turns": {}, "prompts": {}})
    for cat in ("all", "turns", "prompts"):
        base["activity"].setdefault(cat, {})
        for k, v in ((extra.get("activity") or {}).get(cat) or {}).items():
            base["activity"][cat][k] = base["activity"][cat].get(k, 0) + (v or 0)

    # Merge tokens
    for model, counts in (extra.get("tokens_by_model") or {}).items():
        if model not in base["tokens_by_model"]:
            base["tokens_by_model"][model] = {
                "input": 0, "output": 0, "cache_read": 0,
                "cache_write_5m": 0, "cache_write_1h": 0,
            }
        for k, v in counts.items():
            base["tokens_by_model"][model][k] = base["tokens_by_model"][model].get(k, 0) + (v or 0)

    # Merge tools
    for name, cnt in (extra.get("tools") or {}).items():
        base["tools"][name] = base["tools"].get(name, 0) + cnt

    # Extend time window
    for attr, cmp in (("started_at", min), ("ended_at", max)):
        a = base.get(attr)
        b = extra.get(attr)
        if a and b:
            base[attr] = cmp(a, b)
        elif b:
            base[attr] = b

    return base
