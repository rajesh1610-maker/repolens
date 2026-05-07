import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StarsDaily(Base):
    """Daily snapshot of `repos.stargazers_count`.

    Stars history is constructed from these daily snapshots (D-7.2). The
    very first snapshot is "today's stars at first sync"; subsequent
    days fill in as the user keeps RepoLens running. `stars_delta` is
    not stored — it's computed at query time as
    `stars_total - LAG(stars_total)` so the math stays in one place.
    """

    __tablename__ = "stars_daily"

    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    stars_total: Mapped[int] = mapped_column(Integer, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
