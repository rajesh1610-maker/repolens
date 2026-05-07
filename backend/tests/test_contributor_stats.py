"""Pure tests for parse_contributor_stats."""

from __future__ import annotations

from datetime import UTC, datetime

from repolens.services.sync import parse_contributor_stats


def _entry(login: str | None, weeks: list[dict]) -> dict:
    if login is None:
        return {"author": None, "weeks": weeks, "total": sum(w.get("c", 0) for w in weeks)}
    return {
        "author": {"login": login, "avatar_url": f"https://avatars/{login}"},
        "weeks": weeks,
        "total": sum(w.get("c", 0) for w in weeks),
    }


def _w(timestamp: int, commits: int) -> dict:
    return {"w": timestamp, "a": 0, "d": 0, "c": commits}


def test_parser_returns_empty_for_empty_input() -> None:
    assert parse_contributor_stats([]) == []


def test_parser_skips_entries_without_login() -> None:
    out = parse_contributor_stats([_entry(None, [_w(1, 5)])])
    assert out == []


def test_parser_sums_last_13_weeks_only() -> None:
    """20 weeks of 1 commit each → only the trailing 13 should count."""
    weeks = [_w(t, 1) for t in range(1, 21)]  # 20 weeks
    out = parse_contributor_stats([_entry("alice", weeks)])
    assert len(out) == 1
    assert out[0]["github_login"] == "alice"
    assert out[0]["commits_total"] == 13


def test_parser_last_commit_at_uses_most_recent_active_week() -> None:
    # week 5 has 0 commits; week 7 has the most-recent activity
    weeks = [_w(t, c) for t, c in [(1, 1), (2, 0), (3, 2), (4, 0), (5, 0), (6, 0), (7, 3)]]
    out = parse_contributor_stats([_entry("alice", weeks)])
    assert out[0]["last_commit_at"] == datetime.fromtimestamp(7, tz=UTC)


def test_parser_last_commit_at_is_none_when_no_recent_commits() -> None:
    weeks = [_w(t, 0) for t in range(1, 21)]
    out = parse_contributor_stats([_entry("alice", weeks)])
    assert out[0]["commits_total"] == 0
    assert out[0]["last_commit_at"] is None


def test_parser_handles_recent_weeks_param() -> None:
    weeks = [_w(t, 1) for t in range(1, 21)]
    out_5 = parse_contributor_stats([_entry("alice", weeks)], recent_weeks=5)
    out_20 = parse_contributor_stats([_entry("alice", weeks)], recent_weeks=20)
    assert out_5[0]["commits_total"] == 5
    assert out_20[0]["commits_total"] == 20


def test_parser_avatar_passes_through() -> None:
    out = parse_contributor_stats([_entry("bob", [_w(1, 1)])])
    assert out[0]["avatar_url"] == "https://avatars/bob"


def test_parser_multiple_authors_preserve_order() -> None:
    stats = [
        _entry("alice", [_w(1, 5)]),
        _entry("bob", [_w(2, 3)]),
        _entry(None, [_w(3, 100)]),  # skipped
        _entry("carol", [_w(4, 7)]),
    ]
    out = parse_contributor_stats(stats)
    assert [e["github_login"] for e in out] == ["alice", "bob", "carol"]
