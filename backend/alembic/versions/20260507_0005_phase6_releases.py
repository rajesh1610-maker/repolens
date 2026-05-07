"""phase6: releases table + sync_runs.releases_synced

Revision ID: 0005_phase6
Revises: 0004_phase5
Create Date: 2026-05-07

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005_phase6"
down_revision: Union[str, None] = "0004_phase5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sync_runs",
        sa.Column(
            "releases_synced", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    op.create_table(
        "releases",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("repo_id", UUID(as_uuid=True), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("tag_name", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=512), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "draft", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "prerelease",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("body_md", sa.Text(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("github_id", name="uq_releases_github_id"),
        sa.UniqueConstraint("repo_id", "tag_name", name="uq_releases_repo_tag"),
    )
    op.create_index(
        "ix_releases_repo_published", "releases", ["repo_id", "published_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_releases_repo_published", table_name="releases")
    op.drop_table("releases")
    op.drop_column("sync_runs", "releases_synced")
