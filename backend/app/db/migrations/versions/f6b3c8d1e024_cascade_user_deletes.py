"""cascade deletes from users down through every user-owned table

Revision ID: f6b3c8d1e024
Revises: e5a2b7c9d013
Create Date: 2026-10-03 13:00:00.000000

Deleting a row in users now removes their linked_accounts, goals,
net_worth_snapshots, insight_logs and chat_messages, and (via
linked_accounts) their transactions.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f6b3c8d1e024"
down_revision: Union[str, None] = "e5a2b7c9d013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column, referenced table) -- constraint names are Postgres defaults.
_FKS = [
    ("linked_accounts", "user_id", "users"),
    ("goals", "user_id", "users"),
    ("net_worth_snapshots", "user_id", "users"),
    ("insight_logs", "user_id", "users"),
    ("chat_messages", "user_id", "users"),
    ("transactions", "linked_account_id", "linked_accounts"),
]


def _recreate(ondelete: str | None) -> None:
    for table, column, ref in _FKS:
        name = f"{table}_{column}_fkey"
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, ref, [column], ["id"], ondelete=ondelete)


def upgrade() -> None:
    _recreate("CASCADE")


def downgrade() -> None:
    _recreate(None)
