"""memory facts: what the agent remembers about the user across conversations

Revision ID: f2d6a9c1e384
Revises: e8b1d4f2a690
Create Date: 2026-10-30 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "f2d6a9c1e384"
down_revision: Union[str, None] = "e8b1d4f2a690"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "memory_facts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("text", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_memory_facts_user_id", "memory_facts", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_memory_facts_user_id", "memory_facts")
    op.drop_table("memory_facts")
