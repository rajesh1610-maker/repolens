"""Phase 8: soft-validation for the generated weekly digest markdown.

Returns a list of human-readable warnings — never raises, never blocks
the save. The user gets the digest body even if the model wrote
something unexpected; warnings render in the UI as "we noticed:" notes
and are persisted in `validation_warnings` so a later prompt tweak can
be evaluated against historical drift.

Required structure (from the original spec):
    H2 "Headline"
    H2 "What shipped"
    H2 "What's stuck"
    H2 "Community pulse"
    H2 "Suggested actions for the week ahead"
"""

from __future__ import annotations

import re

REQUIRED_SECTIONS: tuple[str, ...] = (
    "Headline",
    "What shipped",
    "What's stuck",
    "Community pulse",
    "Suggested actions for the week ahead",
)

H2_PATTERN = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
MIN_BODY_CHARS = 400
MAX_BODY_CHARS = 12_000


def validate(body_md: str) -> list[str]:
    """Return zero or more warning strings. Empty list = looks fine.

    Designed to be cheap and order-independent — every check runs even
    if an earlier one fired, so the user sees the full set of issues.
    """
    warnings: list[str] = []

    if not body_md or not body_md.strip():
        warnings.append("Digest body is empty.")
        return warnings

    body_len = len(body_md)
    if body_len < MIN_BODY_CHARS:
        warnings.append(
            f"Digest is unusually short ({body_len} chars; expected >= {MIN_BODY_CHARS})."
        )
    if body_len > MAX_BODY_CHARS:
        warnings.append(
            f"Digest is unusually long ({body_len} chars; expected <= {MAX_BODY_CHARS})."
        )

    found_headings = [m.strip() for m in H2_PATTERN.findall(body_md)]
    found_lower = {h.lower() for h in found_headings}

    for required in REQUIRED_SECTIONS:
        if required.lower() not in found_lower:
            warnings.append(f"Missing required section: '## {required}'.")

    if len(found_headings) != len(REQUIRED_SECTIONS):
        warnings.append(
            f"Expected {len(REQUIRED_SECTIONS)} H2 sections, found {len(found_headings)}."
        )

    if "```" in body_md:
        # Digests are prose. Code fences usually mean the model echoed
        # raw JSON or a stack trace from the facts dict — worth flagging.
        warnings.append(
            "Digest contains a code fence (```), which is unexpected for a prose digest."
        )

    return warnings
