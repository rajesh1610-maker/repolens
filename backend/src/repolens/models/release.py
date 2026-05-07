import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Release(Base):
    """A GitHub release. We store published_at + tag_name + body for the
    Releases page. PRs merged since the latest release per repo become
    the input to the draft-notes generator (Phase 6 template, Phase 8 AI).
    """

    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("repo_id", "tag_name", name="uq_releases_repo_tag"),
        Index("ix_releases_repo_published", "repo_id", "published_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False
    )
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    tag_name: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    draft: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    prerelease: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    body_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
