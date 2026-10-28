"""Which category a transaction lands in, and why. One order, for syncs,
re-maps and the confidence backfill alike; the first that applies wins:

1. manual      the user picked it (or split the row): never touched again
2. rule        one of the user's rules (rules_service)
3. learned     the user moved this merchant to the same category
               LEARN_AFTER times by hand (LearnedCategory)
4. classifier  Plaid wasn't sure and a trusted cached second opinion says
               otherwise (category_classifier)
5. aggregator  Plaid's category, through category_mapper
6. fallback    nothing placed it, or it would land in a category the user
               hid: Uncategorized, the review queue

Transaction.category_source records which one it was.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Category, CategoryPref, LearnedCategory, LinkedAccount, Rule, Transaction
from app.services.category_classifier import merchant_key, needs_second_opinion, trusted
from app.services.category_mapper import map_raw_category
from app.services.rules_service import apply_rules, user_rules

MANUAL, RULE, LEARNED, CLASSIFIER, AGGREGATOR, FALLBACK = "manual", "rule", "learned", "classifier", "aggregator", "fallback"
UNCATEGORIZED = "uncategorized"
LEARN_AFTER = 2


@dataclass
class Context:
    """What categorize() needs about one user, loaded once per batch."""

    categories: dict[str, Category]  # built-in key -> Category (seed_default_categories)
    rules: list[Rule] = field(default_factory=list)
    guesses: dict = field(default_factory=dict)  # merchant_key -> cached classifier guess
    learned: dict[str, UUID] = field(default_factory=dict)  # merchant_key -> category id
    hidden: set[UUID] = field(default_factory=set)


def context(db: Session, user_id: UUID, categories: dict[str, Category], guesses: dict | None = None) -> Context:
    return Context(
        categories=categories,
        rules=user_rules(db, user_id),
        guesses=guesses or {},
        learned=learned_categories(db, user_id),
        hidden=hidden_categories(db, user_id),
    )


def learned_categories(db: Session, user_id: UUID) -> dict[str, UUID]:
    rows = db.query(LearnedCategory).filter(LearnedCategory.user_id == user_id, LearnedCategory.hits >= LEARN_AFTER)
    return {row.merchant_key: row.category_id for row in rows}


def hidden_categories(db: Session, user_id: UUID) -> set[UUID]:
    prefs = db.query(CategoryPref.category_id).filter(CategoryPref.user_id == user_id, CategoryPref.hidden.is_(True))
    return {category_id for (category_id,) in prefs}


def categorize(txn, account_type: str | None, ctx: Context) -> bool:
    """Set txn's bankr_category_id and category_source in place (txn can be a
    Transaction or a row-like namespace). Returns True when Plaid wasn't sure
    and there's no cached second opinion yet: worth asking the classifier."""
    if txn.category_source == MANUAL:
        return False
    if apply_rules(txn, ctx.rules) is not None:
        return False
    key = merchant_key(txn.original_merchant_name)
    if key in ctx.learned and not txn.is_split and txn.split_parent_id is None:
        txn.bankr_category_id, txn.category_source = ctx.learned[key], LEARNED
        return False

    mapped = ctx.categories[map_raw_category(txn.raw_aggregator_category, float(txn.amount), account_type, txn.original_merchant_name)]
    txn.bankr_category_id, txn.category_source = mapped.id, AGGREGATOR
    ask = False
    if needs_second_opinion(txn, mapped):
        guess = ctx.guesses.get(key)
        if guess is None:
            ask = True
        elif trusted(guess):
            txn.bankr_category_id, txn.category_source = guess.category_id, CLASSIFIER
    if txn.bankr_category_id in ctx.hidden or txn.bankr_category_id == ctx.categories[UNCATEGORIZED].id:
        txn.bankr_category_id, txn.category_source = ctx.categories[UNCATEGORIZED].id, FALLBACK
    return ask


def learn(db: Session, user_id: UUID, txn: Transaction) -> bool:
    """Count a manual pick toward learning its merchant's category. Returns
    True when this pick is the one that makes it learned."""
    key = merchant_key(txn.original_merchant_name)
    if key is None:
        return False
    row = db.query(LearnedCategory).filter(LearnedCategory.user_id == user_id, LearnedCategory.merchant_key == key).one_or_none()
    if row is None:
        row = LearnedCategory(user_id=user_id, merchant_key=key, category_id=txn.bankr_category_id, hits=0)
        db.add(row)
    if row.category_id != txn.bankr_category_id:
        row.category_id, row.hits = txn.bankr_category_id, 0  # a different pick starts over
    row.hits += 1
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
    return row.hits == LEARN_AFTER


def recategorize(db: Session, user_id: UUID, txns: list[Transaction], categories: dict[str, Category]) -> int:
    """Run the pipeline again over the user's `txns` (their own picks stay).
    Returns how many changed category."""
    from app.services.category_classifier import cached_guesses

    accounts = dict(db.query(LinkedAccount.id, LinkedAccount.account_type).filter(LinkedAccount.user_id == user_id))
    guesses = cached_guesses(db, {k for t in txns if (k := merchant_key(t.original_merchant_name))})
    ctx = context(db, user_id, categories, guesses)
    changed = 0
    for txn in txns:
        before = txn.bankr_category_id
        categorize(txn, accounts.get(txn.linked_account_id), ctx)
        changed += txn.bankr_category_id != before
    db.flush()
    return changed


def merchant_rows(db: Session, user_id: UUID, key: str) -> list[Transaction]:
    """The user's rows from one merchant that the pipeline may still move."""
    rows = (
        db.query(Transaction)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Transaction.category_source != MANUAL,
            Transaction.is_split.is_(False),
            Transaction.split_parent_id.is_(None),
            Transaction.original_merchant_name.ilike(f"%{key.split(' ')[0]}%"),
        )
    )
    return [t for t in rows if merchant_key(t.original_merchant_name) == key]
