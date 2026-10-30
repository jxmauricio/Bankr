"""thumbs up/down on chat replies

Revision ID: d3a8f1c6b927
Revises: c3a9f1e8b247
Create Date: 2026-10-30 12:00:00.000000

One row per rated assistant message (see models.ChatFeedback), exported by
app/scripts/export_feedback.py so bad answers can become eval tasks.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3a8f1c6b927"
down_revision: Union[str, None] = "c3a9f1e8b247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_feedback",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "message_id", sa.Uuid(), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, unique=True
        ),
        sa.Column("rating", sa.String(), nullable=False),
        sa.Column("reason", sa.String(280), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("rating IN ('up', 'down')", name="chat_feedback_rating"),
    )
    op.create_index("ix_chat_feedback_user_id", "chat_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_feedback_user_id", table_name="chat_feedback")
    op.drop_table("chat_feedback")
