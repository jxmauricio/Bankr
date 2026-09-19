"""plaid webhooks: item_id on linked_accounts

Revision ID: 9b1f4d7c6e2a
Revises: 7a3e9c2d4b10
Create Date: 2026-09-19 18:00:00.000000

Nullable, filled in going forward: fresh links get it from
exchange_public_token; existing rows get it lazily the next time that
bank login is resynced (see app/api/accounts.py). No backfill script is
needed -- normal use fills it in within one sync cycle per user.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9b1f4d7c6e2a'
down_revision: Union[str, None] = '7a3e9c2d4b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('linked_accounts', sa.Column('item_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_linked_accounts_item_id'), 'linked_accounts', ['item_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_linked_accounts_item_id'), table_name='linked_accounts')
    op.drop_column('linked_accounts', 'item_id')
