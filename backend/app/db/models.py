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
    account_type: Mapped[str] = mapped_column(String)  # checking | savings | credit | loan | investment
    # Encrypted at rest; never returned to the client. See app/integrations/plaid_client.py.
    access_token_ref: Mapped[str] = mapped_column(Text)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")  # active | disconnected | error

    user: Mapped["User"] = relationship(back_populates="linked_accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="linked_account")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # income | expense
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
