"""trustworthy money answers: per-account balances, sync cursor, category tree

Revision ID: 7a3e9c2d4b10
Revises: 1f84796e238d
Create Date: 2026-09-19 12:00:00.000000

Besides the new columns, this re-seeds the category tree (Transfer becomes
its own non-spend type; Gas, Restaurants, Travel, ... become categories)
and re-maps every existing transaction from its stored
raw_aggregator_category. Without the re-map, rows synced before this
migration would keep counting credit-card payments as spending.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session


# revision identifiers, used by Alembic.
revision: str = '7a3e9c2d4b10'
down_revision: Union[str, None] = '1f84796e238d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('timezone', sa.String(), nullable=True))
    op.add_column('linked_accounts', sa.Column('name', sa.String(), nullable=True))
    op.add_column('linked_accounts', sa.Column('mask', sa.String(), nullable=True))
    op.add_column('linked_accounts', sa.Column('current_balance', sa.Numeric(14, 2), nullable=True))
    op.add_column('linked_accounts', sa.Column('balance_as_of', sa.DateTime(timezone=True), nullable=True))
    op.add_column('linked_accounts', sa.Column('sync_cursor', sa.Text(), nullable=True))
    op.add_column('transactions', sa.Column('pending_transaction_id', sa.String(), nullable=True))

    # Imported here, not at module top, so `alembic history` etc. don't
    # need the app importable.
    from app.services.category_backfill import recategorize_all_transactions

    recategorize_all_transactions(Session(bind=op.get_bind()))


def downgrade() -> None:
    op.drop_column('transactions', 'pending_transaction_id')
    op.drop_column('linked_accounts', 'sync_cursor')
    op.drop_column('linked_accounts', 'balance_as_of')
    op.drop_column('linked_accounts', 'current_balance')
    op.drop_column('linked_accounts', 'mask')
    op.drop_column('linked_accounts', 'name')
    op.drop_column('users', 'timezone')
