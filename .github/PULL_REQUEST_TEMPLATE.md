## What & why

<!-- Summary of the change and the motivation. Link related issues. -->

## Checklist

- [ ] `uv run --group dev pytest` passes
- [ ] `uv run --group dev ruff check .` passes
- [ ] Stays local-first and read-only (no writes to `~/.claude`, no network
      calls that aren't strictly opt-in)
- [ ] No personal data in the diff (paths, prompts, real project names)
- [ ] Tests added/adjusted for parsing, pricing, or export changes
