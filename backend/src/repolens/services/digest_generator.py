"""Phase 8: weekly-digest generator orchestrator.

Wires the moving parts:

    collect_facts()          → JSON facts dict for the window
    Anthropic Messages API   → markdown body
    validate()               → soft warnings
    Digest model row         → persisted (replace-via-DELETE on conflict)

Why "replace-via-DELETE": the (user_id, period_start, period_end) UNIQUE
makes regeneration deterministic — re-running for the same week
explicitly overwrites the previous attempt rather than producing a
duplicate row that the UI would have to disambiguate.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Digest, User
from .anthropic_client import compute_cost, make_client
from .digest_collector import collect_facts, week_window
from .digest_validator import validate

log = logging.getLogger(__name__)


SYSTEM_PROMPT = """\
You are RepoLens, an AI co-maintainer that writes a single weekly digest \
for an open-source maintainer based on a JSON facts dict the user gives you.

Your output is a markdown document with EXACTLY these five H2 sections, in order:

## Headline
A single sentence — the most important thing about the week. No bullet list.

## What shipped
What landed: merged PRs, releases, notable features. Group by repo if multiple. \
2-6 bullets. Reference PR numbers as `#123` (no markdown link, just the number).

## What's stuck
Issues / PRs that need the maintainer's attention this week. Use the \
`stuck_issues` facts. 2-5 bullets. Be honest if nothing is stuck.

## Community pulse
New issues, reactions, traffic, stars. 2-4 bullets. If the numbers are zero or \
near-zero, say so plainly — don't manufacture excitement.

## Suggested actions for the week ahead
3-5 concrete actions the maintainer could take, ordered by priority. \
Be specific (e.g. "Triage #234 — 3 reactions, blocked label, 21 days stale") \
not generic ("review old issues").

Hard rules:
- Use ONLY facts from the JSON dict. Never invent PR numbers, names, repo \
  names, dates, or counts. If a fact isn't in the dict, don't write it.
- If the dict is empty (no activity in the window), write a short, honest \
  digest that says so — do not pad.
