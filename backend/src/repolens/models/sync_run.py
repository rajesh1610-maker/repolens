import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    repos_synced: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    api_calls: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rate_limit_remaining: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="'running'"
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
