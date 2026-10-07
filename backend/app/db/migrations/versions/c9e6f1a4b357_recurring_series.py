"""recurring bills, subscriptions and paychecks

Revision ID: c9e6f1a4b357
Revises: b8d5e0f3a246
Create Date: 2026-10-07 10:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c9e6f1a4b357"
down_revision: Union[str, None] = "b8d5e0f3a246"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "recurring_series",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("merchant_key", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id"), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("cadence", sa.String(), nullable=False),
        sa.Column("typical_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("last_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("last_date", sa.Date(), nullable=False),
        sa.Column("next_expected_date", sa.Date(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="suggested"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "merchant_key", "direction"),
    )
    op.create_index("ix_recurring_series_user_id", "recurring_series", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_recurring_series_user_id", "recurring_series")
    op.drop_table("recurring_series")
