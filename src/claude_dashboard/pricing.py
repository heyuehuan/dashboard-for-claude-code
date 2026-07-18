"""
API pricing per million tokens (MTok), verified 2026-07-08 against
https://platform.claude.com/docs/en/about-claude/pricing.
This is the *equivalent* API cost, not what the user paid (they use a subscription).
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Rate:
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


# Rates ordered from most-specific to least-specific — matched by substring on model id.
# Source: https://platform.claude.com/docs/en/about-claude/pricing (verified 2026-07-08).
# NOTE: Claude Code bills 1h cache writes at the same rate as 5m writes (1.25x input),
# not the API-published 2x rate — so cache_write_1h == cache_write_5m for every model.
# This matches what the CLI / ccusage report; using the 2x rate overestimates cost on
# sessions with many 1h cache-creation tokens.
_RATES: list[tuple[str, Rate]] = [
    # Fable 5 / Mythos 5 (same pricing; Mythos is Project Glasswing-only)
    ("fable-5",   Rate(10.00, 50.00, 1.00, 12.50, 12.50)),
    ("mythos-5",  Rate(10.00, 50.00, 1.00, 12.50, 12.50)),
    # Opus 4.x new pricing
    ("opus-4-8",  Rate(5.00,  25.00, 0.50, 6.25,   6.25)),
    ("opus-4-7",  Rate(5.00,  25.00, 0.50, 6.25,   6.25)),
    ("opus-4-6",  Rate(5.00,  25.00, 0.50, 6.25,   6.25)),
    ("opus-4-5",  Rate(5.00,  25.00, 0.50, 6.25,   6.25)),
    # Opus 4.1 / original Opus 4 legacy pricing. The original Opus 4 id is
    # "claude-opus-4-20250514", so match "opus-4-2025" rather than a bare
    # "opus-4" — a bare prefix would silently price future models (opus-4-9, …)
    # at the legacy 3x rate. Unmatched new models surface in unknown_models
    # instead; add them above when they ship.
    ("opus-4-1",    Rate(15.00, 75.00, 1.50, 18.75, 18.75)),
    ("opus-4-2025", Rate(15.00, 75.00, 1.50, 18.75, 18.75)),
    # Sonnet 5 — standard pricing ($3/$15); introductory $2/$10 runs through 2026-08-31.
    ("sonnet-5",   Rate(3.00, 15.00, 0.30, 3.75,  3.75)),
    # Sonnet 4.x
    ("sonnet-4-6", Rate(3.00, 15.00, 0.30, 3.75,  3.75)),
    ("sonnet-4-5", Rate(3.00, 15.00, 0.30, 3.75,  3.75)),
    ("sonnet-4",   Rate(3.00, 15.00, 0.30, 3.75,  3.75)),
    # Bare "sonnet" alias (session files sometimes record the alias, not a full id)
    ("sonnet",     Rate(3.00, 15.00, 0.30, 3.75,  3.75)),
    # Haiku
    ("haiku-4-5",  Rate(1.00,  5.00, 0.10, 1.25,  1.25)),
    ("haiku-3-5",  Rate(0.80,  4.00, 0.08, 1.00,  1.00)),
]

def _get_rate(model: str) -> Rate | None:
    m = model.lower()
    for key, rate in _RATES:
        if key in m:
            return rate
    return None


def estimate_cost(tokens_by_model: dict[str, dict]) -> dict:
    """
    tokens_by_model: {model_id: {input, output, cache_read,
                                  cache_write_5m, cache_write_1h}}
    Returns {model: usd, ..., "total": usd, "unknown_models": [...]}
    """
    result: dict[str, float] = {}
    unknown: list[str] = []

    for model, tok in tokens_by_model.items():
        rate = _get_rate(model)
        if rate is None or model == "<synthetic>":
            if model != "<synthetic>" and model:
                unknown.append(model)
            result[model] = 0.0
            continue

        cost = (
            tok.get("input", 0)          * rate.input         / 1_000_000
            + tok.get("output", 0)       * rate.output        / 1_000_000
            + tok.get("cache_read", 0)   * rate.cache_read    / 1_000_000
            + tok.get("cache_write_5m", 0) * rate.cache_write_5m / 1_000_000
            + tok.get("cache_write_1h", 0) * rate.cache_write_1h / 1_000_000
        )
        result[model] = round(cost, 6)

    result["total"] = round(sum(v for k, v in result.items() if k != "total"), 6)
    result["unknown_models"] = unknown
    return result
