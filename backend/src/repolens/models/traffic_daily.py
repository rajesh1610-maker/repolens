import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TrafficDaily(Base):
    """Daily traffic snapshot per repo.

    GitHub returns the last 14 days on each call; we upsert by
    `(repo_id, day)` so re-syncing the rolling window is a no-op for
    days we already have, and updates count revisions GitHub publishes.
    """

    __tablename__ = "traffic_daily"

    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("repos.id", ondelete="CASCADE"),
        primary_key=True,
    )
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    views: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unique_views: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    clones: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unique_clones: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