- No code fences, no JSON echoes, no preamble before the first H2.
- The H2 headings must match the five above EXACTLY (case-sensitive).
"""


@dataclass
class DigestResult:
    """Returned to the API layer + scheduler. The Digest row is the
    canonical source of truth; this dataclass just makes the call site
    readable.
    """

    digest: Digest
    warnings: list[str]


class DigestGenerationError(Exception):
    """Raised when generation fails in a way the caller should surface
    (missing API key, model refused, transport error)."""


async def generate_digest(
    db: AsyncSession,
    user: User,
    api_key: str,
    *,
    model: str,
    period_start: date | None = None,
    period_end: date | None = None,
    max_tokens: int = 4000,
) -> DigestResult:
    """Generate (or regenerate) a weekly digest for the given user + window.

    `api_key` is resolved by the caller (services.auth.resolve_anthropic_key)
    so this function stays pure-ish — it doesn't touch settings or
    crypto, only the SDK and the DB.
    """
    if period_start is None or period_end is None:
        period_start, period_end = week_window()

    facts = await collect_facts(db, user, period_start, period_end)

    user_message = (
        "Here is the JSON facts dict for the week of "
        f"{period_start.isoformat()} through {period_end.isoformat()}. "
        "Write the digest now, following the system instructions exactly.\n\n"
        f"```json\n{json.dumps(facts, indent=2, default=str)}\n```"
    )

    client = make_client(api_key)

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # Cache marker — does nothing until the system prompt
                    # crosses the 4096-token min on Opus 4.7. Cheap to keep.
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
        )
    except Exception as exc:
        log.exception("anthropic_call_failed")
        raise DigestGenerationError(
            f"Anthropic call failed: {type(exc).__name__}: {exc}"
        ) from exc

    body_md = _extract_text(response)
    stop_reason = getattr(response, "stop_reason", None)

    if stop_reason == "refusal":
        raise DigestGenerationError(
            "Model declined to generate this digest "
            "(stop_reason=refusal). Try a different week or smaller fact set."
        )

    warnings = validate(body_md)
    usage = response.usage
    cost = compute_cost(usage, model)

    digest = await _persist(
        db,
        user=user,
        period_start=period_start,
        period_end=period_end,
        body_md=body_md,
        input_summary=_summarize_input(facts),
        validation_warnings=warnings,
        model=model,
        usage=usage,
        cost=cost,
        stop_reason=stop_reason,
    )

    return DigestResult(digest=digest, warnings=warnings)


def _extract_text(response: Any) -> str:
    """Concatenate every `text` content block from the response.

    Opus 4.7 may emit `thinking` blocks too; we drop those — `text` is
    the only thing we render. If the response unexpectedly has no text
    block (e.g. tool_use only), return empty string and let the
    validator flag it.
    """
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            parts.append(getattr(block, "text", "") or "")
    return "".join(parts).strip()


def _summarize_input(facts: dict[str, Any]) -> dict[str, Any]:
    """Trim the facts dict to a stable subset for the audit column.

    We keep the totals + counts (cheap to store, useful for "what did
    the model see?" without rendering the full bullet list each time
    the user opens the page).
    """
    return {
        "period": facts.get("period"),
        "repo_count": facts.get("repo_count"),
        "totals": facts.get("totals"),
        "counts": {
            "merged_prs_shown": len(facts.get("merged_prs", [])),
            "merged_prs_truncated": facts.get("merged_prs_truncated", 0),
            "new_issues_shown": len(facts.get("new_issues", [])),
            "new_issues_truncated": facts.get("new_issues_truncated", 0),
            "closed_issues_shown": len(facts.get("closed_issues", [])),
            "closed_issues_truncated": facts.get("closed_issues_truncated", 0),
            "releases_shown": len(facts.get("releases", [])),
            "stuck_issues_shown": len(facts.get("stuck_issues", [])),
        },
    }


async def _persist(
    db: AsyncSession,
    *,
    user: User,
    period_start: date,
    period_end: date,
    body_md: str,
    input_summary: dict[str, Any],
    validation_warnings: list[str],
    model: str,
    usage: Any,
    cost: Decimal,
    stop_reason: str | None,
) -> Digest:
    # Replace-via-DELETE: explicit, observable, and avoids a partial
    # update where some columns from the previous row leak through.
    await db.execute(
        delete(Digest).where(
            Digest.user_id == user.id,
            Digest.period_start == period_start,
            Digest.period_end == period_end,
        )
    )

    digest = Digest(
        id=uuid.uuid4(),
        user_id=user.id,
        period_start=period_start,
        period_end=period_end,
        body_md=body_md,
        input_summary=input_summary,
        validation_warnings=validation_warnings,
        model=model,
        tokens_in=int(getattr(usage, "input_tokens", 0) or 0),
        tokens_out=int(getattr(usage, "output_tokens", 0) or 0),
        cache_creation_input_tokens=int(
            getattr(usage, "cache_creation_input_tokens", 0) or 0
        ),
        cache_read_input_tokens=int(
            getattr(usage, "cache_read_input_tokens", 0) or 0
        ),
        cost_usd=cost,
        stop_reason=stop_reason,
    )
    db.add(digest)
    await db.commit()
    await db.refresh(digest)
    return digest


async def latest_digest(db: AsyncSession, user: User) -> Digest | None:
    """Most recently generated digest for the user (newest period_end first)."""
    stmt = (
        select(Digest)
        .where(Digest.user_id == user.id)
        .order_by(Digest.period_end.desc(), Digest.generated_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_digests(
    db: AsyncSession, user: User, *, limit: int = 20
) -> list[Digest]:
    stmt = (
        select(Digest)
        .where(Digest.user_id == user.id)
        .order_by(Digest.period_end.desc(), Digest.generated_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())
