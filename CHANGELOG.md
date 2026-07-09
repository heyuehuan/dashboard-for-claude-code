# Changelog

## [0.1.0] — 2026-07-08

### Added
- Initial release.
- CLI flags on the entrypoint: `--help`, `--version`, and `--host`/`--port`
  (which take precedence over `DASHBOARD_HOST`/`DASHBOARD_PORT`). Previously
  any argument was silently ignored and the server just started.
- Read-only local dashboard for browsing Claude Code usage: projects, sessions,
  cost/token breakdowns, tool-use stats, and per-session timelines.
- SQLite-backed scan cache (`data/usage.db`); rescans on startup and on-demand
  via `POST /api/refresh`.
- Optional token auth (`DASHBOARD_AUTH_TOKEN`) with `HttpOnly`+`SameSite=strict`
  cookie and constant-time comparison.
- Binds to `127.0.0.1` by default; set `DASHBOARD_HOST=0.0.0.0` to expose on the LAN.
- DNS-rebinding protection: Host-header allowlist when bound to loopback.
- Cookie `secure` flag enabled automatically for non-localhost deployments.
- CI on Python 3.11–3.13, plus ruff lint and lockfile checks.
- Security scanning in CI: gitleaks (secret scanning), bandit (Python SAST),
  and CodeQL. Dev/security tooling lives in opt-in dependency groups, so a plain
  `uv sync` installs runtime dependencies only.
- Demo data generator (`scripts/demo_data.py`) for screenshots and UI exploration.
- Optional prune on refresh (`POST /api/refresh?prune=true`) to drop sessions
  whose transcript was deleted from disk; by default history is kept.
- Community files: code of conduct, issue/PR templates, dependabot config.

### Fixed
- Static export now redacts home-directory paths in dict keys too —
  `settings.json` previously leaked absolute paths even with
  `DASHBOARD_REDACT_HOME=1` (this also fixes settings lookups in remote mode).
- A transcript deleted mid-scan no longer aborts the background refresh.
- Default DB path for installed (pipx/uvx) packages now uses a per-user data
  dir instead of a directory inside the virtualenv.
- Host-header guard now parses bracketed IPv6 hosts correctly and rejects
  empty `Host` headers.
- SQLite cache uses WAL mode and a busy timeout for safer concurrent
  reads during background scans.
- Future Opus model ids no longer silently match legacy (3×) pricing; unmatched
  models are surfaced as unknown instead.
- `scripts/set_summaries.py` and `scripts/session_digest.py` follow
  `DASHBOARD_DB` so summaries land next to the database actually in use.
- Hidden projects remain reachable via a direct detail link.
