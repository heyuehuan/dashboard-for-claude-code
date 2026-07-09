import json
from pathlib import Path
from claude_dashboard.parser import parse_file

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_session.jsonl"


def test_wall_duration_without_fractional_seconds(tmp_path):
    # Timestamps without a ".fff" fraction must still yield a wall duration.
    p = tmp_path / "s.jsonl"
    lines = [
        {"type": "user", "promptId": "p1", "sessionId": "s",
         "message": {"role": "user", "content": "hi"},
         "timestamp": "2026-05-10T10:00:00Z"},
        {"type": "assistant", "sessionId": "s",
         "message": {"model": "claude-sonnet-4-6", "role": "assistant",
                     "usage": {"input_tokens": 1, "output_tokens": 1}, "content": []},
         "timestamp": "2026-05-10T10:00:30Z"},
    ]
    p.write_text("\n".join(json.dumps(o) for o in lines))
    s = parse_file(p)
    assert s["wall_duration_ms"] == 30000


def test_malformed_lines_are_skipped_not_fatal(tmp_path):
    # Real transcripts can contain a half-written or corrupt line (e.g. the
    # session is mid-write). The parser must skip bad lines and still tally the
    # good ones rather than crashing or zeroing everything out.
    p = tmp_path / "s.jsonl"
    good_user = {"type": "user", "promptId": "p1", "sessionId": "s",
                 "message": {"role": "user", "content": "hi"},
                 "timestamp": "2026-05-10T10:00:00.000Z"}
    good_asst = {"type": "assistant", "sessionId": "s",
                 "message": {"model": "claude-sonnet-4-6", "role": "assistant",
                             "usage": {"input_tokens": 7, "output_tokens": 3},
                             "content": [{"type": "tool_use", "id": "t1", "name": "Bash"}]},
                 "timestamp": "2026-05-10T10:00:05.000Z"}
    lines = [
        json.dumps(good_user),
        "{ this is not valid json",     # truncated / corrupt
        "",                              # blank line
        "not even close to json",       # garbage
        json.dumps(good_asst),
    ]
    p.write_text("\n".join(lines))
    s = parse_file(p)
    assert s["user_rounds"] == 1
    assert s["assistant_messages"] == 1
    assert s["tools"].get("Bash") == 1
    assert s["tokens_by_model"]["claude-sonnet-4-6"]["input"] == 7


def test_tool_use_deduped_across_streaming_duplicates(tmp_path):
    # Same requestId emitted twice (streaming) — tokens and tool_use counts must
    # reflect the last entry only, not be doubled.
    p = tmp_path / "s.jsonl"
    dup = {
        "type": "assistant", "sessionId": "s", "requestId": "req-xyz",
        "message": {"model": "claude-sonnet-4-6", "role": "assistant",
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "content": [{"type": "tool_use", "id": "t1", "name": "Edit"}]},
        "timestamp": "2026-05-10T10:00:00.000Z",
    }
    p.write_text("\n".join(json.dumps(dup) for _ in range(3)))
    s = parse_file(p)
    assert s["tools"].get("Edit") == 1
    assert s["assistant_messages"] == 1
    assert s["tokens_by_model"]["claude-sonnet-4-6"]["input"] == 10
    assert s["tokens_by_model"]["claude-sonnet-4-6"]["output"] == 5


def test_session_id():
    s = parse_file(FIXTURE)
    assert s["session_id"] == "test-session-001"


def test_cwd_and_version():
    s = parse_file(FIXTURE)
    assert s["cwd"] == "/Users/test/myproject"
    assert s["version"] == "2.1.0"


def test_user_rounds():
    # Only the first user message has promptId + string content → 1 round
    s = parse_file(FIXTURE)
    assert s["user_rounds"] == 1


def test_assistant_messages():
    # Two real assistant messages (non-synthetic, non-error)
    s = parse_file(FIXTURE)
    assert s["assistant_messages"] == 2


def test_api_duration():
    # Two turn_duration events: 5000 + 3000 = 8000 ms
    s = parse_file(FIXTURE)
    assert s["api_duration_ms"] == 8000


def test_tokens():
    s = parse_file(FIXTURE)
    tok = s["tokens_by_model"]["claude-sonnet-4-6"]
    # input: 120+50=170, output: 80+30=110
    assert tok["input"] == 170
    assert tok["output"] == 110
    # cache_read: 500+0=500
    assert tok["cache_read"] == 500
    # cache_write_5m: 0+200=200
    assert tok["cache_write_5m"] == 200
    assert tok["cache_write_1h"] == 0


def test_code_lines():
    s = parse_file(FIXTURE)
    # Counted from the tool result's structuredPatch: 2 removed (-), 3 added (+)
    assert s["code_lines_removed"] == 2
    assert s["code_lines_added"] == 3


def test_session_signals():
    s = parse_file(FIXTURE)
    assert s["git_branch"] == "feature/fix-bug"
    assert s["last_user_prompt"] == "Fix the bug in main.py"
    # permission modes seen: one 'default' line + one 'acceptEdits' on the user line
    assert s["permission_modes"] == {"default": 1, "acceptEdits": 1}


def test_tools():
    s = parse_file(FIXTURE)
    assert s["tools"].get("Edit") == 1


def test_timestamps():
    s = parse_file(FIXTURE)
    assert s["started_at"] == "2026-05-10T10:00:00.000Z"
    assert s["ended_at"] == "2026-05-10T10:00:10.002Z"
    assert s["wall_duration_ms"] is not None
    assert s["wall_duration_ms"] > 0
