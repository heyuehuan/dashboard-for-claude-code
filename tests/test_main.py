"""Tests for the CLI entrypoint (claude_dashboard.__main__).

uvicorn.run is stubbed so nothing actually binds a port; we only verify
host/port resolution (flags > env > defaults), --version/--help exits, and the
failure path for a bad DASHBOARD_PORT.
"""
from __future__ import annotations

import pytest

from claude_dashboard import __main__ as cli


def test_main_uses_env_host_and_port(monkeypatch):
    called = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, host, port: called.update(host=host, port=port))
    monkeypatch.setenv("DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.setenv("DASHBOARD_PORT", "9001")
    cli.main([])
    assert called == {"host": "0.0.0.0", "port": 9001}


def test_main_defaults(monkeypatch):
    called = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, host, port: called.update(host=host, port=port))
    monkeypatch.delenv("DASHBOARD_HOST", raising=False)
    monkeypatch.delenv("DASHBOARD_PORT", raising=False)
    cli.main([])
    assert called == {"host": "127.0.0.1", "port": 8042}


def test_main_rejects_non_integer_port(monkeypatch, capsys):
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: pytest.fail("should not start server"))
    monkeypatch.setenv("DASHBOARD_PORT", "not-a-number")
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 1
    assert "DASHBOARD_PORT must be an integer" in capsys.readouterr().out


def test_main_flags_override_env(monkeypatch):
    called = {}
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, host, port: called.update(host=host, port=port))
    monkeypatch.setenv("DASHBOARD_HOST", "127.0.0.1")
    monkeypatch.setenv("DASHBOARD_PORT", "9001")
    cli.main(["--host", "0.0.0.0", "--port", "9002"])
    assert called == {"host": "0.0.0.0", "port": 9002}


def test_main_host_flag_syncs_env_for_app_import(monkeypatch):
    # app.py reads DASHBOARD_HOST at import time for its Host-header guard;
    # main() must publish the --host override to the environment before then.
    import os
    monkeypatch.setattr(cli.uvicorn, "run", lambda app, host, port: None)
    monkeypatch.setenv("DASHBOARD_HOST", "127.0.0.1")
    cli.main(["--host", "0.0.0.0"])
    assert os.environ["DASHBOARD_HOST"] == "0.0.0.0"


def test_main_version_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: pytest.fail("should not start server"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "dashboard-for-claude-code" in capsys.readouterr().out


def test_main_help_exits_zero(monkeypatch, capsys):
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: pytest.fail("should not start server"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--host" in out and "--port" in out


def test_main_rejects_non_integer_port_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: pytest.fail("should not start server"))
    with pytest.raises(SystemExit) as exc:
        cli.main(["--port", "not-a-number"])
    assert exc.value.code == 2  # argparse usage error
