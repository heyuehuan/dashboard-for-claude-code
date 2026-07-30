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


def test_rate_change_reprices_unchanged_sessions(projects_dir, store, monkeypatch):
    """An edit to the pricing table must re-price sessions already in the DB. The
    mtime/size cache would otherwise skip them and keep serving the old cost_usd."""
    _add_session(projects_dir)
    scanner.refresh(store)
    before = store.get_session("test-session-001")["cost_usd"]

    # Same file on disk, but the rate table now fingerprints differently.
    monkeypatch.setattr(scanner, "rate_revision", lambda: "deadbeefdeadbeef")
    monkeypatch.setattr(
        scanner, "estimate_cost", lambda tokens: {"by_model": {}, "total": 99.0, "unknown_models": []}
    )

    report = scanner.refresh(store)
    assert (report.updated, report.skipped) == (1, 0)
    assert store.get_session("test-session-001")["cost_usd"] == 99.0
    assert before != 99.0

    # The revision is recorded, so the next scan goes back to skipping.
    report = scanner.refresh(store)
    assert (report.updated, report.skipped) == (0, 1)


def test_rate_revision_not_recorded_when_scan_errors(projects_dir, store, monkeypatch):
    """A scan that hit an error left some sessions on their old cost, so the revision
    must stay unrecorded and the re-price must be retried on the next refresh."""
    _add_session(projects_dir)
    scanner.refresh(store)

    monkeypatch.setattr(scanner, "rate_revision", lambda: "deadbeefdeadbeef")
    _add_session(projects_dir, name="test-session-002.jsonl")

    real_parse = scanner.parse_file

    def parse_file(path):
        if Path(path).name == "test-session-002.jsonl":
            raise ValueError("unreadable")
        return real_parse(path)

    monkeypatch.setattr(scanner, "parse_file", parse_file)

    report = scanner.refresh(store)
    assert report.errors  # the bad transcript was reported, not fatal
    monkeypatch.setattr(scanner, "parse_file", real_parse)

    # Revision unrecorded → everything is re-parsed again rather than skipped.
    report = scanner.refresh(store)
    assert report.skipped == 0
