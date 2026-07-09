"""Scanner tests against a fake ~/.claude/projects tree in tmp_path.

Covers the incremental-scan contract (add → skip → update), resilience to
files vanishing mid-scan, and the opt-in prune of sessions whose transcript
is gone from disk.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from claude_dashboard import scanner
from claude_dashboard.store import Store

_FIXTURE = Path(__file__).parent / "fixtures" / "tiny_session.jsonl"


@pytest.fixture
def projects_dir(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(scanner, "_CLAUDE_PROJECTS", root)
    return root


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "usage.db")
    yield s
    s.close()


def _add_session(projects_dir: Path, project: str = "-Users-test-myproject",
                 name: str = "test-session-001.jsonl") -> Path:
    proj = projects_dir / project
    proj.mkdir(exist_ok=True)
    dest = proj / name
    shutil.copy(_FIXTURE, dest)
    return dest


def test_refresh_adds_then_skips(projects_dir, store):
    _add_session(projects_dir)

    report = scanner.refresh(store)
    assert report.added == 1
    assert report.errors == []
    assert store.get_session("test-session-001")["cwd"] == "/Users/test/myproject"

    # Unchanged file → skipped on the next scan.
    report = scanner.refresh(store)
    assert (report.added, report.updated, report.skipped) == (0, 0, 1)


def test_refresh_updates_changed_file(projects_dir, store):
    path = _add_session(projects_dir)
    scanner.refresh(store)

    with open(path, "a") as fh:
        fh.write("\n")
    report = scanner.refresh(store)
    assert report.updated == 1


def test_file_vanishing_mid_scan_does_not_kill_refresh(projects_dir, store, monkeypatch):
    _add_session(projects_dir)

    # Simulate the transcript disappearing between iterdir() and parsing
    # (e.g. Claude Code's own cleanup running concurrently).
    def _gone(path):
        raise FileNotFoundError(path)

    monkeypatch.setattr(scanner, "parse_file", _gone)
    report = scanner.refresh(store)  # must not raise
    assert report.added == 0
    assert report.errors == []  # a vanished file is not an error


def test_prune_removes_sessions_with_deleted_transcripts(projects_dir, store):
    path = _add_session(projects_dir)
    scanner.refresh(store)
    assert store.get_session("test-session-001")

    path.unlink()

    # Default: deleted transcripts stay in the cache (history survives cleanup).
    report = scanner.refresh(store)
    assert report.pruned == 0
    assert store.get_session("test-session-001")

    # Opt-in prune drops the session and its file-tracking row.
    report = scanner.refresh(store, prune=True)
    assert report.pruned == 1
    assert store.get_session("test-session-001") is None
    assert store.get_file(str(path)) is None
