"""Daily briefing: a short list of things worth a look today, each with a
one-tap fix (app/services/briefing_actions.py).

Same split as insights_job and the weekly recap: plain Python below decides
which items exist and writes their titles from the user's numbers; the model
only writes one optional line above them. If it can't be reached the
briefing is still saved, without that line.

Items come from detection Bankr already does, plus a duplicate-charge check:
  review        charges the pipeline couldn't place (Uncategorized), one per
                merchant, with the classifier's cached guess when there is one
  unusual       get_unusual_transactions' outliers
  duplicate     the same merchant and amount twice within a few days
  price_change  a confirmed subscription that went up or down
  renewal       a subscription billing in the next RENEWAL_REMINDER_DAYS days
  trial         a tiny charge from a known subscription merchant, the usual
                sign of a trial or intro offer

One briefing per user per day (their time zone), made on first ask like the
recap. What the user does about an item is kept by its key in
BriefingItemState, so a handled item never comes back on a later day.
"""

import json
import logging
from collections import defaultdict
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import tools
from app.agent.agent_client import build_agent_client
from app.config import settings
from app.db.models import (
    BriefingItemState,
    Category,
    DailyBriefing,
    InsightLog,
    LinkedAccount,
    MerchantCategoryGuess,
    RecurringSeries,
    Transaction,
)
from app.db.seed_categories import display_names
from app.services import categorization_service as categorization
from app.services import money_query as mq
from app.services import recurring_service as recurring
from app.services.category_classifier import merchant_key as classifier_key
from app.services.subscription_help import CANCEL_PAGES

logger = logging.getLogger(__name__)

_client = build_agent_client()

MAX_ITEMS = 8
# Duplicates: the same merchant and amount this many days apart or fewer,
# the later one in the last DUPLICATE_RECENT_DAYS. Small charges (two
# coffees) repeat honestly all the time, so they're left out.
DUPLICATE_WINDOW_DAYS = 3
DUPLICATE_RECENT_DAYS = 7
DUPLICATE_MIN_AMOUNT = 20.0
# Trials: a charge this small from a known subscription merchant, in the
# last TRIAL_RECENT_DAYS, with no bigger charge from them before it.
TRIAL_MAX_AMOUNT = 2.0
TRIAL_RECENT_DAYS = 14
# The review queue only reaches back this far; older rows are in Transactions.
REVIEW_LOOKBACK_DAYS = 60

# Most pressing first: money that may need to come back, then what's about
# to bill, then tidying up.
_ORDER = ["duplicate", "unusual", "renewal", "trial", "price_change", "review"]
ACTIONS = {
    "review": ["recategorize", "create_rule", "dismiss"],
    "unusual": ["mark_expected", "dismiss"],
    "duplicate": ["mark_expected", "dismiss"],
    "price_change": ["mark_expected", "dismiss"],
    "renewal": ["dismiss"],
    "trial": ["dismiss"],
}
# Items that come with a cancel page or an email to copy.
HAS_HELP = {"unusual", "duplicate", "price_change", "renewal", "trial"}


def _money(amount: float) -> str:
    return f"${abs(amount):,.2f}"


def _day(d: date) -> str:
    return f"{d:%b} {d.day}"


def _when(due: date, today: date) -> str:
    days = (due - today).days
    if days <= 0:
        return "today"
    if days == 1:
        return "tomorrow"
    return f"in {days} days"


def _item(key: str, type_: str, title: str, detail: str, **fields) -> dict:
    return {
        "key": key,
        "type": type_,
        "title": title,
        "detail": detail,
        "merchant": None,
        "amount": None,
        "date": None,
        "transaction_ids": [],
        "series_id": None,
        "suggestion": None,
        **fields,
        "actions": ACTIONS[type_],
        "has_help": type_ in HAS_HELP,
    }


def _user_rows(db: Session, user_id: UUID):
    return (
        db.query(Transaction)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(LinkedAccount.user_id == user_id)
    )


# --- detectors ---------------------------------------------------------------


