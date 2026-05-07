"""phase5: inbox_items derived table

Revision ID: 0004_phase5
Revises: 0003_phase4a
Create Date: 2026-05-07

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0004_phase5"
down_revision: Union[str, None] = "0003_phase4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "inbox_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("repo_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),
        sa.Column("repo_full_name", sa.String(length=512), nullable=False),
        sa.Column("repo_visibility", sa.String(length=16), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column(
            "draft", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("author_login", sa.String(length=255), nullable=True),
        sa.Column("author_avatar_url", sa.String(length=512), nullable=True),
        sa.Column(
            "labels", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("reactions_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "priority_score",
            sa.Numeric(8, 2),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "is_review_request",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_mention",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_needs_response",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["repo_id"], ["repos.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_inbox_user_priority", "inbox_items", ["user_id", "priority_score"]
    )
    op.create_index("ix_inbox_user_kind", "inbox_items", ["user_id", "kind"])
    op.create_index(
        "ix_inbox_user_last_activity", "inbox_items", ["user_id", "last_activity_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_inbox_user_last_activity", table_name="inbox_items")
    op.drop_index("ix_inbox_user_kind", table_name="inbox_items")
    op.drop_index("ix_inbox_user_priority", table_name="inbox_items")
    op.drop_table("inbox_items")
