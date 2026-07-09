#!/usr/bin/env python3
"""Generate a self-contained *demo* database full of synthetic placeholder data.

This never reads your real ~/.claude logs. It writes an isolated SQLite file you
can point the dashboard at to produce screenshots or try the UI without exposing
any personal project names, paths, or costs:

    python scripts/demo_data.py /tmp/demo.db
    DASHBOARD_DB=/tmp/demo.db DASHBOARD_NO_SCAN=1 python -m claude_dashboard

The data is deterministic (seeded), so re-running yields identical output.
"""
from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as a plain script (python scripts/demo_data.py) as well as -m.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from claude_dashboard.pricing import estimate_cost  # noqa: E402
from claude_dashboard.store import Store  # noqa: E402

# Fictional projects — nothing here maps to a real user or repository.
_PROJECTS = [
    ("acme-storefront", "/Users/dev/code/acme-storefront", 1.6),
    ("billing-service", "/Users/dev/code/billing-service", 1.3),
    ("ml-pipeline", "/Users/dev/code/ml-pipeline", 1.1),
    ("mobile-app", "/Users/dev/code/mobile-app", 0.9),
    ("infra-terraform", "/Users/dev/work/infra-terraform", 0.7),
    ("docs-site", "/Users/dev/code/docs-site", 0.5),
    ("data-warehouse", "/Users/dev/work/data-warehouse", 0.4),
    ("throwaway-poc", "/Users/dev/code/throwaway-poc", 0.25),
]

# Rename / tag / hide overrides. A display name containing a "/" renders the
# prefix as a colored tag pill (e.g. "work/acme-storefront" → a "work" tag),
# demonstrating the project rename + tagging feature. One project is hidden to
# show the hide control: it drops out of the overview and Projects tab but still
# appears (marked hidden) in Settings.
_PROJECT_SETTINGS = {
    "/Users/dev/code/acme-storefront": ("work/acme-storefront", False),
    "/Users/dev/code/billing-service": ("work/billing-service", False),
    "/Users/dev/code/mobile-app": ("work/mobile-app", False),
    "/Users/dev/code/ml-pipeline": ("research/ml-pipeline", False),
    "/Users/dev/work/data-warehouse": ("research/data-warehouse", False),
    "/Users/dev/work/infra-terraform": ("ops/infra-terraform", False),
    "/Users/dev/code/docs-site": ("personal/docs-site", False),
    "/Users/dev/code/throwaway-poc": ("personal/throwaway-poc", True),
}

_MODELS = [
    ("claude-opus-4-8", 0.30),
    ("claude-sonnet-4-6", 0.45),
    ("claude-haiku-4-5", 0.20),
    ("claude-fable-5", 0.05),
]

_TOOLS = ["Bash", "Read", "Edit", "Grep", "Write", "TodoWrite",
          "Task", "Glob", "WebFetch", "MultiEdit"]

_SKILLS = ["code-review", "frontend-design", "verify", "dataviz",
           "security-review", "run", "simplify"]

_PERMISSION_MODES = [
    ("default", 0.55),
    ("acceptEdits", 0.30),
    ("plan", 0.10),
    ("bypassPermissions", 0.05),
]

_BRANCHES = ["main", "develop", "feature/checkout", "fix/flaky-test",
             "feature/api-v2", "chore/deps"]

_PROMPTS = [
    "Refactor the checkout flow to use the new pricing module",
    "Add tests for the retry logic and fix the flaky case",
    "Investigate the slow query on the orders endpoint",
    "Wire up the settings page to the new API",
    "Write a migration for the audit-log table",
]


def _weighted(rng: random.Random, choices: list[tuple[str, float]]) -> str:
    keys = [c[0] for c in choices]
    weights = [c[1] for c in choices]
    return rng.choices(keys, weights=weights, k=1)[0]


def _make_tokens(rng: random.Random, model: str, scale: float) -> dict:
    base = int(scale * rng.randint(40_000, 220_000))
    return {
        model: {
            "input": int(base * rng.uniform(0.06, 0.14)),
            "output": int(base * rng.uniform(0.04, 0.10)),
            "cache_read": int(base * rng.uniform(0.6, 1.4)),
            "cache_write_5m": int(base * rng.uniform(0.05, 0.2)),
            "cache_write_1h": int(base * rng.uniform(0.0, 0.05)),
        }
    }


def _bucket(activity: dict, dow: int, hour: int, msgs: int, turns: int, prompts: int):
    key = f"{dow}-{hour}"
    for cat, n in (("all", msgs), ("turns", turns), ("prompts", prompts)):
        if n:
            activity[cat][key] = activity[cat].get(key, 0) + n


