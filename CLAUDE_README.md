# Claude Instructions — Dashboard for Claude Code

This file is written for Claude (AI assistant / Claude Code agent). Follow the steps below when a user asks you to set up, run, or configure this project. Do not skip steps or assume they have already been completed unless the user confirms.

---

## Step 1 — Install dependencies

```bash
uv sync
```

Confirm it exits without errors before proceeding.

---

## Step 2 — Start the dashboard locally

```bash
uv run python -m claude_dashboard
```

The server starts at **http://localhost:8042**. On first run, all sessions are parsed in the background — the UI appears immediately and fills in as scanning completes. Tell the user to open that URL and confirm they can see the dashboard before continuing.

---

## Step 3 — Ask the user about session summaries

Once the dashboard is confirmed running, ask the user:

> "The dashboard can show a one- or two-sentence summary on each session card. Would you like me to generate summaries for sessions that don't have one yet?"

**Before they agree, state the following clearly:**

- Generating summaries **uses your Claude Code agent tokens** — the same budget as any other Claude Code session.
- Each batch reads session content (first prompt, last assistant response, tools used) and writes a short summary. This is done locally; no data leaves your machine.
- If you have many unsummarized sessions this may take several rounds and could be **slow or cost more tokens than expected**. You can run it in batches and stop at any time.
- Summaries are stored in `data/session_summary.json` and picked up on the next dashboard refresh — no server restart needed.

If the user says no, stop here. If they say yes, continue to Step 4.

---

## Step 4 — Generate and apply session summaries

### 4a. Check how many sessions need summaries

```bash
python scripts/session_digest.py 1 --offset 0
```

This prints the total count of sessions missing a summary. Show it to the user so they can decide how many to process at once. A reasonable batch size is 8 (the default).

### 4b. Read the digests

Run the digest script to see the batch:

```bash
python scripts/session_digest.py [N] [--offset M]
```

- `N` — number of sessions to summarize in this batch (default 8; use a smaller number like 3–5 if the sessions are long or you want to keep token use low)
- `--offset M` — skip the first M sessions (use to process later batches)

Read the printed output carefully. Each block contains:
- `SESSION_ID` — the ID you must key the summary to
- `FIRST_PROMPT` / `COMPACT_SUMMARY` / `LAST_ASSISTANT` — context for writing the summary
- Project name, branch, cost, tools used, duration

### 4c. Write the summaries

For each session in the digest, write a **one- or two-sentence summary** that describes what the session accomplished. Be specific and factual — avoid generic phrases. Examples of good summaries:

- "Refactored auth middleware to fix session token storage; added integration tests."
- "Debugged a race condition in the job queue; traced to missing lock around queue.pop()."
- "Added CSV export to the billing report page and wired it to the existing API endpoint."

Produce a JSON object:

```json
{
  "SESSION_ID_1": "Summary text here.",
  "SESSION_ID_2": "Summary text here."
}
```

### 4d. Apply the summaries

Pipe the JSON to `set_summaries.py`:

```bash
echo '{"SESSION_ID_1": "...", "SESSION_ID_2": "..."}' | python scripts/set_summaries.py
```

Or write it to a temp file and pass it:

```bash
python scripts/set_summaries.py /tmp/summaries.json
```

The script prefixes each entry with `[Claude Summary]` (unless already present) and merges it into `data/session_summary.json`. It prints a confirmation line showing how many were merged.

### 4e. Refresh the dashboard

Tell the user to click **Refresh** in the dashboard header, or trigger it via the API:

```bash
curl -s -X POST http://localhost:8042/api/refresh
```

Summaries will now appear on the relevant session cards.

### 4f. Repeat for more batches (if needed)

The digest lists only sessions that are still **missing** a summary, so once a
batch is applied those sessions drop out of the list. To process the next
batch, run the same command again **without changing the offset**:

```bash
python scripts/session_digest.py 8    # next batch — offset stays 0
```

Do **not** increment `--offset` between applied batches — that would skip
sessions that still need summaries. Use `--offset` only to peek ahead at later
sessions without summarizing the earlier ones.

Ask the user after each batch whether to continue.

---

## Notes

- You can stop summarizing at any time — summaries already written are saved.
- If `data/session_summary.json` does not exist yet, `set_summaries.py` creates it.
- To override the summary file location: `DASHBOARD_SUMMARY_FILE=/path/to/file python scripts/set_summaries.py ...`
- The dashboard never modifies `~/.claude/projects/` — all writes go to `data/`.
