"""phase7: traffic_daily + stars_daily + contributors

Revision ID: 0006_phase7
Revises: 0005_phase6
Create Date: 2026-05-07

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0006_phase7"
down_revision: Union[str, None] = "0005_phase6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sync_runs",
        sa.Column(
            "traffic_days_synced", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "sync_runs",
        sa.Column(
            "contributors_synced", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    op.create_table(
        "traffic_daily",
        sa.Column("repo_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "unique_views", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("clones", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "unique_clones", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "stars_daily",
        sa.Column("repo_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("stars_total", sa.Integer(), nullable=False),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "contributors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("repo_id", UUID(as_uuid=True), nullable=False),
        sa.Column("github_login", sa.String(length=255), nullable=False),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column(
            "commits_total", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_commit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "repo_id", "github_login", name="uq_contributors_repo_login"
        ),
    )
    op.create_index(
        "ix_contributors_repo_commits",
        "contributors",
        ["repo_id", "commits_total"],
    )


def downgrade() -> None:
    op.drop_index("ix_contributors_repo_commits", table_name="contributors")
    op.drop_table("contributors")
    op.drop_table("stars_daily")
    op.drop_table("traffic_daily")
    op.drop_column("sync_runs", "contributors_synced")
    op.drop_column("sync_runs", "traffic_days_synced")