def build(store: Store, *, seed: int = 7, n_sessions: int = 60, days: int = 35) -> None:
    # Non-crypto RNG: seeded only for reproducible synthetic demo data.
    rng = random.Random(seed)  # nosec B311
    now = datetime.now(timezone.utc)

    for i in range(n_sessions):
        name, path, weight = rng.choices(
            _PROJECTS, weights=[p[2] for p in _PROJECTS], k=1
        )[0]

        # Bias sessions toward weekday working hours for a realistic heatmap.
        day_offset = rng.randint(0, days - 1)
        day = now - timedelta(days=day_offset)
        # weekday(): Mon=0..Sun=6 → nudge weekends to be sparse
        if day.weekday() >= 5 and rng.random() < 0.7:
            day -= timedelta(days=rng.randint(1, 2))
        hour = rng.choices(
            range(24),
            weights=[1, 1, 1, 1, 1, 1, 2, 3, 5, 8, 9, 9, 7, 8, 9, 9, 8, 6, 4, 4, 3, 3, 2, 1],
            k=1,
        )[0]
        start = day.replace(hour=hour, minute=rng.randint(0, 59), second=0, microsecond=0)

        # Tokens across 1-2 models
        model = _weighted(rng, _MODELS)
        tokens = _make_tokens(rng, model, weight)
        if rng.random() < 0.4:
            other = _weighted(rng, _MODELS)
            if other != model:
                for m, t in _make_tokens(rng, other, weight * 0.4).items():
                    tokens[m] = t

        # Derive timing FROM the tokens so the numbers stay internally
        # consistent. API processing time tracks output generation (~50 tok/s)
        # plus a little prompt/cache-processing overhead; wall time adds the
        # user's own thinking/reading time on top (so wall > api always).
        out_tok = sum(t.get("output", 0) for t in tokens.values())
        in_tok = sum(t.get("input", 0) for t in tokens.values())
        cw_tok = sum(t.get("cache_write_5m", 0) + t.get("cache_write_1h", 0)
                     for t in tokens.values())
        throughput = rng.uniform(45, 62)  # output tokens/sec
        api_ms = int(out_tok / throughput * 1000
                     + (in_tok + 0.15 * cw_tok) / 7000 * 1000)
        api_ms = max(api_ms, 15_000)
        wall_ms = int(api_ms / rng.uniform(0.28, 0.7))
        wall_min = max(1, wall_ms // 60_000)
        end = start + timedelta(milliseconds=wall_ms)

        rounds = max(1, min(30, int(wall_min / rng.uniform(4, 12))))
        assistant = rounds + rng.randint(rounds, rounds * 3)

        tools: dict[str, int] = {}
        for _ in range(rng.randint(4, len(_TOOLS))):
            t = rng.choice(_TOOLS)
            tools[t] = tools.get(t, 0) + rng.randint(1, 14)

        skills: dict[str, int] = {}
        if rng.random() < 0.5:
            for _ in range(rng.randint(1, 3)):
                s = rng.choice(_SKILLS)
                skills[s] = skills.get(s, 0) + rng.randint(1, 3)

        modes: dict[str, int] = {}
        for _ in range(rng.randint(2, 6)):
            modes[_weighted(rng, _PERMISSION_MODES)] = (
                modes.get(_weighted(rng, _PERMISSION_MODES), 0) + rng.randint(1, 8)
            )
        # ensure at least one mode present
        primary_mode = _weighted(rng, _PERMISSION_MODES)
        modes[primary_mode] = modes.get(primary_mode, 0) + rng.randint(3, 12)

        # Activity: spread messages over the hours the session spanned.
        activity = {"all": {}, "turns": {}, "prompts": {}}
        span_hours = max(1, min(6, (wall_min // 45) + 1))
        dow = (start.weekday() + 1) % 7  # 0=Sun..6=Sat, matching parser
        remaining_msgs = assistant + rounds
        for h in range(span_hours):
            hh = (start.hour + h) % 24
            share = remaining_msgs // (span_hours - h) if span_hours - h else remaining_msgs
            t_share = max(0, int(share * 0.7))
            p_share = max(0, rounds // span_hours)
            _bucket(activity, dow, hh, share, t_share, p_share)
            remaining_msgs -= share

        branch = rng.choice(_BRANCHES)
        cost = estimate_cost(tokens).get("total", 0.0)

        store.upsert_session({
            "session_id": f"demo-{i:04d}",
            "project_path": path,
            "project_name": name,
            "cwd": path,
            "version": "2.1.0",
            "git_branch": branch,
            "branch_counts": {branch: rounds, "main": rng.randint(1, 4)},
            "activity": activity,
            "custom_title": None,
            "last_user_prompt": rng.choice(_PROMPTS),
            "started_at": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "ended_at": end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "wall_duration_ms": wall_ms,
            "api_duration_ms": api_ms,
            "user_rounds": rounds,
            "assistant_messages": assistant,
            "code_lines_added": rng.randint(10, 900),
            "code_lines_removed": rng.randint(0, 400),
            "subagent_count": rng.randint(0, 4),
            "error_count": rng.randint(0, 2),
            "tool_errors": rng.randint(0, 6),
            "user_rejections": rng.randint(0, 3),
            "bash_count": tools.get("Bash", 0),
            "bash_interrupted": rng.randint(0, 2),
            "git_operations": rng.randint(0, 8),
            "tasks_completed": rng.randint(0, 6),
            "permission_modes": modes,
            "skills_used": skills,
            "tokens_by_model": tokens,
            "tools": tools,
            "cost_usd": cost,
        })

    # Apply rename / tag / hide overrides (see _PROJECT_SETTINGS).
    for path, (display_name, hidden) in _PROJECT_SETTINGS.items():
        store.upsert_project_setting(path, display_name, hidden)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data") / "demo.db"
    if out.exists():
        out.unlink()
    store = Store(out)
    build(store)
    n = store.summary()["total_sessions"]
    store.close()
    print(f"Wrote {n} synthetic sessions to {out}")


if __name__ == "__main__":
    main()
