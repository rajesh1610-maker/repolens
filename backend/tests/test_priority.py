"""Tests for the priority scoring functions.

These tests lock the contract for `static_priority` and `total_score`.
The formulas are:

    static_priority = 0.5 * reactions_total
                     - 10 if draft and kind == 'pr'
                     +  5 if any of {"good first issue", "help wanted"} in labels

    total_score = static_priority - 5 * days_since(last_activity_at)

Both formulas are pure functions of their inputs. Changing weights here
should change at most one test plus a comment in priority.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from repolens.services.priority import (
    LABEL_BOOST,
    PRIORITY_DRAFT_PENALTY,
    PRIORITY_LABEL_BONUS,
    PRIORITY_REACTION_WEIGHT,
    PRIORITY_TIME_DECAY_PER_DAY,
    static_priority,
    total_score,
)


def _item(**overrides) -> dict:
    base = {
        "kind": "issue",
        "draft": False,
        "reactions_total": 0,
        "labels": [],
    }
    base.update(overrides)
    return base


# ---------------- static_priority ----------------


def test_baseline_item_scores_zero() -> None:
    assert static_priority(_item()) == pytest.approx(0.0)


def test_reactions_contribute_half_each() -> None:
    assert static_priority(_item(reactions_total=10)) == pytest.approx(
        PRIORITY_REACTION_WEIGHT * 10
    )
    assert static_priority(_item(reactions_total=100)) == pytest.approx(
        PRIORITY_REACTION_WEIGHT * 100
    )


def test_draft_pr_takes_penalty() -> None:
    assert static_priority(_item(kind="pr", draft=True)) == pytest.approx(
        -PRIORITY_DRAFT_PENALTY
    )


def test_draft_flag_on_issue_does_not_apply_pr_penalty() -> None:
    """`draft` is a PR-only concept; a stray True on an issue must not penalize."""
    assert static_priority(_item(kind="issue", draft=True)) == pytest.approx(0.0)


@pytest.mark.parametrize("label", sorted(LABEL_BOOST))
def test_each_boost_label_grants_bonus(label: str) -> None:
    assert static_priority(_item(labels=[label])) == pytest.approx(
        PRIORITY_LABEL_BONUS
    )


def test_label_bonus_applies_once_even_with_multiple_matches() -> None:
    """Two boost labels still only give one bonus — boost is a flag, not a sum."""
    assert static_priority(
        _item(labels=["good first issue", "help wanted"])
    ) == pytest.approx(PRIORITY_LABEL_BONUS)


def test_unrelated_labels_have_no_effect() -> None:
    assert static_priority(_item(labels=["bug", "p0", "wip"])) == pytest.approx(0.0)


def test_label_match_is_case_insensitive_and_whitespace_tolerant() -> None:
    """GitHub labels can have inconsistent casing — match defensively."""
    assert static_priority(_item(labels=["Good First Issue"])) == pytest.approx(
        PRIORITY_LABEL_BONUS
    )
    assert static_priority(_item(labels=["  HELP wanted  "])) == pytest.approx(
        PRIORITY_LABEL_BONUS
    )


def test_signals_compose_additively() -> None:
    item = _item(
        kind="pr",
        draft=True,
        reactions_total=20,
        labels=["good first issue"],
    )
    expected = (
        PRIORITY_REACTION_WEIGHT * 20  # +10
        - PRIORITY_DRAFT_PENALTY  # -10
        + PRIORITY_LABEL_BONUS  # +5
    )
    assert static_priority(item) == pytest.approx(expected)


def test_missing_optional_fields_are_handled() -> None:
    """The builder may pass partial dicts (e.g. PR rows lack reactions)."""
    assert static_priority({"kind": "pr"}) == pytest.approx(0.0)
    assert static_priority({"kind": "issue"}) == pytest.approx(0.0)


# ---------------- total_score ----------------


def test_total_score_with_zero_age_equals_static() -> None:
    now = datetime(2026, 5, 7, 12, 0, tzinfo=UTC)
    assert total_score(static=10.0, last_activity_at=now, now=now) == pytest.approx(
        10.0
    )


def test_total_score_decays_linearly_with_days() -> None:
    now = datetime(2026, 5, 7, tzinfo=UTC)
    one_day_ago = now - timedelta(days=1)
    seven_days_ago = now - timedelta(days=7)

    assert total_score(0.0, one_day_ago, now) == pytest.approx(
        -PRIORITY_TIME_DECAY_PER_DAY
    )
    assert total_score(0.0, seven_days_ago, now) == pytest.approx(
        -7 * PRIORITY_TIME_DECAY_PER_DAY
    )


def test_total_score_static_then_decay() -> None:
    """Popular old issue: 10 reactions (+5) updated 7 days ago (-35) = -30."""
    now = datetime(2026, 5, 7, tzinfo=UTC)
    seven_days_ago = now - timedelta(days=7)
    assert total_score(5.0, seven_days_ago, now) == pytest.approx(
        5.0 - 7 * PRIORITY_TIME_DECAY_PER_DAY
    )
