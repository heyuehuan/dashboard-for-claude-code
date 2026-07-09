"""Tests for scripts/demo_data.py — the synthetic-data generator used for
screenshots and trying the UI. Its guarantees matter for the public repo:
the data must stay deterministic and must never contain a real user's paths.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from claude_dashboard.store import Store

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture
def demo():
    spec = importlib.util.spec_from_file_location("demo_data_script", _SCRIPTS / "demo_data.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_build_is_deterministic(demo, tmp_path):
    # Same seed → byte-for-byte identical aggregates, so screenshots are stable.
    a = Store(tmp_path / "a.db")
    b = Store(tmp_path / "b.db")
    demo.build(a, seed=7, n_sessions=20)
    demo.build(b, seed=7, n_sessions=20)
    assert a.summary() == b.summary()
    a.close()
    b.close()


def test_build_session_count_and_synthetic_paths(demo, tmp_path):
    store = Store(tmp_path / "demo.db")
    demo.build(store, seed=7, n_sessions=25)
    sessions = store.list_sessions()
    assert len(sessions) == 25
    # Every path is a fictional /Users/dev/... path — never a real home dir.
    assert all(s["project_path"].startswith("/Users/dev/") for s in sessions)
    store.close()


def test_build_wall_time_exceeds_api_time(demo, tmp_path):
    # The generator documents wall > api always (user think time on top of API).
    store = Store(tmp_path / "demo.db")
    demo.build(store, seed=3, n_sessions=40)
    for s in store.list_sessions():
        assert s["wall_duration_ms"] > s["api_duration_ms"]
    store.close()


def test_build_applies_hidden_and_rename_settings(demo, tmp_path):
    store = Store(tmp_path / "demo.db")
    demo.build(store, seed=7, n_sessions=30)
    settings = store.get_all_project_settings()
    # The throwaway-poc project is seeded hidden; renames carry a "/" tag prefix.
    assert settings["/Users/dev/code/throwaway-poc"]["hidden"] is True
    assert settings["/Users/dev/code/acme-storefront"]["display_name"] == "work/acme-storefront"
    store.close()
