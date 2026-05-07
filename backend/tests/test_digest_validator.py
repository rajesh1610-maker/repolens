"""Pure-function tests for the digest validator."""

from __future__ import annotations

from repolens.services.digest_validator import REQUIRED_SECTIONS, validate

# A minimal valid body — every required section, prose only.
GOOD_BODY = (
    "## Headline\n"
    "Quiet week with two PRs landing.\n\n"
    "## What shipped\n"
    "- Merged #12 in foo/bar — search fix\n"
    "- Merged #15 in foo/bar — docs touch-up\n\n"
    "## What's stuck\n"
    "- #98 has been blocked for 21 days\n\n"
    "## Community pulse\n"
    "- 3 new issues, 1 with reactions\n"
    "- Stars: +4\n\n"
    "## Suggested actions for the week ahead\n"
    "- Review #98 — blocked label, 3 reactions\n"
    "- Triage #99 — needs-info, no response in 14 days\n"
    "- Cut a patch release — 5 fixes since last tag\n"
    + ("\nFiller text. " * 30)
)


def test_validate_clean_body_returns_no_warnings() -> None:
    assert validate(GOOD_BODY) == []


def test_validate_empty_body_warns() -> None:
    warnings = validate("")
    assert warnings == ["Digest body is empty."]


def test_validate_whitespace_body_warns() -> None:
    warnings = validate("   \n   \t  \n")
    assert warnings == ["Digest body is empty."]


def test_validate_short_body_warns_about_length() -> None:
    short = (
        "## Headline\nx\n## What shipped\n## What's stuck\n"
        "## Community pulse\n## Suggested actions for the week ahead\n"
    )
    warnings = validate(short)
    assert any("unusually short" in w for w in warnings)


def test_validate_missing_section_warns_for_each_missing() -> None:
    body = (
        "## Headline\n"
        "x\n\n"
        "## What shipped\n"
        "x\n\n"
        + ("Filler text. " * 60)  # push past min length
    )
    warnings = validate(body)
    missing = [w for w in warnings if w.startswith("Missing required section")]
    # Three required sections are missing
    assert len(missing) == 3
    assert any("What's stuck" in w for w in missing)
    assert any("Community pulse" in w for w in missing)
    assert any("Suggested actions for the week ahead" in w for w in missing)


def test_validate_wrong_heading_count_warns() -> None:
    extra = GOOD_BODY + "\n## Bonus section\nextra content\n"
    warnings = validate(extra)
    assert any(
        f"Expected {len(REQUIRED_SECTIONS)} H2 sections" in w for w in warnings
    )


def test_validate_code_fence_warns() -> None:
    fenced = GOOD_BODY + "\n\n```json\n{\"x\": 1}\n```\n"
    warnings = validate(fenced)
    assert any("code fence" in w for w in warnings)


def test_validate_section_match_is_case_insensitive() -> None:
    """Be lenient: a model that writes 'HEADLINE' shouldn't fail the check."""
    body = GOOD_BODY.replace("## Headline", "## HEADLINE")
    warnings = validate(body)
    # 5 sections still found, all required ones still match
    assert not any("Missing required section" in w for w in warnings)
