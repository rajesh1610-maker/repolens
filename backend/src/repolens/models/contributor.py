import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Contributor(Base):
    """Per-repo contributor snapshot.

    `commits_total` is the sum of commits in the last 13 weeks (≈90d)
    from GitHub's `/stats/contributors` weeks array. We rebuild the
    full list on each successful contributors-sync, so missing rows
    indicate the contributor stopped contributing. UNIQUE on
    `(repo_id, github_login)` for upserts.
    """

    __tablename__ = "contributors"
    __table_args__ = (
        UniqueConstraint("repo_id", "github_login", name="uq_contributors_repo_login"),
        Index("ix_contributors_repo_commits", "repo_id", "commits_total"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repos.id", ondelete="CASCADE"), nullable=False
    )
    github_login: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    commits_total: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_commit_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
