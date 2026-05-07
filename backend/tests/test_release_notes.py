"""Pure-function tests for the release-notes generator."""

from __future__ import annotations

import pytest

from repolens.services.release_notes import (
    CATEGORY_BREAKING,
    CATEGORY_FEATURES,
    CATEGORY_FIXES,
    CATEGORY_OTHER,
    categorize_pr,
    generate_notes,
)


@pytest.mark.parametrize(
    "title,labels,expected",
    [
        # Conventional-commit prefixes
        ("feat: new dashboard", [], CATEGORY_FEATURES),
        ("feature: rate limiting", [], CATEGORY_FEATURES),
        ("fix: null pointer", [], CATEGORY_FIXES),
        ("bug: edge case", [], CATEGORY_FIXES),
        # Labels (case-insensitive)
        ("Improve docs", ["enhancement"], CATEGORY_FEATURES),
        ("Random title", ["Bug"], CATEGORY_FIXES),
        # Breaking takes priority
        ("feat: BREAKING CHANGE in API", [], CATEGORY_BREAKING),
        ("Anything", ["breaking-change"], CATEGORY_BREAKING),
        # Default
        ("chore: bump deps", [], CATEGORY_OTHER),
        ("Just some refactor", [], CATEGORY_OTHER),
    ],
)
def test_categorize_pr(title: str, labels: list[str], expected: str) -> None:
    assert categorize_pr(title, labels) == expected


def test_generate_notes_empty_list_says_so() -> None:
    out = generate_notes(
        repo_full_name="owner/repo",
        next_tag="v1.0.1",
        previous_tag="v1.0.0",
        pulls=[],
    )
    assert "owner/repo" in out
    assert "v1.0.1" in out
    assert "no merged" in out.lower()


def test_generate_notes_groups_and_orders_categories() -> None:
    pulls = [
        {"number": 1, "title": "feat: A", "labels": [], "author_login": "alice"},
        {"number": 2, "title": "fix: B", "labels": [], "author_login": "bob"},
        {
            "number": 3,
            "title": "BREAKING CHANGE: API change",
            "labels": [],
            "author_login": "alice",
        },
        {"number": 4, "title": "Misc tidy", "labels": [], "author_login": None},
    ]
    out = generate_notes(
        repo_full_name="o/r",
        next_tag="v2.0.0",
        previous_tag="v1.9.0",
        pulls=pulls,
    )

    # Order: Breaking first, then Features, Fixes, Other.
    breaking_idx = out.index("Breaking changes")
    features_idx = out.index("Features")
    fixes_idx = out.index("Fixes")
    other_idx = out.index("Other")
    assert breaking_idx < features_idx < fixes_idx < other_idx


def test_generate_notes_strips_conventional_prefix_from_bullet() -> None:
    pulls = [
        {"number": 7, "title": "feat: cleaner UI", "labels": [], "author_login": "x"},
    ]
    out = generate_notes(
        repo_full_name="o/r", next_tag="v1.0.0", previous_tag=None, pulls=pulls
    )
    # Bullet should NOT start with "feat:" — that's the category header now
    assert "- cleaner UI (#7" in out
    assert "feat:" not in out.split("Features")[1].split("\n")[1]


def test_generate_notes_thanks_unique_authors() -> None:
    pulls = [
        {"number": 1, "title": "feat: x", "labels": [], "author_login": "alice"},
        {"number": 2, "title": "fix: y", "labels": [], "author_login": "bob"},
        {"number": 3, "title": "fix: z", "labels": [], "author_login": "alice"},
    ]
    out = generate_notes(
        repo_full_name="o/r", next_tag="v1.0.0", previous_tag=None, pulls=pulls
    )
    # alice appears once in the thanks line, not twice
    thanks_line = [line for line in out.splitlines() if line.startswith("Thanks")]
    assert len(thanks_line) == 1
    assert thanks_line[0].count("@alice") == 1
    assert "@bob" in thanks_line[0]
