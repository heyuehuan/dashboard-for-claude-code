from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path

from claude_dashboard.parser import parse_file, merge_stats
from claude_dashboard.pricing import estimate_cost
from claude_dashboard.store import Store


_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


@dataclass
class RefreshReport:
    added: int = 0
    updated: int = 0
    skipped: int = 0
    pruned: int = 0
    errors: list[str] = field(default_factory=list)


def refresh(store: Store, prune: bool = False) -> RefreshReport:
    """Scan ~/.claude/projects and update the cache.

    With prune=True, sessions whose transcript file no longer exists on disk
    are removed from the DB. Default is to keep them: Claude Code deletes old
    transcripts after `cleanupPeriodDays`, and the cache deliberately preserves
    that history.
    """
    report = RefreshReport()

    if not _CLAUDE_PROJECTS.exists():
        return report

    for project_dir in sorted(_CLAUDE_PROJECTS.iterdir()):
        if not project_dir.is_dir():
            continue

        project_path = _decode_project_path(project_dir.name)

        # Collect top-level session jsonl files (not subagent files)
        session_files: dict[str, Path] = {}  # session_id -> path
        for f in project_dir.iterdir():
            if f.suffix == ".jsonl" and f.is_file():
                # UUID based name
                session_id = f.stem
                session_files[session_id] = f

        for session_id, jsonl_path in session_files.items():
            # Everything below can hit files deleted between iterdir() and here
            # (e.g. Claude Code's own cleanup); one vanished session must not
            # kill the whole scan — especially the silent startup thread.
            try:
                stat = os.stat(jsonl_path)
                mtime = stat.st_mtime
                size = stat.st_size

                # Subagent files are checked separately via _subagents_changed below.
                subagent_paths = _find_subagents(jsonl_path)

                cached = store.get_file(str(jsonl_path))
                if cached and cached["mtime"] == mtime and cached["size"] == size:
                    # Check if subagents changed
                    if not _subagents_changed(store, subagent_paths):
                        report.skipped += 1
                        continue
                    is_update = True
                else:
                    is_update = bool(cached)

                stats = parse_file(jsonl_path)
                stats["session_id"] = stats["session_id"] or session_id
                # Use cwd from the file itself — it's the authoritative path.
                # The folder-name encoding is lossy (dashes = slashes), so names
                # like "server-management" would decode incorrectly if we relied on it.
                cwd = stats.get("cwd") or project_path
                stats["project_path"] = cwd
                stats["project_name"] = cwd.rstrip("/").split("/")[-1] if cwd else project_dir.name

                # Merge subagent stats
                for sub_path in subagent_paths:
                    try:
                        sub_stats = parse_file(sub_path)
                        merge_stats(stats, sub_stats)
                        sub_stat = os.stat(sub_path)
                        store.upsert_file(
                            str(sub_path), session_id,
                            sub_stat.st_mtime, sub_stat.st_size
                        )
                    except Exception as e:
                        report.errors.append(f"{sub_path}: {e}")

                # Estimate cost
                cost_result = estimate_cost(stats.get("tokens_by_model", {}))
                stats["cost_usd"] = cost_result.get("total", 0.0)
                stats.pop("_req_prev", None)

                store.upsert_session(stats)
                store.upsert_file(str(jsonl_path), stats["session_id"], mtime, size)

                if is_update:
                    report.updated += 1
                else:
                    report.added += 1

            except FileNotFoundError:
                # Deleted mid-scan; the stale DB entry is handled by prune.
                continue
            except Exception as e:
                report.errors.append(f"{jsonl_path}: {e}")

    if prune:
        report.pruned = _prune_missing(store)

    return report


def _decode_project_path(encoded: str) -> str:
    """Convert `-Users-alice-projects-MyApp` → `/Users/alice/projects/MyApp`."""
    # Strip a single leading dash, then replace remaining dashes with slashes.
    # This is a heuristic — consecutive dashes in real path segments would break it,
    # but Claude Code itself uses the same encoding scheme.
    if encoded.startswith("-"):
        encoded = encoded[1:]
    return "/" + encoded.replace("-", "/")


def _find_subagents(session_jsonl: Path) -> list[Path]:
    """Look for subagents/<session_id>/subagents/agent-*.jsonl patterns."""
    results = []
    # Pattern: ~/.claude/projects/<project>/<session_id>/subagents/agent-*.jsonl
    session_dir = session_jsonl.parent / session_jsonl.stem
    if session_dir.is_dir():
        sub_dir = session_dir / "subagents"
        if sub_dir.is_dir():
            for f in sorted(sub_dir.glob("agent-*.jsonl")):
                if f.is_file():
                    results.append(f)
    return results


def _subagents_changed(store: Store, paths: list[Path]) -> bool:
    for p in paths:
        try:
            stat = os.stat(p)
        except FileNotFoundError:
            return True  # vanished since listing — reparse to drop its stats
        cached = store.get_file(str(p))
        if not cached or cached["mtime"] != stat.st_mtime or cached["size"] != stat.st_size:
            return True
    return False


def _prune_missing(store: Store) -> int:
    """Delete DB entries whose backing files are gone. Returns sessions removed.

    A session row is removed only when its main transcript
    (<session_id>.jsonl) is missing; orphaned subagent file rows are cleaned
    up without touching their parent session.
    """
    removed = 0
    for row in store.list_files():
        path = row["path"]
        if os.path.exists(path):
            continue
        store.delete_file(path)
        if path.endswith(f"{row['session_id']}.jsonl"):
            store.delete_session(row["session_id"])
            removed += 1
    return removed
