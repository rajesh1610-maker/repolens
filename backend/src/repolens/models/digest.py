import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Digest(Base):
    """One generated weekly digest per user, per (period_start, period_end).

    UNIQUE on `(user_id, period_start, period_end)` so re-running for the
    same week is a deliberate replace-via-DELETE; we don't accidentally
    generate two digests for one Mon-Sun window.

    `input_summary` and `validation_warnings` are persisted as JSONB so
    we can reproduce or audit a digest without re-collecting facts. The
    token + cost columns let the frontend show "this week's digest cost
    you $0.08" without needing the Anthropic dashboard.
    """

    __tablename__ = "digests"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "period_start",
            "period_end",
            name="uq_digests_user_period",
        ),
        Index("ix_digests_user_period_end", "user_id", "period_end"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)

    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    input_summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default="'{}'::jsonb"
    )
    validation_warnings: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="'[]'::jsonb"
    )

    model: Mapped[str] = mapped_column(String(64), nullable=False)
    tokens_in: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    tokens_out: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cache_creation_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cache_read_input_tokens: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(10, 6), nullable=False, server_default="0"
    )
    stop_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
