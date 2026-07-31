"""
API pricing per million tokens (MTok), verified 2026-07-30 against
https://platform.claude.com/docs/en/about-claude/pricing.
This is the *equivalent* API cost, not what the user paid (they use a subscription).

Costs computed here run below what the CLI's own `/cost` reports, because the token
counts they are computed from come from the session transcript, and the transcript
does not record every billed API call. Requests the CLI makes on the side are not
written to the jsonl at all — most visibly the fast-model helper behind
WebSearch/WebFetch, whose entire model line can be absent from the file while
appearing in `/cost`.

The counts the transcript *does* record are the real billed ones, and are used as-is.
Two of them look wrong at a glance and are not:

  * `usage.input_tokens` is the genuinely uncached remainder, not a placeholder —
    the full prompt is input + cache_read + cache_creation. It reads 1-2 on most
    turns because the CLI's cache breakpoint sits on the last content block, and is
    only large on a first, uncached call (e.g. the opening turn of a subagent).
  * `usage.output_tokens` already includes thinking tokens. On models that never
    return raw chain-of-thought the thinking text is absent from the transcript, but
    the tokens are in this count and are billed as output.

See the `Rate` table below for the per-model numbers; see the de-duplication notes in
parser.py for how the counts themselves are arrived at.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Rate:
    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float


# Rates ordered from most-specific to least-specific — matched by substring on model id.
# Source: https://platform.claude.com/docs/en/about-claude/pricing (verified 2026-07-30).
# Every row derives from the published input rate: cache_read = 0.1x input,
# cache_write_5m = 1.25x input, cache_write_1h = 2x input. test_rates_derive_from_input_price
# pins that, so a new row can't quietly invent its own ratios.
#
# The 1h column used to be set equal to the 5m column, on the assumption that the CLI
# bills 1h writes at the 5m rate. That was wrong: 2x input is the published rate for a
# 1h cache write, and every row was understating cost on sessions with 1h cache
# creation. A residual against `/cost` remains under either value — most plausibly the
# side requests described in the module docstring — so don't read the 1h rate back off
# that difference.
_RATES: list[tuple[str, Rate]] = [
    # Fable 5 / Mythos 5 (same pricing; Mythos is Project Glasswing-only)
    ("fable-5",   Rate(10.00, 50.00, 1.00, 12.50, 20.00)),
    ("mythos-5",  Rate(10.00, 50.00, 1.00, 12.50, 20.00)),
    # Opus 5 — same rates as Opus 4.8
    ("opus-5",    Rate(5.00,  25.00, 0.50, 6.25,  10.00)),
    # Opus 4.x new pricing
    ("opus-4-8",  Rate(5.00,  25.00, 0.50, 6.25,  10.00)),
    ("opus-4-7",  Rate(5.00,  25.00, 0.50, 6.25,  10.00)),
    ("opus-4-6",  Rate(5.00,  25.00, 0.50, 6.25,  10.00)),
    ("opus-4-5",  Rate(5.00,  25.00, 0.50, 6.25,  10.00)),
    # Opus 4.1 / original Opus 4 legacy pricing. The original Opus 4 id is
    # "claude-opus-4-20250514", so match "opus-4-2025" rather than a bare
    # "opus-4" — a bare prefix would silently price future models (opus-4-9, …)
    # at the legacy 3x rate. Unmatched new models surface in unknown_models
    # instead; add them above when they ship.
    ("opus-4-1",    Rate(15.00, 75.00, 1.50, 18.75, 30.00)),
    ("opus-4-2025", Rate(15.00, 75.00, 1.50, 18.75, 30.00)),
    # Sonnet 5 — standard pricing ($3/$15); introductory $2/$10 runs through 2026-08-31.
    ("sonnet-5",   Rate(3.00, 15.00, 0.30, 3.75,  6.00)),
    # Sonnet 4.x
    ("sonnet-4-6", Rate(3.00, 15.00, 0.30, 3.75,  6.00)),
    ("sonnet-4-5", Rate(3.00, 15.00, 0.30, 3.75,  6.00)),
    ("sonnet-4",   Rate(3.00, 15.00, 0.30, 3.75,  6.00)),
    # Bare "sonnet" alias (session files sometimes record the alias, not a full id)
    ("sonnet",     Rate(3.00, 15.00, 0.30, 3.75,  6.00)),
    # Haiku
    ("haiku-4-5",  Rate(1.00,  5.00, 0.10, 1.25,  2.00)),
    ("haiku-3-5",  Rate(0.80,  4.00, 0.08, 1.00,  1.60)),
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
    Returns {"by_model": {model: usd}, "total": usd, "unknown_models": [...]}.

    Models with no known rate (and the "<synthetic>" pseudo-model the CLI writes for
    local error messages) cost 0; only the genuinely unrecognised ones are reported
    in "unknown_models".
    """
    by_model: dict[str, float] = {}
    unknown: list[str] = []

    for model, tok in tokens_by_model.items():
        rate = _get_rate(model)
        if rate is None or model == "<synthetic>":
            if model != "<synthetic>" and model:
                unknown.append(model)
            by_model[model] = 0.0
            continue

        cost = (
            tok.get("input", 0)          * rate.input         / 1_000_000
            + tok.get("output", 0)       * rate.output        / 1_000_000
            + tok.get("cache_read", 0)   * rate.cache_read    / 1_000_000
            + tok.get("cache_write_5m", 0) * rate.cache_write_5m / 1_000_000
            + tok.get("cache_write_1h", 0) * rate.cache_write_1h / 1_000_000
        )
        by_model[model] = round(cost, 6)

    return {
        "by_model": by_model,
        "total": round(sum(by_model.values()), 6),
        "unknown_models": unknown,
    }


def rate_revision() -> str:
    """A short fingerprint of the rate table. The scanner stores it and re-parses
    everything when it changes, so editing a rate actually re-prices the sessions
    already in the DB instead of only affecting sessions whose files change next."""
    return hashlib.sha256(repr(_RATES).encode()).hexdigest()[:16]


def rate_table() -> list[tuple[str, Rate]]:
    """The (match-key, Rate) table, in match order. The browser bundle keeps its own
    copy in static/app.js so it can price client-side in remote mode; tests assert the
    two stay identical."""
    return list(_RATES)
