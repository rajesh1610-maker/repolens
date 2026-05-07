"""Priority scoring for the Inbox.

Two pure functions, two formulas. Weights are constants so the test suite
locks the contract; tuning means changing one constant and re-reading the
test that pinned its value.

Phase 5 atemporal signals (collected from local DB):
    - reactions_total (Issue only)
    - draft (PR only)
    - boost-labels: "good first issue" / "help wanted" (case-insensitive)

Phase 5 temporal signal (computed at query time):
    - days since last_activity_at

Deferred to Phase 6+ (need data we don't yet sync):
    - is_review_request (requested_reviewers from /pulls)
    - is_mention (substring scan over comment bodies)
    - is_needs_response (comment timeline + last commenter heuristic)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

PRIORITY_REACTION_WEIGHT = 0.5
PRIORITY_DRAFT_PENALTY = 10.0
PRIORITY_LABEL_BONUS = 5.0
PRIORITY_TIME_DECAY_PER_DAY = 5.0

# Boost labels: case-insensitive match against this set.
LABEL_BOOST: frozenset[str] = frozenset({"good first issue", "help wanted"})


def _has_boost_label(labels: list[str]) -> bool:
    for label in labels:
        if not isinstance(label, str):
            continue
        if label.strip().lower() in LABEL_BOOST:
            return True
    return False


def static_priority(item: dict[str, Any]) -> float:
    """Atemporal priority score for an inbox candidate.

    Stored in `inbox_items.priority_score`. The time-decay component is
    layered on at query time via `total_score` (Python) or the equivalent
    SQL expression.

    Expected keys on `item`:
        kind: "pr" | "issue"            — required
        draft: bool                      — only meaningful for PRs
        reactions_total: int             — defaults to 0
        labels: list[str]                — defaults to []

    Missing optional keys are tolerated; this function never raises.
    """
    score = 0.0

    reactions = int(item.get("reactions_total") or 0)
    score += PRIORITY_REACTION_WEIGHT * reactions

    if item.get("kind") == "pr" and bool(item.get("draft")):
        score -= PRIORITY_DRAFT_PENALTY

    if _has_boost_label(item.get("labels") or []):
        score += PRIORITY_LABEL_BONUS

    return score


def total_score(static: float, last_activity_at: datetime, now: datetime) -> float:
    """Total priority including the time-decay component.

    Mirrors the SQL expression used in `ORDER BY` on /api/inbox so the
    Python and SQL views never drift. Days are computed in floating
    seconds for precision; truncating to integer days would create
    ranking ties at midnight.
    """
    days = (now - last_activity_at).total_seconds() / 86400.0
    return static - PRIORITY_TIME_DECAY_PER_DAY * days
