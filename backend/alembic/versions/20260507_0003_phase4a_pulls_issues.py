"""phase4a: pull_requests + issues + SyncRun counters

Revision ID: 0003_phase4a
Revises: 0002_phase1
Create Date: 2026-05-07

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0003_phase4a"
down_revision: Union[str, None] = "0002_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sync_runs",
        sa.Column("pulls_synced", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "sync_runs",
        sa.Column("issues_synced", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "pull_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("repo_id", UUID(as_uuid=True), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("draft", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("author_login", sa.String(length=255), nullable=True),
        sa.Column("author_avatar_url", sa.String(length=512), nullable=True),
        sa.Column("labels", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", JSONB(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("github_id", name="uq_pulls_github_id"),
        sa.UniqueConstraint("repo_id", "number", name="uq_pulls_repo_number"),
    )
    op.create_index(
        "ix_pulls_repo_state_updated",
        "pull_requests",
        ["repo_id", "state", "updated_at"],
    )

    op.create_table(
        "issues",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("repo_id", UUID(as_uuid=True), nullable=False),
        sa.Column("github_id", sa.BigInteger(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("author_login", sa.String(length=255), nullable=True),
        sa.Column("author_avatar_url", sa.String(length=512), nullable=True),
        sa.Column("labels", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reactions_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw", JSONB(), nullable=True),
        sa.Column(
            "synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("github_id", name="uq_issues_github_id"),
        sa.UniqueConstraint("repo_id", "number", name="uq_issues_repo_number"),
    )
    op.create_index(
        "ix_issues_repo_state_reactions",
        "issues",
        ["repo_id", "state", "reactions_total"],
    )


def downgrade() -> None:
    op.drop_index("ix_issues_repo_state_reactions", table_name="issues")
    op.drop_table("issues")
    op.drop_index("ix_pulls_repo_state_updated", table_name="pull_requests")
    op.drop_table("pull_requests")
    op.drop_column("sync_runs", "issues_synced")
    op.drop_column("sync_runs", "pulls_synced")
