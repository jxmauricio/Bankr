"""named save/track goals

Revision ID: d4f1c0a8e912
Revises: c2e8a91b4d70
Create Date: 2026-09-20 16:00:00.000000

Goals are one of two kinds: save (a named dollar target) or track_spending.
The old save_amount / pay_off_debt / build_emergency_fund types become
save rows with those labels as names, not separate categories.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4f1c0a8e912"
down_revision: Union[str, None] = "c2e8a91b4d70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("goals", sa.Column("name", sa.String(), nullable=True))
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE goals SET name = CASE type
                WHEN 'pay_off_debt' THEN 'Paying off debt'
                WHEN 'build_emergency_fund' THEN 'Emergency fund'
                WHEN 'save_amount' THEN 'Savings goals'
                WHEN 'track_spending' THEN COALESCE(category, 'Spending')
                ELSE COALESCE(name, 'Goal')
            END
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE goals SET type = 'save'
            WHERE type IN ('save_amount', 'pay_off_debt', 'build_emergency_fund')
            """
        )
    )


def downgrade() -> None:
    op.drop_column("goals", "name")
