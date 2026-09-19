import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    apple_sub: Mapped[str | None] = mapped_column(String, unique=True, index=True, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # IANA name (e.g. "America/New_York"), reported by the client. Decides
    # where "this month" / "last week" start and end -- a UTC server
    # otherwise puts a 9pm Pacific purchase on the 1st into the wrong month.
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    linked_accounts: Mapped[list["LinkedAccount"]] = relationship(back_populates="user")
    goals: Mapped[list["Goal"]] = relationship(back_populates="user")


class LinkedAccount(Base):
    __tablename__ = "linked_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    aggregator: Mapped[str] = mapped_column(String, default="plaid")
    aggregator_account_id: Mapped[str] = mapped_column(String, index=True)
    institution_name: Mapped[str] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    mask: Mapped[str | None] = mapped_column(String, nullable=True)  # last 4 digits
    account_type: Mapped[str] = mapped_column(String)  # checking | savings | credit | loan | investment
    # Stored per account (not just summed into NetWorthSnapshot) so net worth
    # can be shown as the visible sum of its parts. For credit/loan this is
    # the amount owed, as a positive number.
    current_balance: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    balance_as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Encrypted at rest; never returned to the client. See app/integrations/plaid_client.py.
    access_token_ref: Mapped[str] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active | disconnected | error
    # Aggregator's incremental-sync cursor. It belongs to the whole bank
    # login (every account under one access token shares it), so
    # sync_service.py writes the same value to each of those accounts.
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Plaid's Item id -- the whole bank login, shared by every account under
    # it, same as sync_cursor. This is how an inbound webhook (which only
    # carries an item_id, never an access token) finds its way back to a
    # user's rows; see app/services/webhook_service.py. Nullable because
    # accounts linked before this column existed don't have one yet -- it
    # gets backfilled the next time that login is synced (see
    # app/api/accounts.py resync_all_accounts).
    item_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)

    user: Mapped["User"] = relationship(back_populates="linked_accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="linked_account")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # income | expense | transfer
    parent_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = uuid_pk()
    linked_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("linked_accounts.id"), index=True)
    aggregator_transaction_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    date: Mapped[date] = mapped_column(Date, index=True)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_aggregator_category: Mapped[str | None] = mapped_column(String, nullable=True)
    bankr_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    is_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    linked_account: Mapped["LinkedAccount"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship()


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String)  # save_amount | pay_off_debt | build_emergency_fund
    target_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    starting_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    current_progress_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String, default="active")  # active | completed | abandoned
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="goals")


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    total_assets: Mapped[float] = mapped_column(Numeric(14, 2))
    total_liabilities: Mapped[float] = mapped_column(Numeric(14, 2))
    net_worth: Mapped[float] = mapped_column(Numeric(14, 2))


class InsightLog(Base):
    __tablename__ = "insight_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String)  # overspend | goal_drift | unusual_transaction | weekly_summary
    message: Mapped[str] = mapped_column(Text)
    related_transaction_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    delivered_via: Mapped[str] = mapped_column(String)  # push | in_app
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    role: Mapped[str] = mapped_column(String)  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text)
    # [{"tool": name, "label": ...}, ...] for an assistant message -- the
    # tool calls that backed this reply, shown to the user as a
    # trust/verification trail (see claude_agent.run_agent_turn). Always
    # null on user-role messages.
    tool_calls: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
