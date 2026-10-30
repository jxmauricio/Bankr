import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
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


class DevicePushToken(Base):
    """One iOS (or later Android) device that's allowed to receive pushes
    for this user. The same physical phone re-registers the same token;
    a token that shows up under a new user is reassigned, because APNs
    tokens are per-install, not per-account."""

    __tablename__ = "device_push_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String, unique=True)
    platform: Mapped[str] = mapped_column(String, default="ios")  # ios | android
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LinkedAccount(Base):
    __tablename__ = "linked_accounts"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    aggregator: Mapped[str] = mapped_column(String, default="plaid")
    aggregator_account_id: Mapped[str] = mapped_column(String, index=True)
    institution_name: Mapped[str] = mapped_column(String)
    institution_logo: Mapped[str | None] = mapped_column(Text, nullable=True)  # base64 PNG
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


class CategoryGroup(Base):
    """A heading over categories: Food & Dining over Groceries, Restaurants & Bars,
    Coffee Shops. Only categories hold transactions, splits and rules; a group is
    what totals roll up to, and what a budget can cover as one line (see
    CategoryPref.budget_mode). Every category is in exactly one group, and a
    category that stands alone (Travel) is the only one in its group."""

    __tablename__ = "category_groups"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Stable id of a built-in group ("food_and_drink"); None on a user's own.
    system_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # income | expense | transfer | excluded
    # Set on a group a user made for themselves; None on the built-in ones.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String)
    type: Mapped[str] = mapped_column(String)  # income | expense | transfer | excluded
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("category_groups.id"), index=True)
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=True)
    # Stable id of a built-in category ("restaurants"), what code looks it up
    # by: the name is only for people. None on a user's own categories.
    system_key: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    # Set on a category a user made for themselves (see category_service);
    # None on the built-in ones, which every user shares.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    group: Mapped["CategoryGroup"] = relationship(lazy="joined")


class CategoryPref(Base):
    """One user's view of a built-in category or group, which every user
    shares: their own name for it, and for a spending group, whether its
    budget is one line for the group or a line per category."""

    __tablename__ = "category_prefs"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id"),
        UniqueConstraint("user_id", "group_id"),
        CheckConstraint("(category_id IS NULL) <> (group_id IS NULL)", name="category_prefs_one_target"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="CASCADE"), nullable=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("category_groups.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    budget_mode: Mapped[str | None] = mapped_column(String, nullable=True)  # by_group (default) | by_category
    # A built-in category this user doesn't want: gone from pickers, and
    # what would land in it lands in Uncategorized instead.
    hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = uuid_pk()
    linked_account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("linked_accounts.id", ondelete="CASCADE"), index=True)
    aggregator_transaction_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    date: Mapped[date] = mapped_column(Date, index=True)
    merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    raw_aggregator_category: Mapped[str | None] = mapped_column(String, nullable=True)
    # Plaid's confidence in raw_aggregator_category (VERY_HIGH ... LOW,
    # UNKNOWN). LOW/UNKNOWN expense rows get a second opinion from
    # app/services/category_classifier.py.
    aggregator_category_confidence: Mapped[str | None] = mapped_column(String, nullable=True)
    bankr_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    is_pending: Mapped[bool] = mapped_column(Boolean, default=False)
    pending_transaction_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # User edits. merchant_name is what every surface shows; the aggregator's
    # own name is kept in original_merchant_name so rules can still match it
    # after a rename. merchant_overridden stops a re-sync (which re-maps
    # every modified row) from undoing the user's rename.
    original_merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    merchant_overridden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Where bankr_category_id came from: manual | rule | learned | classifier
    # | aggregator | fallback (see categorization_service). A re-sync never
    # touches a manual one.
    category_source: Mapped[str] = mapped_column(String, default="aggregator", server_default="aggregator")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Excluded rows still show in the Transactions list but never count as
    # spending or income (a reimbursed work trip, a one-off gift).
    is_excluded: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # A split parent stays as the bank's record but stops counting; its
    # children (same account and date, aggregator id "<parent>:split:<n>")
    # carry the amounts and categories instead. Children must sum to it.
    is_split: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    split_parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True, index=True
    )

    linked_account: Mapped["LinkedAccount"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship()


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String)  # save | track_spending
    target_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    starting_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    current_progress_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    status: Mapped[str] = mapped_column(String, default="active")  # active | completed | abandoned
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    # track_spending only: what it watches -- a group, a category or a named
    # slice of a group ("eating_out", see money_query.CATEGORY_SLICES),
    # exactly one of the three -- and a rolling named window ("this_month").
    # Savings goals leave these null.
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("category_groups.id", ondelete="SET NULL"), nullable=True
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    category_slice: Mapped[str | None] = mapped_column(String, nullable=True)
    window: Mapped[str | None] = mapped_column(String, nullable=True)

    user: Mapped["User"] = relationship(back_populates="goals")


class NetWorthSnapshot(Base):
    __tablename__ = "net_worth_snapshots"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    total_assets: Mapped[float] = mapped_column(Numeric(14, 2))
    total_liabilities: Mapped[float] = mapped_column(Numeric(14, 2))
    net_worth: Mapped[float] = mapped_column(Numeric(14, 2))


