import re
from pathlib import Path

from claude_dashboard.pricing import estimate_cost, rate_table


def test_sonnet_basic():
    tokens = {
        "claude-sonnet-4-6": {
            "input": 1_000_000,
            "output": 1_000_000,
            "cache_read": 0,
            "cache_write_5m": 0,
            "cache_write_1h": 0,
        }
    }
    result = estimate_cost(tokens)
    # $3 input + $15 output = $18
    assert abs(result["by_model"]["claude-sonnet-4-6"] - 18.0) < 0.001
    assert abs(result["total"] - 18.0) < 0.001


def test_opus_cache():
    tokens = {
        "claude-opus-4-7": {
            "input": 0,
            "output": 0,
            "cache_read": 1_000_000,       # $0.50
            "cache_write_5m": 1_000_000,   # $6.25
            "cache_write_1h": 1_000_000,   # $10.00 (2x input)
        }
    }
    result = estimate_cost(tokens)
    expected = 0.50 + 6.25 + 10.00
    assert abs(result["by_model"]["claude-opus-4-7"] - expected) < 0.001


def test_opus_5():
    tokens = {
        "claude-opus-5": {
            "input": 1_000_000,   # $5.00
            "output": 1_000_000,  # $25.00
            "cache_read": 1_000_000,      # $0.50
            "cache_write_5m": 1_000_000,  # $6.25
            "cache_write_1h": 1_000_000,  # $10.00 (2x input)
        }
    }
    result = estimate_cost(tokens)
    assert abs(result["by_model"]["claude-opus-5"] - 46.75) < 0.001
    assert result["unknown_models"] == []


def test_haiku():
    tokens = {
        "claude-haiku-4-5": {
            "input": 2_000_000,   # $2.00
            "output": 1_000_000,  # $5.00
            "cache_read": 0,
            "cache_write_5m": 0,
            "cache_write_1h": 0,
        }
    }
    result = estimate_cost(tokens)
    assert abs(result["total"] - 7.0) < 0.001


def test_unknown_model_zero_cost():
    tokens = {
        "some-unknown-model-v99": {
            "input": 999_999,
            "output": 999_999,
            "cache_read": 0,
            "cache_write_5m": 0,
            "cache_write_1h": 0,
        }
    }
    result = estimate_cost(tokens)
    assert result["total"] == 0.0
    assert "some-unknown-model-v99" in result["unknown_models"]


def test_synthetic_ignored():
    tokens = {
        "<synthetic>": {"input": 100, "output": 100, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0},
        "claude-haiku-4-5": {"input": 1_000_000, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0},
    }
    result = estimate_cost(tokens)
    # Only haiku contributes: $1
    assert abs(result["total"] - 1.0) < 0.001
    assert "<synthetic>" not in result.get("unknown_models", [])


def test_opus_generation_pricing_boundaries():
    """Ordering/fallback intent: 4.5+ get new pricing, 4.1 and the original
    Opus 4 (dated id) get legacy pricing, and *future* opus versions must NOT
    silently fall through to the legacy rate — they surface as unknown."""
    mtok = {"output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0}
    tokens = {
        "claude-opus-4-8":          {"input": 1_000_000, **mtok},  # new: $5
        "claude-opus-4-1-20250805": {"input": 1_000_000, **mtok},  # legacy: $15
        "claude-opus-4-20250514":   {"input": 1_000_000, **mtok},  # legacy: $15
        "claude-opus-4-9":          {"input": 1_000_000, **mtok},  # future: unknown
    }
    result = estimate_cost(tokens)
    assert abs(result["by_model"]["claude-opus-4-8"] - 5.0) < 0.001
    assert abs(result["by_model"]["claude-opus-4-1-20250805"] - 15.0) < 0.001
    assert abs(result["by_model"]["claude-opus-4-20250514"] - 15.0) < 0.001
    assert result["by_model"]["claude-opus-4-9"] == 0.0
    assert result["unknown_models"] == ["claude-opus-4-9"]


def test_multi_model_total():
    tokens = {
        "claude-sonnet-4-6": {"input": 1_000_000, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0},
        "claude-haiku-4-5":  {"input": 1_000_000, "output": 0, "cache_read": 0, "cache_write_5m": 0, "cache_write_1h": 0},
    }
    result = estimate_cost(tokens)
    # $3 + $1 = $4
    assert abs(result["total"] - 4.0) < 0.001


def test_rates_derive_from_input_price():
    """cache_read = 0.1x input, cache_write_5m = 1.25x, cache_write_1h = 2x.
    Guards against a hand-edited row drifting out of that relationship."""
    for key, r in rate_table():
        assert abs(r.cache_read - r.input * 0.1) < 1e-9, key
        assert abs(r.cache_write_5m - r.input * 1.25) < 1e-9, key
        assert abs(r.cache_write_1h - r.input * 2.0) < 1e-9, key


def test_js_rate_table_matches_python():
    """static/app.js carries its own copy of the rate table so the browser can price
    client-side in remote mode. It must stay identical to _RATES, in the same order —
    the substring matching is order-dependent ("opus-4-1" must precede "opus-4-2025")."""
    app_js = Path(__file__).resolve().parents[1] / "src" / "claude_dashboard" / "static" / "app.js"
    block = app_js.read_text()
    block = block[block.index("const MODEL_RATES = ["):]
    block = block[: block.index("\n];") + 3]

    js_rates = [
        (m.group(1), *(float(g) for g in m.groups()[1:]))
        for m in re.finditer(
            r'"([^"]+)",\s*\{\s*input:\s*([\d.]+),\s*output:\s*([\d.]+),\s*'
            r"cache_read:\s*([\d.]+),\s*cache_write_5m:\s*([\d.]+),\s*cache_write_1h:\s*([\d.]+),",
            block,
        )
    ]
    py_rates = [
        (key, r.input, r.output, r.cache_read, r.cache_write_5m, r.cache_write_1h)
        for key, r in rate_table()
    ]
    assert js_rates == py_rates
