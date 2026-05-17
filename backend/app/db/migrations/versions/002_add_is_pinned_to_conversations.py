"""Add is_pinned column to conversations.

Revision ID: 002_add_is_pinned_to_conversations
Revises: 001_initial_schema
Create Date: 2026-05-18

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision: str = "002_add_is_pinned"
down_revision = "001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "is_pinned",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "is_pinned")
