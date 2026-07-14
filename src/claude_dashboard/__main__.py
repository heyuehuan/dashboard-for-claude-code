import argparse
import os
from importlib.metadata import PackageNotFoundError, version

import uvicorn


def _dist_version() -> str:
    try:
        return version("dashboard-for-claude-code")
    except PackageNotFoundError:
        return "unknown (running from source without install)"


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        prog="dashboard-for-claude-code",
        description="Claude Code Personal Analytics — a private, local, read-only analytics dashboard for your Claude Code sessions.",
    )
    parser.add_argument(
        "--host",
        help="interface to bind; overrides DASHBOARD_HOST (default: 127.0.0.1, "
             "localhost-only — use 0.0.0.0 to expose on your LAN)",
    )
    parser.add_argument(
        "--port", type=int,
        help="port to serve on; overrides DASHBOARD_PORT (default: 8042)",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {_dist_version()}",
    )
    args = parser.parse_args(argv)

    host = args.host or os.environ.get("DASHBOARD_HOST", "127.0.0.1")
    if args.port is not None:
        port = args.port
    else:
        try:
            port = int(os.environ.get("DASHBOARD_PORT", "8042"))
        except ValueError:
            print("ERROR: DASHBOARD_PORT must be an integer", flush=True)
            raise SystemExit(1)

    if args.host:
        # app.py derives its Host-header guard (and cookie secure flag) from
        # DASHBOARD_HOST at import time, so the override must land in the
        # environment before the app module is imported below.
        os.environ["DASHBOARD_HOST"] = args.host

    from claude_dashboard.app import app
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
