"""Tests for the privacy layer in scripts/export.py.

The static export is the only path where dashboard data can leave the machine,
so its redaction helpers get direct coverage: home-dir redaction (including
dict *keys* — settings.json is keyed by absolute project paths) and raw-prompt
stripping.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def export(monkeypatch):
    spec = importlib.util.spec_from_file_location("export_script", _SCRIPTS / "export.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_REDACT_HOME", True)
    monkeypatch.setattr(mod, "_HOME_STR", "/Users/alice")
    return mod


def test_redact_string_prefix_only(export):
    assert export._redact("/Users/alice/code/app") == "~/code/app"
    # Only a leading home prefix is redacted; mid-string mentions are left alone.
    assert export._redact("see /Users/alice/code") == "see /Users/alice/code"
    assert export._redact("/Users/bob/code") == "/Users/bob/code"


def test_redact_dict_keys_and_values(export):
    # settings.json shape: keyed by absolute project path.
    settings = {"/Users/alice/code/app": {"display_name": "work/app", "hidden": False}}
    out = export._redact(settings)
    assert out == {"~/code/app": {"display_name": "work/app", "hidden": False}}


def test_redact_nested_structures(export):
    obj = {
        "projects": [
            {"project_path": "/Users/alice/code/app", "cost": 1.5},
            {"project_path": "/tmp/other", "cost": 2.0},
        ]
    }
    out = export._redact(obj)
    assert out["projects"][0]["project_path"] == "~/code/app"
    assert out["projects"][1]["project_path"] == "/tmp/other"
    assert out["projects"][0]["cost"] == 1.5


def test_redact_disabled_passthrough(export, monkeypatch):
    monkeypatch.setattr(export, "_REDACT_HOME", False)
    obj = {"/Users/alice/code/app": "/Users/alice/code/app"}
    assert export._redact(obj) == obj


def test_strip_private_drops_raw_prompts(export):
    sessions = [
        {"session_id": "A", "last_user_prompt": "secret prompt", "cost_usd": 1.0},
        {"session_id": "B", "last_user_prompt": None, "summary": "[Claude Summary] ok"},
    ]
    out = export._strip_private(sessions)
    for s in out:
        assert "last_user_prompt" not in s
    # Everything else survives.
    assert out[0]["session_id"] == "A"
    assert out[1]["summary"] == "[Claude Summary] ok"


def test_safe_session_id_pattern(export):
    assert export._SAFE_SID.match("abc-123_XYZ")
    assert not export._SAFE_SID.match("../../etc/passwd")
    assert not export._SAFE_SID.match("a/b")
    assert not export._SAFE_SID.match("")


# ── End-to-end: main() produces the full static bundle, redacted ────────────

def test_main_writes_redacted_static_bundle(export, tmp_path, monkeypatch, capsys):
    home = "/Users/alice"
    monkeypatch.setattr(export, "_HOME_STR", home)
    monkeypatch.setattr(export, "_REDACT_HOME", True)

    pub = tmp_path / "remote_public"
    monkeypatch.setattr(export, "DB_PATH", tmp_path / "usage.db")
    monkeypatch.setattr(export, "PUB", pub)
    monkeypatch.setattr(export, "DATA_OUT", pub / "data")
    monkeypatch.setattr(export, "SRC_OUT", pub / "src")

    # Stand in for the scanner: seed the store main() opens, so no ~/.claude read.
    def fake_refresh(store, **kw):
        store.upsert_session({
            "session_id": "sess-001",
            "project_path": f"{home}/code/myapp",
            "project_name": "myapp",
            "cwd": f"{home}/code/myapp",
            "last_user_prompt": "SHOULD NOT LEAK",
            "started_at": "2026-05-10T09:00:00.000Z",
            "ended_at": "2026-05-10T09:30:00.000Z",
            "cost_usd": 1.0,
        })
        return SimpleNamespace(added=1, updated=0, skipped=0, errors=[])

    monkeypatch.setattr(export, "refresh", fake_refresh)

    export.main()
    capsys.readouterr()

    data = pub / "data"
    for name in ("summary.json", "projects.json", "sessions.json",
                 "settings.json", "meta.json"):
        assert (data / name).exists(), name
    assert (data / "sessions" / "sess-001.json").exists()

    # Home dir is redacted to ~ in exported data; raw prompt never ships.
    projects_txt = (data / "projects.json").read_text()
    assert "~/code/myapp" in projects_txt
    assert home not in projects_txt
    sessions_txt = (data / "sessions.json").read_text()
    assert "SHOULD NOT LEAK" not in sessions_txt

    # index.html carries the remote flag and rewrites /static/ → /src/.
    index = (pub / "index.html").read_text()
    assert "window.DASHBOARD_REMOTE=true" in index
    assert 'src="/src/app.js' in index
    assert "/static/" not in index

    # Static assets copied to src/, but the shell index.html is not duplicated there.
    assert (pub / "src" / "app.js").exists()
    assert not (pub / "src" / "index.html").exists()
