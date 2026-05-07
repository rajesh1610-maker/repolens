"""Deterministic release-notes generator.

Categorizes merged PRs into Features / Fixes / Other based on
conventional-commit prefix in the title or labels. No LLM — Phase 8
adds AI polish on top. The output is a markdown string the user can
copy + paste into a GitHub release.

Categorization rules (first match wins):
    Features  — title starts with `feat:` or `feature:`,
                or labels include `feature` / `enhancement`
    Fixes     — title starts with `fix:` or `bug:`,
                or labels include `bug` / `fix`
    Breaking  — title contains `BREAKING CHANGE` (anywhere) or
                labels include `breaking` / `breaking-change`
    Other     — everything else
"""

from __future__ import annotations

from typing import Any

CATEGORY_FEATURES = "Features"
CATEGORY_FIXES = "Fixes"
CATEGORY_BREAKING = "Breaking changes"
CATEGORY_OTHER = "Other"

ORDER = (CATEGORY_BREAKING, CATEGORY_FEATURES, CATEGORY_FIXES, CATEGORY_OTHER)
EMOJI = {
    CATEGORY_BREAKING: "💥",
    CATEGORY_FEATURES: "🚀",
    CATEGORY_FIXES: "🐛",
    CATEGORY_OTHER: "📝",
}


def _prefix_matches(title: str, prefixes: tuple[str, ...]) -> bool:
    lower = title.lstrip().lower()
    return any(lower.startswith(p) for p in prefixes)


def _has_label(labels: list[str], targets: set[str]) -> bool:
    for label in labels or []:
        if isinstance(label, str) and label.strip().lower() in targets:
            return True
    return False


def categorize_pr(title: str, labels: list[str]) -> str:
    """Return one of ORDER. Pure function for test pinning."""
    if "BREAKING CHANGE" in (title or "") or _has_label(
        labels, {"breaking", "breaking-change", "breaking change"}
    ):
        return CATEGORY_BREAKING
    if _prefix_matches(title or "", ("feat:", "feature:")) or _has_label(
        labels, {"feature", "enhancement"}
    ):
        return CATEGORY_FEATURES
    if _prefix_matches(title or "", ("fix:", "bug:")) or _has_label(
        labels, {"bug", "fix"}
    ):
        return CATEGORY_FIXES
    return CATEGORY_OTHER


_STRIPPABLE_PREFIXES: tuple[str, ...] = (
    "feat:",
    "feature:",
    "fix:",
    "bug:",
    "chore:",
    "docs:",
    "refactor:",
)


def _strip_prefix(title: str) -> str:
    """Drop a leading `feat:` / `fix:` etc so the bullet reads cleanly."""
    lower = title.lstrip().lower()
    for p in _STRIPPABLE_PREFIXES:
        if lower.startswith(p):
            return title.lstrip()[len(p):].lstrip()
    return title


def generate_notes(
    *,
    repo_full_name: str,
    next_tag: str,
    previous_tag: str | None,
    pulls: list[dict[str, Any]],
) -> str:
    """Build a markdown release-notes draft.

    `pulls` is a list of dicts shaped like the /api/repos/{}/{}/pulls
    response — must include `number`, `title`, `labels`, `author_login`.
    Order within a category preserves the input order (caller usually
    sorts merged-at desc).
    """
    sections: dict[str, list[dict[str, Any]]] = {c: [] for c in ORDER}
    for pr in pulls:
        cat = categorize_pr(pr.get("title", ""), pr.get("labels") or [])
        sections[cat].append(pr)

    lines: list[str] = []
    header = f"## {next_tag} — {repo_full_name}"
    lines.append(header)
    if previous_tag:
        lines.append(f"_Compared to **{previous_tag}**._")
    lines.append("")

    if not pulls:
        lines.append("_No merged pull requests since the last release._")
        return "\n".join(lines)

    for cat in ORDER:
        rows = sections[cat]
        if not rows:
            continue
        lines.append(f"### {EMOJI[cat]} {cat}")
        for pr in rows:
            title = _strip_prefix(pr.get("title", ""))
            num = pr.get("number")
            author = pr.get("author_login")
            suffix = f" (#{num}" + (f" by @{author}" if author else "") + ")"
            lines.append(f"- {title}{suffix}")
        lines.append("")

    contributors = sorted(
        {p["author_login"] for p in pulls if p.get("author_login")}
    )
    if contributors:
        lines.append("---")
        lines.append("Thanks to: " + ", ".join(f"@{c}" for c in contributors))

    return "\n".join(lines).rstrip() + "\n"
