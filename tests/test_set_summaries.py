"""Tests for scripts/set_summaries.py — the merge tool that writes the canonical
data/session_summary.json the dashboard reads.

The script is import-side-effect-free (all work happens in main()), so tests
load it as a module, point DASHBOARD_SUMMARY_FILE at a tmp file, and drive main()
with stdin/argv.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _load_with_summary_file(monkeypatch, summary_path: Path):
    monkeypatch.setenv("DASHBOARD_SUMMARY_FILE", str(summary_path))
    spec = importlib.util.spec_from_file_location(
        "set_summaries_script", _SCRIPTS / "set_summaries.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # reads DASHBOARD_SUMMARY_FILE at import time
    return mod


def _run(mod, monkeypatch, incoming, capsys):
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(incoming)))
    monkeypatch.setattr("sys.argv", ["set_summaries.py"])  # no file arg → stdin
    mod.main()
    capsys.readouterr()  # swallow the "Merged N …" line


class _Stdin:
    def __init__(self, text):
        self._text = text

    def read(self):
        return self._text


def test_prefixes_and_writes(tmp_path, monkeypatch, capsys):
    summary_file = tmp_path / "session_summary.json"
    mod = _load_with_summary_file(monkeypatch, summary_file)
    _run(mod, monkeypatch, {"abc": "Refactored auth."}, capsys)

    data = json.loads(summary_file.read_text())
    assert data == {"abc": "[Claude Summary] Refactored auth."}


def test_does_not_double_prefix(tmp_path, monkeypatch, capsys):
    summary_file = tmp_path / "session_summary.json"
    mod = _load_with_summary_file(monkeypatch, summary_file)
    _run(mod, monkeypatch, {"abc": "[Claude Summary] Already tagged."}, capsys)

    data = json.loads(summary_file.read_text())
    assert data["abc"] == "[Claude Summary] Already tagged."


def test_merges_into_existing_and_skips_blank_or_nonstring(tmp_path, monkeypatch, capsys):
    summary_file = tmp_path / "session_summary.json"
    summary_file.write_text(json.dumps({"old": "[Claude Summary] Kept."}))
    mod = _load_with_summary_file(monkeypatch, summary_file)
    _run(mod, monkeypatch, {"new": "Added.", "blank": "   ", "bad": 123}, capsys)

    data = json.loads(summary_file.read_text())
    assert data["old"] == "[Claude Summary] Kept."          # existing preserved
    assert data["new"] == "[Claude Summary] Added."         # new merged
    assert "blank" not in data and "bad" not in data        # invalid dropped


def test_write_is_atomic_no_tmp_left_behind(tmp_path, monkeypatch, capsys):
    summary_file = tmp_path / "session_summary.json"
    mod = _load_with_summary_file(monkeypatch, summary_file)
    _run(mod, monkeypatch, {"abc": "x"}, capsys)

    # The .tmp file is renamed into place, never left around.
    assert not (tmp_path / "session_summary.json.tmp").exists()
    assert summary_file.exists()
