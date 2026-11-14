"""recurring series can sit out of the budget

Revision ID: l5e2a9c4b173
Revises: k4d8b1c5e290
Create Date: 2026-11-14 15:35:00.000000

Budget auto-fills from recurring charges so a new user has a starting list.
in_budget lets them drop a vendor or group from Budget without dismissing
the series — it's still a subscription, just not an envelope.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l5e2a9c4b173"
down_revision: Union[str, None] = "k4d8b1c5e290"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "recurring_series",
        sa.Column("in_budget", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade() -> None:
    op.drop_column("recurring_series", "in_budget")