def find_duplicate_charges(db: Session, user_id: UUID, today: date) -> list[dict]:
    """Pairs of posted spending charges with the same merchant and amount at
    most DUPLICATE_WINDOW_DAYS apart, the later one recent. Merchants with a
    recurring series are skipped: a weekly class billed on Monday and again
    on Thursday after a reschedule is still expected."""
    since = today - timedelta(days=DUPLICATE_RECENT_DAYS + DUPLICATE_WINDOW_DAYS)
    rows = (
        _user_rows(db, user_id)
        .filter(
            Transaction.date >= since,
            Transaction.amount <= -DUPLICATE_MIN_AMOUNT,
            Transaction.is_pending.is_(False),
            Transaction.split_parent_id.is_(None),
            *mq.counted_filters(),
        )
        .order_by(Transaction.date, Transaction.created_at)
        .all()
    )
    expected = recurring.recurring_merchant_keys(db, user_id)
    by_charge: dict[tuple[str, float], list[Transaction]] = defaultdict(list)
    for txn in rows:
        key = recurring.merchant_key(txn.original_merchant_name or txn.merchant_name)
        if key and key not in expected:
            by_charge[(key, round(float(txn.amount), 2))].append(txn)

    pairs = []
    for charges in by_charge.values():
        for earlier, later in zip(charges, charges[1:]):
            if (later.date - earlier.date).days <= DUPLICATE_WINDOW_DAYS and (today - later.date).days < DUPLICATE_RECENT_DAYS:
                pairs.append((earlier, later))
    return [
        {
            "transaction_ids": [str(a.id), str(b.id)],
            "merchant": b.merchant_name or "Unknown merchant",
            "amount": -float(b.amount),
            "dates": [a.date, b.date],
        }
        for a, b in pairs
    ]


def _review_items(db: Session, user_id: UUID, today: date) -> list[dict]:
    """The review queue (category_source "fallback"), one item per merchant,
    newest first. The classifier's cached guess for the merchant is the
    suggestion even when it was too unsure to apply on its own."""
    rows = (
        _user_rows(db, user_id)
        .filter(
            Transaction.category_source == categorization.FALLBACK,
            Transaction.date >= today - timedelta(days=REVIEW_LOOKBACK_DAYS),
            Transaction.is_split.is_(False),
        )
        .order_by(Transaction.date.desc(), Transaction.created_at.desc())
        .all()
    )
    by_merchant: dict[str, list[Transaction]] = {}
    for txn in rows:
        key = classifier_key(txn.original_merchant_name or txn.merchant_name)
        if key:
            by_merchant.setdefault(key, []).append(txn)
    if not by_merchant:
        return []

    guesses = {
        g.merchant_key: g
        for g in db.query(MerchantCategoryGuess).filter(MerchantCategoryGuess.merchant_key.in_(by_merchant))
    }
    hidden = categorization.hidden_categories(db, user_id)
    names = display_names(db, user_id)
    items = []
    for key, txns in by_merchant.items():
        newest = txns[0]
        merchant = newest.merchant_name or newest.original_merchant_name
        total = sum(abs(float(t.amount)) for t in txns)
        guess = guesses.get(key)
        suggestion = None
        if guess is not None and guess.category_id not in hidden:
            category = db.get(Category, guess.category_id)
            if category is not None and category.system_key != categorization.UNCATEGORIZED:
                suggestion = {
                    "category_id": str(category.id),
                    "category": names.get(category.id, category.name),
                    "source": "classifier",
                }
        count = f"{len(txns)} charges" if len(txns) > 1 else "1 charge"
        detail = f"{count}, {_money(total)} in all, since {_day(txns[-1].date)}."
        if suggestion:
            detail += f" Looks like {suggestion['category']}."
        items.append(
            _item(
                # Keyed to the newest row: dismissing it hides the merchant until another charge lands.
                f"review:{newest.id}",
                "review",
                f"Pick a category for {merchant}",
                detail,
                merchant=merchant,
                amount=round(total, 2),
                date=newest.date.isoformat(),
                transaction_ids=[str(t.id) for t in txns],
                suggestion=suggestion,
            )
        )
    return items


def _unusual_items(db: Session, user_id: UUID) -> list[dict]:
    items = []
    for t in tools.get_unusual_transactions(db, user_id).get("unusual_transactions", []):
        merchant = t["merchant_name"] or "Unknown merchant"
        items.append(
            _item(
                f"unusual:{t['transaction_id']}",
                "unusual",
                f"{merchant}: {_money(t['amount'])}, bigger than usual",
                f"Charged {_day(date.fromisoformat(t['date']))}. Far above what you usually spend in one go.",
                merchant=merchant,
                amount=abs(t["amount"]),
                date=t["date"],
                transaction_ids=[t["transaction_id"]],
            )
        )
    return items


def _duplicate_items(db: Session, user_id: UUID, today: date) -> list[dict]:
    items = []
    for d in find_duplicate_charges(db, user_id, today):
        first, second = d["dates"]
        items.append(
            _item(
                f"duplicate:{d['transaction_ids'][0]}:{d['transaction_ids'][1]}",
                "duplicate",
                f"{d['merchant']} charged {_money(d['amount'])} twice",
                f"On {_day(first)} and {_day(second)}. If it was one purchase, ask them to refund one.",
                merchant=d["merchant"],
                amount=d["amount"],
                date=second.isoformat(),
                transaction_ids=d["transaction_ids"],
                charges=[{"amount": d["amount"], "date": first.isoformat()}, {"amount": d["amount"], "date": second.isoformat()}],
            )
        )
    return items