class InsightLog(Base):
    __tablename__ = "insight_logs"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String)  # budget_overspend | goal_drift | unusual_transaction | price_change
    message: Mapped[str] = mapped_column(Text)
    related_transaction_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    # Identifies the event an insight is about (see insights_job._dedupe_key)
    # so the job, which reruns on every sync, never phrases it twice.
    dedupe_key: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    delivered_via: Mapped[str] = mapped_column(String)  # push | in_app
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WeeklyRecap(Base):
    """One Monday-Sunday summary: the numbers (computed in Python) and the
    short take Claude wrote from them. The latest one also gets an
    InsightLog row ("weekly_recap:<week_start>"), which carries its read
    state and puts it in the notifications list."""

    __tablename__ = "weekly_recaps"
    __table_args__ = (UniqueConstraint("user_id", "week_start", name="uq_weekly_recap_user_week"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    week_start: Mapped[date] = mapped_column(Date)
    week_end: Mapped[date] = mapped_column(Date)
    headline: Mapped[str] = mapped_column(String)
    facts: Mapped[dict] = mapped_column(JSONB)
    # Null when the model couldn't be reached; the numbers still show.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    role: Mapped[str] = mapped_column(String)  # user | assistant | tool
    content: Mapped[str] = mapped_column(Text)
    # [{"tool": name, "label": ...}, ...] for an assistant message -- the
    # tool calls that backed this reply, shown to the user as a
    # trust/verification trail (see claude_agent.run_agent_turn). Always
    # null on user-role messages.
    tool_calls: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MerchantCategoryGuess(Base):
    """A classifier's answer for one merchant, shared by every user: a
    merchant's name says the same thing whoever shops there. Cached so each
    merchant costs one call, and so a re-sync never flips its category."""

    __tablename__ = "merchant_category_guesses"

    id: Mapped[uuid.UUID] = uuid_pk()
    # Lowercased, whitespace-collapsed bank merchant name; see category_classifier.merchant_key.
    merchant_key: Mapped[str] = mapped_column(String, unique=True, index=True)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    source: Mapped[str] = mapped_column(String)  # e.g. "jev"
    model: Mapped[str] = mapped_column(String)  # which classifier version answered
    # The classifier's own certainty, 0-1. Kept even when it's below
    # settings.jev_min_confidence: the merchant isn't asked again, and the
    # transaction keeps Plaid's category.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LearnedCategory(Base):
    """What a user keeps picking for one merchant. Each time they move a
    merchant's transaction to the same category by hand, hits goes up; a
    different pick starts over. From LEARN_AFTER hits on, that merchant's
    new rows land there (categorization_service), below the user's rules."""

    __tablename__ = "learned_categories"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # See category_classifier.merchant_key.
    merchant_key: Mapped[str] = mapped_column(String)
    category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))
    hits: Mapped[int] = mapped_column(default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class Rule(Base):
    """"Always categorize <merchant> as <category>" -- applied to every
    synced transaction the user hasn't categorized by hand."""

    __tablename__ = "rules"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # Case-insensitive text of the bank's merchant name (or the user's rename):
    # anywhere in it, or the whole name when match_exact.
    merchant_contains: Mapped[str] = mapped_column(String)
    match_exact: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Optional bounds on the charge's size (absolute value).
    amount_min: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount_max: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    linked_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("linked_accounts.id", ondelete="CASCADE"), nullable=True
    )
    set_category_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("categories.id"))
    set_merchant_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # Higher wins when several rules match; ties go to the newest.
    priority: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class RecurringSeries(Base):
    """A charge (or paycheck) that repeats on a schedule, found by
    app/services/recurring_service.py. Detection re-runs after every sync
    and refreshes the numbers, but never changes the user's status or kind."""

    __tablename__ = "recurring_series"
    __table_args__ = (UniqueConstraint("user_id", "merchant_key", "direction"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    merchant_key: Mapped[str] = mapped_column(String)  # normalized merchant name
    direction: Mapped[str] = mapped_column(String)  # out | in
    display_name: Mapped[str] = mapped_column(String)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String)  # bill | subscription | income
    cadence: Mapped[str] = mapped_column(String)  # weekly | biweekly | monthly | quarterly | yearly
    # Sizes are positive. typical_amount is the median of every charge
    # before the latest, so a price change shows as last != typical.
    typical_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    last_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    last_date: Mapped[date] = mapped_column(Date)
    next_expected_date: Mapped[date] = mapped_column(Date)
    occurrences: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String, default="suggested")  # suggested | confirmed | dismissed
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class BudgetSettings(Base):
    """How a user budgets. "flex" (the default): fixed bills each get a line
    and everything else shares one Flexible amount. "category": every
    category gets its own line, YNAB-style."""

    __tablename__ = "budget_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    mode: Mapped[str] = mapped_column(String, default="flex")  # flex | category
    flex_amount: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    flex_rollover: Mapped[bool] = mapped_column(Boolean, default=False)
    # First month the Flexible amount applies to; its rollover starts here.
    start_month: Mapped[date] = mapped_column(Date)


class Budget(Base):
    """A monthly amount for one spending group, or for one category in a
    group the user budgets by category (CategoryPref.budget_mode)."""

    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category_id"),
        UniqueConstraint("user_id", "group_id"),
        CheckConstraint("(category_id IS NULL) <> (group_id IS NULL)", name="budgets_one_target"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("category_groups.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    group: Mapped[str] = mapped_column(String, default="flex")  # fixed | flex (only matters in flex mode)
    # Leftover (or overspending) carries into next month.
    rollover: Mapped[bool] = mapped_column(Boolean, default=False)
    # First month the budget applies to; rollover never reaches before it.
    start_month: Mapped[date] = mapped_column(Date)


class BudgetMove(Base):
    """Money moved between budget lines for one month -- how overspending
    gets covered. Each side is a group's line or a category's; both null
    means the Flexible bucket."""

    __tablename__ = "budget_moves"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month: Mapped[date] = mapped_column(Date)  # first of the month
    from_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    to_category_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    from_group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("category_groups.id"), nullable=True)
    to_group_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("category_groups.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(12, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
