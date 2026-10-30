"""daily briefings, what users did about their items, cancel links and notification prefs

Revision ID: b7d2e9f4a183
Revises: c3a9f1e8b247
Create Date: 2026-10-30 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "b7d2e9f4a183"
down_revision: Union[str, None] = "c3a9f1e8b247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _user_id() -> sa.Column:
    return sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "daily_briefings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _user_id(),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("items", postgresql.JSONB(), nullable=False),
        sa.Column("intro", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "day", name="uq_daily_briefing_user_day"),
    )
    op.create_index("ix_daily_briefings_user_id", "daily_briefings", ["user_id"])

    op.create_table(
        "briefing_item_states",
        sa.Column("id", sa.Uuid(), primary_key=True),
        _user_id(),
        sa.Column("item_key", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "item_key"),
    )
    op.create_index("ix_briefing_item_states_user_id", "briefing_item_states", ["user_id"])

    op.create_table(
        "merchant_cancel_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("merchant_key", sa.String(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_merchant_cancel_links_merchant_key", "merchant_cancel_links", ["merchant_key"], unique=True)

    op.create_table(
        "notification_prefs",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("daily_briefing", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("weekly_recap", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_table("notification_prefs")
    op.drop_table("merchant_cancel_links")
    op.drop_table("briefing_item_states")
    op.drop_table("daily_briefings")