def _subscription_items(db: Session, user_id: UUID, today: date) -> list[dict]:
    """Renewals coming up, and price changes not already said by a renewal."""
    horizon = today + timedelta(days=settings.renewal_reminder_days)
    renewing: set[UUID] = set()
    items = []
    subscriptions = (
        db.query(RecurringSeries)
        .filter(
            RecurringSeries.user_id == user_id,
            RecurringSeries.kind == "subscription",
            RecurringSeries.status != "dismissed",
        )
        .order_by(RecurringSeries.next_expected_date)
        .all()
    )
    for s in subscriptions:
        if not recurring.is_active(s, today) or s.next_expected_date > horizon:
            continue
        # A few days late is still coming; it's due "today".
        due = max(s.next_expected_date, today)
        detail = f"{_money(float(s.last_amount))} on {_day(due)}"
        changed = abs(float(s.last_amount) - float(s.typical_amount)) > recurring.PRICE_CHANGE_THRESHOLD * float(s.typical_amount)
        detail += f", up from {_money(float(s.typical_amount))}." if changed and s.last_amount > s.typical_amount else "."
        renewing.add(s.id)
        items.append(
            _item(
                f"renewal:{s.id}:{s.next_expected_date.isoformat()}",
                "renewal",
                f"{s.display_name} renews {_when(due, today)}",
                detail + " Still using it? Now's the time to cancel if not.",
                merchant=s.display_name,
                amount=float(s.last_amount),
                date=due.isoformat(),
                series_id=str(s.id),
            )
        )

    for s in recurring.price_changes(db, user_id):
        if s.id in renewing:
            continue
        went = "up" if s.last_amount > s.typical_amount else "down"
        items.append(
            _item(
                f"price_change:{s.id}:{s.last_date.isoformat()}",
                "price_change",
                f"{s.display_name} went {went} to {_money(float(s.last_amount))}",
                f"It was usually {_money(float(s.typical_amount))}. The new price was charged {_day(s.last_date)}.",
                merchant=s.display_name,
                amount=float(s.last_amount),
                date=s.last_date.isoformat(),
                series_id=str(s.id),
                previous_amount=float(s.typical_amount),
            )
        )
    return items


def _trial_items(db: Session, user_id: UUID, today: date) -> list[dict]:
    rows = (
        _user_rows(db, user_id)
        .filter(
            Transaction.date >= today - timedelta(days=TRIAL_RECENT_DAYS),
            Transaction.amount < 0,
            Transaction.amount > -TRIAL_MAX_AMOUNT,
            *mq.counted_filters(),
        )
        .all()
    )
    items = []
    for txn in rows:
        key = recurring.merchant_key(txn.original_merchant_name or txn.merchant_name)
        if key not in CANCEL_PAGES:
            continue
        paid_before = (
            _user_rows(db, user_id)
            .filter(Transaction.date <= txn.date, Transaction.amount <= -TRIAL_MAX_AMOUNT, Transaction.id != txn.id)
            .filter(Transaction.merchant_name.ilike(f"%{key.split(' ')[0]}%"))
            .count()
        )
        if paid_before:
            continue
        merchant = CANCEL_PAGES[key][0]
        items.append(
            _item(
                f"trial:{txn.id}",
                "trial",
                f"Possible {merchant} trial",
                f"A {_money(float(txn.amount))} charge on {_day(txn.date)} is how trials and intro offers usually start. "
                "Check when it turns into the full price.",
                merchant=merchant,
                amount=abs(float(txn.amount)),
                date=txn.date.isoformat(),
                transaction_ids=[str(txn.id)],
            )
        )
    return items


def handled_keys(db: Session, user_id: UUID) -> dict[str, str]:
    return dict(
        db.query(BriefingItemState.item_key, BriefingItemState.status).filter(BriefingItemState.user_id == user_id)
    )


def compute_items(db: Session, user_id: UUID, today: date) -> list[dict]:
    """Every open item for today, most pressing first, at most MAX_ITEMS."""
    found = [
        *_duplicate_items(db, user_id, today),
        *_unusual_items(db, user_id),
        *_subscription_items(db, user_id, today),
        *_trial_items(db, user_id, today),
        *_review_items(db, user_id, today),
    ]
    handled = handled_keys(db, user_id)
    # A doubled charge is often also an outlier; say it once, as the duplicate.
    in_duplicates = {tid for i in found if i["type"] == "duplicate" for tid in i["transaction_ids"]}
    items = [
        i
        for i in found
        if i["key"] not in handled and not (i["type"] == "unusual" and i["transaction_ids"][0] in in_duplicates)
    ]
    items.sort(key=lambda i: _ORDER.index(i["type"]))
    return items[:MAX_ITEMS]


