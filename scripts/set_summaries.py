#!/usr/bin/env python3
"""Merge a batch of session summaries into data/session_summary.json.

Reads a JSON object {session_id: summary_text} from a file argument or stdin,
prefixes each value with "[Claude Summary] " (unless already present), merges it
into the canonical summary file, and writes the file back atomically.

The dashboard treats data/session_summary.json as the source of truth and
ingests it on its next refresh (server startup or POST /api/refresh) — no running
server is required to add summaries. Override the location with
DASHBOARD_SUMMARY_FILE if your DB lives elsewhere.

Input can come from any source: a script, a manual JSON file, or an AI tool.
"""
import json
import os
import sys
from pathlib import Path

PREFIX = "[Claude Summary] "
ROOT = Path(__file__).resolve().parent.parent

# The dashboard reads summaries from session_summary.json *next to the DB*
# (see Store.summary_file), so when DASHBOARD_DB is set, follow it — otherwise
# the two silently disagree. DASHBOARD_SUMMARY_FILE still overrides everything.
_db = os.environ.get("DASHBOARD_DB")
_default_summary = (
    Path(_db).parent / "session_summary.json"
    if _db
    else ROOT / "data" / "session_summary.json"
)
SUMMARY_FILE = Path(os.environ.get("DASHBOARD_SUMMARY_FILE", _default_summary))


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text().strip()
    return json.loads(text) if text else {}


def main():
    raw = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    incoming = json.loads(raw)

    summaries = _load(SUMMARY_FILE)
    n = 0
    for sid, text in incoming.items():
        if not isinstance(text, str):
            continue
        text = text.strip()
        if not text:
            continue
        if not text.startswith("[Claude Summary]"):
            text = PREFIX + text
        summaries[sid] = text
        n += 1

    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = SUMMARY_FILE.with_name(SUMMARY_FILE.name + ".tmp")
    tmp.write_text(json.dumps(summaries, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(SUMMARY_FILE)
    print(f"Merged {n} summaries → {SUMMARY_FILE} ({len(summaries)} total)")


if __name__ == "__main__":
    main()
