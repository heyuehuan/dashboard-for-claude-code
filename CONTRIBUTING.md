# Contributing

Bug reports, docs fixes, and code changes are all welcome.

## Getting started

```bash
uv sync --all-groups                     # runtime + dev tools (pytest, ruff) + security (bandit)
uv run python -m claude_dashboard        # http://localhost:8042
uv run --group dev pytest -v             # run the tests
```

> A plain `uv sync` installs runtime dependencies only (so end users who just want
> to run the dashboard stay lean). Contributors need `--all-groups` to get the test,
> lint, and security tooling.

## Guidelines

- **Stay local-first and read-only.** This tool must never modify a user's logs
  or send data off their machine by default. Do not submit PRs that break this
  rule without making it strictly opt-in.
- **No personal or sensitive data in commits.** Don't commit anything from
  `data/`, `logs/`, `remote_public/`, or a real `scripts/deploy.env` — these are
  gitignored. Use the synthetic fixtures in `tests/fixtures/` for tests.
- **Match the surrounding style.** The code favors small, dependency-light,
  readable modules. The UI is intentionally vanilla JS + Chart.js — no build step.
- **Add tests** for parsing and pricing changes; those are the parts most likely
  to regress.

## Pull requests

1. Fork and create a feature branch.
2. Make your change, add/adjust tests, and run `uv run --group dev pytest`.
3. Open a PR describing the change and the motivation.

## Reporting bugs

Open an issue with steps to reproduce. If it involves parsing, a **redacted**
snippet of the relevant JSONL (with paths and prompt text removed) is very helpful.

By contributing, you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
