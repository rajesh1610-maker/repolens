"""phase1: users, repos, sync_runs

Revision ID: 0002_phase1
Revises: 0001_initial
Create Date: 2026-05-07

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002_phase1"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("github_login", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("avatar_url", sa.String(length=512), nullable=True),
        sa.Column("pat_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("anthropic_key_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column(
            "public_only_mode",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("github_id", name="uq_users_github_id"),
    )

    op.create_table(
        "repos",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("owner", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("stars", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("forks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_issues_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pushed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "tracked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("github_id", name="uq_repos_github_id"),
    )
    op.create_index("ix_repos_user_tracked", "repos", ["user_id", "tracked"])
    op.create_index("ix_repos_full_name", "repos", ["full_name"])

    op.create_table(
        "sync_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repos_synced", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("api_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rate_limit_remaining", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'running'"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("sync_runs")
    op.drop_index("ix_repos_full_name", table_name="repos")
    op.drop_index("ix_repos_user_tracked", table_name="repos")
    op.drop_table("repos")
    op.drop_table("users")