# --- wording -----------------------------------------------------------------


def teaser_for(items: list[dict]) -> str:
    """The push / notification line: plain facts, no model. The most pressing
    item by name, then how many more."""
    if not items:
        return "Nothing needs you today."
    first = items[0]["title"]
    rest = len(items) - 1
    return f"{first}." + (f" Plus {rest} more to look at." if rest else "")


def _write_intro(items: list[dict]) -> str | None:
    try:
        return _client.complete(
            system=(
                "Write ONE short, friendly sentence (under 20 words) introducing the user's daily money briefing. "
                "Mention the most pressing item. Use only the facts given, with dollar signs. No markdown, no advice "
                "beyond what the items say, no greeting longer than one word."
            ),
            user_message=json.dumps([{"type": i["type"], "title": i["title"], "detail": i["detail"]} for i in items]),
        ).strip().split("\n")[0] or None
    except Exception:
        logger.exception("daily briefing intro failed")
        return None


# --- saving and reading ------------------------------------------------------


def _find(db: Session, user_id: UUID, day: date) -> DailyBriefing | None:
    return db.query(DailyBriefing).filter(DailyBriefing.user_id == user_id, DailyBriefing.day == day).one_or_none()


def get_or_create_briefing(db: Session, user_id: UUID, notify: bool = False) -> DailyBriefing:
    """Today's briefing, made now if there isn't one. `notify` also logs it
    as an unread notification when it has anything in it."""
    today = mq.today_for_user(db, user_id)
    briefing = _find(db, user_id, today)
    if briefing is None:
        items = compute_items(db, user_id, today)
        briefing = DailyBriefing(user_id=user_id, day=today, items=items, intro=_write_intro(items) if items else None)
        db.add(briefing)
        try:
            db.commit()
        except IntegrityError:
            # Two requests made the same day at once; keep the first.
            db.rollback()
            briefing = _find(db, user_id, today)
    if notify:
        log_notification(db, briefing)
    return briefing


def item_statuses(db: Session, briefing: DailyBriefing) -> dict[str, str]:
    """Each item's status now: open, or what the user did. A review item the
    user categorized somewhere else (Transactions, a rule) counts as done."""
    handled = handled_keys(db, briefing.user_id)
    still_queued = set()
    review_ids = [tid for i in briefing.items if i["type"] == "review" for tid in i["transaction_ids"]]
    if review_ids:
        still_queued = {
            str(tid)
            for (tid,) in db.query(Transaction.id).filter(
                Transaction.id.in_(review_ids), Transaction.category_source == categorization.FALLBACK
            )
        }
    statuses = {}
    for i in briefing.items:
        if i["key"] in handled:
            statuses[i["key"]] = handled[i["key"]]
        elif i["type"] == "review" and not still_queued.intersection(i["transaction_ids"]):
            statuses[i["key"]] = "done"
        else:
            statuses[i["key"]] = "open"
    return statuses


def briefing_dict(db: Session, briefing: DailyBriefing) -> dict:
    statuses = item_statuses(db, briefing)
    items = [{**i, "status": statuses[i["key"]]} for i in briefing.items]
    open_items = [i for i in items if i["status"] == "open"]
    notification = notification_for(db, briefing)
    return {
        "day": briefing.day.isoformat(),
        "intro": briefing.intro,
        "teaser": teaser_for(open_items),
        "items": items,
        "open_count": len(open_items),
        "read": notification is None or notification.read_at is not None,
        "created_at": briefing.created_at.isoformat(),
    }


def dedupe_key(day: date) -> str:
    return f"daily_briefing:{day.isoformat()}"


def notification_for(db: Session, briefing: DailyBriefing) -> InsightLog | None:
    return (
        db.query(InsightLog)
        .filter(InsightLog.user_id == briefing.user_id, InsightLog.dedupe_key == dedupe_key(briefing.day))
        .one_or_none()
    )


def log_notification(db: Session, briefing: DailyBriefing, delivered_via: str = "in_app") -> InsightLog | None:
    """The briefing's row in the notifications list, once per day and only
    when it has something in it. Returns the row when this call made it."""
    if not briefing.items or notification_for(db, briefing) is not None:
        return None
    log = InsightLog(
        user_id=briefing.user_id,
        type="daily_briefing",
        message=teaser_for(briefing.items),
        dedupe_key=dedupe_key(briefing.day),
        delivered_via=delivered_via,
    )
    db.add(log)
    db.commit()
    return log
