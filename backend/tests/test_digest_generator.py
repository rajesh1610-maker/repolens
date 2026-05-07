"""Generator tests with a fake Anthropic client.

We don't hit the real API — `generate_digest` takes the SDK call site
through `make_client(api_key)`, so we monkeypatch that to return a
stubbed AsyncAnthropic-shaped object whose `messages.create` returns a
canned response. Lets us verify:

  * the persisted Digest row carries usage/cost/warnings
  * regeneration replaces (UNIQUE constraint behavior)
  * stop_reason="refusal" surfaces as DigestGenerationError
  * empty/blank body still persists (with warnings)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import delete, insert, select

from repolens.db import SessionLocal
from repolens.models import Digest, Repo, User
from repolens.services import digest_generator
from repolens.services.anthropic_client import compute_cost
from repolens.services.digest_generator import (
    DigestGenerationError,
    generate_digest,
)

PERIOD_START = date(2026, 4, 27)
PERIOD_END = date(2026, 5, 3)


@dataclass
class _FakeUsage:
    input_tokens: int = 1200
    output_tokens: int = 600
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass
class _FakeBlock:
    type: str
    text: str


@dataclass
class _FakeResponse:
    content: list[_FakeBlock]
    usage: _FakeUsage
    stop_reason: str | None = "end_turn"


class _FakeMessages:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.last_kwargs: dict[str, Any] | None = None

    async def create(self, **kwargs: Any) -> _FakeResponse:
        self.last_kwargs = kwargs
        return self.response


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.messages = _FakeMessages(response)


GOOD_BODY = (
    "## Headline\n"
    "Two PRs landed; nothing on fire.\n\n"
    "## What shipped\n"
    "- Merged #10\n\n"
    "## What's stuck\n"
    "- Nothing this week.\n\n"
    "## Community pulse\n"
    "- Stars +0; one new issue.\n\n"
    "## Suggested actions for the week ahead\n"
    "- Triage backlog.\n"
    "- Tag a release.\n"
    "- Reply to oldest PR.\n"
    + ("Filler text to clear the min-length floor. " * 10)
)


@pytest.fixture
async def seeded_user() -> Any:
    user_id = uuid.uuid4()
    base_gh = 9_500_000_000_000
    async with SessionLocal() as db:
        await db.execute(
            insert(User).values(
                id=user_id,
                github_id=base_gh,
                github_login=f"gen-test-{user_id.hex[:8]}",
                public_only_mode=False,
            )
        )
        await db.execute(
            insert(Repo).values(
                id=uuid.uuid4(),
                user_id=user_id,
                github_id=base_gh + 1,
                owner="gt",
                name="repo",
                full_name="gt/repo",
                visibility="public",
                stars=0,
                forks=0,
                open_issues_count=0,
                tracked=True,
            )
        )
        await db.commit()

    yield user_id

    async with SessionLocal() as db:
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()


async def _load_user(user_id: uuid.UUID) -> User:
    async with SessionLocal() as db:
        return (await db.execute(select(User).where(User.id == user_id))).scalar_one()


def _patch_client(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> _FakeClient:
    fake = _FakeClient(response)
    monkeypatch.setattr(digest_generator, "make_client", lambda _key: fake)
    return fake


@pytest.mark.asyncio
async def test_generate_persists_digest_with_usage_and_cost(
    seeded_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = seeded_user
    user = await _load_user(user_id)
    response = _FakeResponse(
        content=[_FakeBlock(type="text", text=GOOD_BODY)],
        usage=_FakeUsage(input_tokens=1200, output_tokens=600),
    )
    fake = _patch_client(monkeypatch, response)

    async with SessionLocal() as db:
        result = await generate_digest(
            db,
            user,
            api_key="sk-fake",
            model="claude-opus-4-7",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )

    assert result.warnings == []
    assert result.digest.body_md.startswith("## Headline")
    assert result.digest.tokens_in == 1200
    assert result.digest.tokens_out == 600
    assert result.digest.model == "claude-opus-4-7"
    assert result.digest.stop_reason == "end_turn"
    expected_cost = compute_cost(_FakeUsage(1200, 600), "claude-opus-4-7")
    assert result.digest.cost_usd == expected_cost
    assert expected_cost > Decimal("0")

    # input_summary keeps the period & totals (audit trail)
    assert result.digest.input_summary["period"]["start"] == PERIOD_START.isoformat()

    # The SDK call carried adaptive thinking + a cache marker on the system block
    assert fake.messages.last_kwargs is not None
    assert fake.messages.last_kwargs["thinking"] == {"type": "adaptive"}
    system = fake.messages.last_kwargs["system"]
    assert isinstance(system, list)
    assert system[0]["cache_control"] == {"type": "ephemeral"}


@pytest.mark.asyncio
async def test_generate_replaces_existing_digest_for_same_period(
    seeded_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = seeded_user
    user = await _load_user(user_id)
    response = _FakeResponse(
        content=[_FakeBlock(type="text", text=GOOD_BODY)],
        usage=_FakeUsage(),
    )
    _patch_client(monkeypatch, response)

    async with SessionLocal() as db:
        first = await generate_digest(
            db,
            user,
            api_key="sk-fake",
            model="claude-opus-4-7",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )
        second = await generate_digest(
            db,
            user,
            api_key="sk-fake",
            model="claude-opus-4-7",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )

    assert first.digest.id != second.digest.id

    async with SessionLocal() as db:
        rows = (
            await db.execute(select(Digest).where(Digest.user_id == user_id))
        ).scalars().all()

    assert len(rows) == 1
    assert rows[0].id == second.digest.id


@pytest.mark.asyncio
async def test_generate_refusal_raises(
    seeded_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = seeded_user
    user = await _load_user(user_id)
    response = _FakeResponse(
        content=[_FakeBlock(type="text", text="I cannot do that.")],
        usage=_FakeUsage(),
        stop_reason="refusal",
    )
    _patch_client(monkeypatch, response)

    async with SessionLocal() as db:
        with pytest.raises(DigestGenerationError):
            await generate_digest(
                db,
                user,
                api_key="sk-fake",
                model="claude-opus-4-7",
                period_start=PERIOD_START,
                period_end=PERIOD_END,
            )

        # No row persisted on refusal
        rows = (
            await db.execute(select(Digest).where(Digest.user_id == user_id))
        ).scalars().all()
        assert rows == []


@pytest.mark.asyncio
async def test_generate_persists_with_warnings_when_body_malformed(
    seeded_user, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Soft-validation contract: malformed body still saves, warnings populated."""
    user_id = seeded_user
    user = await _load_user(user_id)
    response = _FakeResponse(
        content=[_FakeBlock(type="text", text="too short")],
        usage=_FakeUsage(),
    )
    _patch_client(monkeypatch, response)

    async with SessionLocal() as db:
        result = await generate_digest(
            db,
            user,
            api_key="sk-fake",
            model="claude-opus-4-7",
            period_start=PERIOD_START,
            period_end=PERIOD_END,
        )

    assert result.warnings  # non-empty
    assert result.digest.body_md == "too short"
    assert result.digest.validation_warnings == result.warnings


def test_compute_cost_known_model() -> None:
    """Sanity-check: 1M tokens in + 1M tokens out on Opus 4.7 = $5 + $25 = $30."""
    usage = _FakeUsage(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_creation_input_tokens=0,
        cache_read_input_tokens=0,
    )
    cost = compute_cost(usage, "claude-opus-4-7")
    assert cost == Decimal("30.000000")


def test_compute_cost_unknown_model_falls_back_to_opus() -> None:
    usage = _FakeUsage(input_tokens=1_000_000, output_tokens=0)
    cost_unknown = compute_cost(usage, "made-up-model")
    cost_opus = compute_cost(usage, "claude-opus-4-7")
    assert cost_unknown == cost_opus  # fallback


def test_compute_cost_includes_cache_tokens() -> None:
    usage = _FakeUsage(
        input_tokens=0,
        output_tokens=0,
        cache_creation_input_tokens=1_000_000,  # $6.25 on Opus 4.7
        cache_read_input_tokens=1_000_000,  # $0.50 on Opus 4.7
    )
    cost = compute_cost(usage, "claude-opus-4-7")
    assert cost == Decimal("6.750000")
