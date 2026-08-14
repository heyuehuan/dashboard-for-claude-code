# Changelog

## [0.1.1] — 2026-08-14

### Fixed
- Opus 5 had no rate row, so its sessions priced at $0 and surfaced under
  unknown models. Model display names now derive from the id instead of a
  12-character slice, so `claude-opus-5` renders as "Opus 5" rather than
  "claude-opus-" — and the next model degrades to a name, not a truncation.
- 1h cache writes bill at 2× input, not the 5m rate (1.25×). Every model row
  was understating cost on sessions with 1h cache creation. Stored costs are
  computed at parse time and the mtime/size cache would have served the old
  numbers forever, so the scanner now fingerprints the rate table and
  re-prices every session once after a rate edit.
- The browser-side rate table in `static/app.js` (used for client-side pricing
  in remote mode) had drifted from `pricing.py`: it was missing the mythos-5
  row and used a bare `opus-4` key, which would price future Opus models at the
  legacy 3× rate. A test now fails if the two tables disagree.
- CI pinned `astral-sh/setup-uv@v7`, a tag that can never advance: setup-uv
  stopped publishing floating major tags after v7, so Dependabot resolved the
  latest ref as 7 and silently never proposed an upgrade. All workflows now pin
  the action by commit SHA (v10.0.1), which Dependabot can track.

### Changed
- `estimate_cost` returns per-model costs under a `by_model` key instead of
  mixing them into the top-level dict alongside `total` and `unknown_models`.

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
