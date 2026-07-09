# Security Policy

## Local by Design

Dashboard for Claude Code is **local-first and read-only** by design:

- It only ever **reads** files under `~/.claude/projects/`; it never writes to them.
- It runs entirely on your machine. No telemetry, no external network calls.
- The optional static export (`scripts/export.py`) strips raw prompt text and can
  redact home-directory paths before anything is written to `remote_public/`.

If you expose the dashboard beyond your own machine (LAN or remote hosting), review
[`scripts/SECURITY.md`](scripts/SECURITY.md) for hardening options: binding to
localhost, token auth, Cloudflare Access, and origin IP allowlisting.

## Reporting a vulnerability

If you discover a security issue, please **do not post vulnerability details in
a public issue**. Instead, use GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository (Security → Report a vulnerability). If that doesn't work
for you, open a GitHub issue that says only "security issue — please reach out"
(no details) and a maintainer will follow up with a private channel.

Please include steps to reproduce and the potential impact. We'll acknowledge the
report and work with you on a fix and coordinated disclosure.
