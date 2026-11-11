"""investment holdings from Plaid

Revision ID: i2b8d4c1e073
Revises: h1a4c8e2d960
Create Date: 2026-11-11 15:40:00.000000

Brokerage positions with the close price Plaid sent on the last bank sync.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "i2b8d4c1e073"
down_revision: Union[str, None] = "h1a4c8e2d960"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "investment_holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("linked_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("security_id", sa.String(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("quantity", sa.Numeric(18, 8), nullable=False),
        sa.Column("price", sa.Numeric(14, 4), nullable=True),
        sa.Column("value", sa.Numeric(14, 2), nullable=False),
        sa.Column("cost_basis", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_as_of", sa.Date(), nullable=True),
        sa.Column("security_type", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["linked_account_id"], ["linked_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("linked_account_id", "security_id"),
    )
    op.create_index(
        op.f("ix_investment_holdings_linked_account_id"),
        "investment_holdings",
        ["linked_account_id"],
        unique=False,
    )
    op.create_index(op.f("ix_investment_holdings_user_id"), "investment_holdings", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_investment_holdings_user_id"), table_name="investment_holdings")
    op.drop_index(op.f("ix_investment_holdings_linked_account_id"), table_name="investment_holdings")
    op.drop_table("investment_holdings")
