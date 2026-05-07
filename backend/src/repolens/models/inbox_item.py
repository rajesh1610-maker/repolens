import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class InboxItem(Base):
    """Denormalized rollup for the Inbox page.

    Rebuilt at the end of every successful sync. Contains only OPEN items
    from TRACKED repos. Each row carries enough denormalized context (repo
    name, title, labels, URL) to render the Inbox without joining to
    `repos` / `pull_requests` / `issues`.

    `priority_score` is the *atemporal* component (reactions, draft
    penalty, label boost). Time-decay (`-5 * days_since_last_activity`)
    is computed at query time so ranking stays fresh between syncs.
    """

    __tablename__ = "inbox_items"
    __table_args__ = (
        Index("ix_inbox_user_priority", "user_id", "priority_score"),
        Index("ix_inbox_user_kind", "user_id", "kind"),
        Index("ix_inbox_user_last_activity", "user_id", "last_activity_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False
    )

    # 'pr' | 'issue' — drives source table when we need the full row,
    # and the icon/state pill on the frontend.
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Denormalized snapshot — Inbox queries should never need to JOIN.
    repo_full_name: Mapped[str] = mapped_column(String(512), nullable=False)
    repo_visibility: Mapped[str] = mapped_column(String(16), nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    draft: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    author_login: Mapped[str | None] = mapped_column(String(255), nullable=True)
    author_avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    labels: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default="[]"
    )
    reactions_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    comments_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Static (atemporal) priority. Time-decay applied at query time.
    priority_score: Mapped[float] = mapped_column(
        Numeric(8, 2), nullable=False, default=0, server_default="0"
    )

    # Phase 5 always sets these false. Phase 6+ wires them up once we
    # sync comments / review requests / mention timelines.
    is_review_request: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_mention: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_needs_response: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_stale: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
