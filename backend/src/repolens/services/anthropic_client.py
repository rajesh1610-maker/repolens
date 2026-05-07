"""Anthropic SDK factory + pricing + cost computation (Phase 8 — weekly digest).

A thin shim over `AsyncAnthropic` so the rest of the codebase doesn't import
the SDK directly. Two reasons:

1. Centralizes the cost table — pricing is per-model and we want one place
   to update when Anthropic publishes new tiers.
2. Lets tests inject a fake client without monkey-patching the SDK module.

Pricing (USD per token, last refreshed 2026-04-29; see `shared/models.md`
in the claude-api skill):

    claude-opus-4-7   — $5.00 / $25.00 per 1M input/output tokens
    claude-haiku-4-5  — $1.00 / $5.00  per 1M input/output tokens

Cache write is 1.25x input; cache read is 0.10x input — Anthropic's
standard ephemeral pricing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic


# Per-token pricing. Multiply by token count to get USD.
# Stored as Decimal for safe accumulation into the digests.cost_usd column.
PRICING: dict[str, dict[str, Decimal]] = {
    "claude-opus-4-7": {
        "input": Decimal("5.00") / Decimal(1_000_000),
        "output": Decimal("25.00") / Decimal(1_000_000),
        "cache_write": Decimal("6.25") / Decimal(1_000_000),
        "cache_read": Decimal("0.50") / Decimal(1_000_000),
    },
    "claude-haiku-4-5": {
        "input": Decimal("1.00") / Decimal(1_000_000),
        "output": Decimal("5.00") / Decimal(1_000_000),
        "cache_write": Decimal("1.25") / Decimal(1_000_000),
        "cache_read": Decimal("0.10") / Decimal(1_000_000),
    },
}


def make_client(api_key: str) -> AsyncAnthropic:
    """Return an `AsyncAnthropic` bound to the caller's API key.

    Imported lazily so test environments without the package can still
    import this module (the cost table is useful on its own).
    """
    from anthropic import AsyncAnthropic

    return AsyncAnthropic(api_key=api_key)


def compute_cost(usage: Any, model: str) -> Decimal:
    """Compute USD cost from an Anthropic Usage block.

    `usage` is the `.usage` attribute of a Message response (or any object
    with `input_tokens`, `output_tokens`, and the two cache counters).
    Unknown models fall back to opus-4-7 pricing — better to over-report
    than to record $0 and lose the audit trail.

    Returns a Decimal so callers can store it directly in Numeric(10, 6).
    """
    rates = PRICING.get(model, PRICING["claude-opus-4-7"])

    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

    return (
        Decimal(input_tokens) * rates["input"]
        + Decimal(output_tokens) * rates["output"]
        + Decimal(cache_write) * rates["cache_write"]
        + Decimal(cache_read) * rates["cache_read"]
    ).quantize(Decimal("0.000001"))
