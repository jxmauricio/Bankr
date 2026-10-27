"""Plaid category confidence on transactions, plus a per-merchant cache of
classifier answers for the low-confidence ones

Revision ID: a7c2e9d4f318
Revises: b3d9e4f7a812
Create Date: 2026-10-25 12:00:00.000000

Nullable: rows synced before this have no confidence until
app/jobs/backfill_category_confidence.py (or their next modification) fills it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a7c2e9d4f318"
down_revision: Union[str, None] = "b3d9e4f7a812"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("aggregator_category_confidence", sa.String(), nullable=True))
    op.create_table(
        "merchant_category_guesses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("merchant_key", sa.String(), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_merchant_category_guesses_merchant_key"), "merchant_category_guesses", ["merchant_key"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_merchant_category_guesses_merchant_key"), table_name="merchant_category_guesses")
    op.drop_table("merchant_category_guesses")
    op.drop_column("transactions", "aggregator_category_confidence")
