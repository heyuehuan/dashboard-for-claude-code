"""Tests for scripts/session_digest.py — extracts a compact digest (first prompt,
last assistant reply, compact summary) from a transcript for the summarization
workflow. The parsing helpers carry the logic, so they get direct coverage.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def digest():
    spec = importlib.util.spec_from_file_location("session_digest_script", _SCRIPTS / "session_digest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_clip_collapses_whitespace_and_truncates(digest):
    assert digest._clip("a   b\n c", 100) == "a b c"
    assert digest._clip("x" * 50, 10) == "x" * 10 + "…"
    assert digest._clip(None, 10) == ""


def test_text_of_handles_string_and_blocks(digest):
    assert digest._text_of("hello") == "hello"
    blocks = [{"type": "text", "text": "one"}, {"type": "tool_use"}, {"type": "text", "text": "two"}]
    assert digest._text_of(blocks) == "one\ntwo"
    assert digest._text_of([{"type": "tool_use"}]) is None  # no text blocks


def test_is_noise_flags_harness_wrappers(digest):
    assert digest._is_noise("<command-name>foo</command-name>")
    assert digest._is_noise("  <system-reminder>x")
    assert digest._is_noise("Caveat: local command")
    assert not digest._is_noise("Fix the bug in main.py")


def test_extract_pulls_first_prompt_and_last_assistant(digest, tmp_path):
    p = tmp_path / "t.jsonl"
    lines = [
        {"type": "user", "promptId": "p1",
         "message": {"role": "user", "content": "<command-name>clear</command-name>"}},  # noise
        {"type": "user", "promptId": "p2",
         "message": {"role": "user", "content": "Fix the login bug"}},                   # real prompt
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "Looking into it."}]}},
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "Fixed and tested."}]}},        # last
        "{ corrupt line",                                                                 # skipped
    ]
    p.write_text("\n".join(json.dumps(o) if isinstance(o, dict) else o for o in lines))
    ext = digest.extract(str(p))
    assert ext["first_prompt"] == "Fix the login bug"
    assert ext["last_assistant"] == "Fixed and tested."
    assert ext["compact"] is None


def test_extract_prefers_compact_summary(digest, tmp_path):
    p = tmp_path / "t.jsonl"
    lines = [
        {"type": "user", "isCompactSummary": True,
         "message": {"content": "Session so far: refactored the parser."}},
    ]
    p.write_text("\n".join(json.dumps(o) for o in lines))
    ext = digest.extract(str(p))
    assert ext["compact"] == "Session so far: refactored the parser."
