"""Daily briefing: the duplicate detector, which items a briefing holds and
in what order, the one-tap fixes (preview, then confirm), and the cancel
links and emails behind subscription items."""

from datetime import date, datetime, time, timedelta, timezone

import pytest

from app.db.models import (
    BriefingItemState,
    DailyBriefing,
    InsightLog,
    MerchantCancelLink,
    MerchantCategoryGuess,
    RecurringSeries,
    Rule,
    Transaction,
)
from app.db.seed_categories import seed_default_categories
from app.integrations.bank_aggregator import AggregatorTransaction
from app.integrations.web_search import SearchResult
from app.jobs import daily_briefing_job as job
from app.services import briefing_actions as actions
from app.services import money_query as mq
from app.services.recurring_service import add_months, detect_recurring
from app.services.sync_service import sync_user_accounts
from tests.fake_agent_client import FakeAgentClient
from tests.fake_aggregator import FakeAggregatorClient
from tests.fake_web_search import FakeWebSearchClient

# get_unusual_transactions reads the real date, so "today" is the real one.
TODAY = date.today()
NOW = datetime.combine(TODAY, time(16), tzinfo=timezone.utc)  # noon in New York


@pytest.fixture(autouse=True)
def _frozen(monkeypatch):
    monkeypatch.setattr(mq, "_now", lambda: NOW)
    monkeypatch.setattr(job, "_client", FakeAgentClient(completions=["Two things to look at today."] * 5))


def _t(txn_id, days_ago, amount, merchant, raw="GENERAL_MERCHANDISE_OTHER_GENERAL_MERCHANDISE"):
    return AggregatorTransaction(txn_id, "acc_checking", amount, TODAY - timedelta(days=days_ago), merchant, raw, False)


def _everyday(n=10):
    """Ordinary small spending, so one big charge stands out."""
    return [_t(f"day{i}", 3 + i * 5, -20.0 - i, "Corner Store", "GENERAL_MERCHANDISE_SUPERSTORES") for i in range(n)]


def _sync(db, user, *txns):
    sync_user_accounts(
        db, user.id, "fake-token", aggregator=FakeAggregatorClient(transactions_by_account={"acc_checking": list(txns)})
    )


def _row(db, txn_id) -> Transaction:
    return db.query(Transaction).filter(Transaction.aggregator_transaction_id == txn_id).one()


def _keys(items):
    return [i["key"] for i in items]


# --- duplicate detector ------------------------------------------------------


def test_duplicate_is_same_merchant_and_amount_within_a_few_days(db, user):
    _sync(
        db,
        user,
        _t("tix1", 4, -86.50, "Ticketmaster"),
        _t("tix2", 2, -86.50, "Ticketmaster"),
        # Small repeats are everyday life, not duplicates.
        _t("cof1", 2, -5.25, "Blue Bottle"),
        _t("cof2", 1, -5.25, "Blue Bottle"),
        # Too far apart.
        _t("shoe1", 6, -120.0, "Nike"),
        _t("shoe2", 1, -120.0, "Nike"),
        # Different amounts.
        _t("gas1", 2, -41.0, "Shell"),
        _t("gas2", 1, -38.0, "Shell"),
    )
    found = job.find_duplicate_charges(db, user.id, TODAY)
    assert [(d["merchant"], d["amount"]) for d in found] == [("Ticketmaster", 86.50)]
    assert found[0]["transaction_ids"] == [str(_row(db, "tix1").id), str(_row(db, "tix2").id)]


def test_duplicate_skips_old_pairs_pending_rows_and_recurring_merchants(db, user):
    gym = [_t(f"gym{i}", i * 30, -60.0, "Equinox") for i in range(4)]
    _sync(
        db,
        user,
        *gym,
        _t("gym-extra", 2, -60.0, "Equinox"),  # a recurring merchant billing twice is its business
        _t("old1", 30, -75.0, "Target"),
        _t("old2", 29, -75.0, "Target"),
        AggregatorTransaction("pend", "acc_checking", -99.0, TODAY, "Amazon", None, True),
        _t("posted", 1, -99.0, "Amazon"),
    )
    detect_recurring(db, user.id)
    assert db.query(RecurringSeries).filter(RecurringSeries.merchant_key == "equinox").count() == 1
    assert job.find_duplicate_charges(db, user.id, TODAY) == []


# --- assembly ----------------------------------------------------------------


def _subscription(db, user, name, last_amount, typical, next_in_days, status="confirmed"):
    series = RecurringSeries(
        user_id=user.id,
        merchant_key=name.lower(),
        direction="out",
        display_name=name,
        kind="subscription",
        cadence="monthly",
        typical_amount=typical,
        last_amount=last_amount,
        last_date=add_months(TODAY + timedelta(days=next_in_days), -1),
        next_expected_date=TODAY + timedelta(days=next_in_days),
        occurrences=5,
        status=status,
    )
    db.add(series)
    db.commit()
    return series


def test_briefing_items_come_from_every_detector_most_pressing_first(db, user):
    categories = seed_default_categories(db)
    _sync(
        db,
        user,
        *_everyday(),
        _t("big", 1, -950.0, "Apple Store"),
        _t("dup1", 3, -64.0, "Uber Eats"),
        _t("dup2", 1, -64.0, "Uber Eats"),
        _t("mystery1", 2, -18.0, "SQ *KOVA CAFE", None),
        _t("mystery2", 9, -12.0, "SQ *KOVA CAFE", None),
        _t("trial", 1, -1.00, "Hulu"),
    )
    db.add(MerchantCategoryGuess(merchant_key="sq *kova cafe", category_id=categories["coffee_shops"].id, source="jev", model="t", confidence=0.6))
    db.commit()
    netflix = _subscription(db, user, "Netflix", 22.99, 15.49, next_in_days=2)
    spotify = _subscription(db, user, "Spotify", 13.99, 11.99, next_in_days=20)
    _subscription(db, user, "Far Away", 9.99, 9.99, next_in_days=20)

    items = job.compute_items(db, user.id, TODAY)

    assert [i["type"] for i in items] == ["duplicate", "unusual", "renewal", "trial", "price_change", "review"]
    dup, unusual, renewal, trial, price, review = items
    assert dup["title"] == "Uber Eats charged $64.00 twice"
    assert unusual["title"] == "Apple Store: $950.00, bigger than usual"
    assert renewal["key"] == f"renewal:{netflix.id}:{netflix.next_expected_date.isoformat()}"
    assert renewal["title"] == "Netflix renews in 2 days"
    assert renewal["detail"].startswith("$22.99 on ") and "up from $15.49" in renewal["detail"]
    assert trial["title"] == "Possible Hulu trial"
    assert price["title"] == "Spotify went up to $13.99" and price["series_id"] == str(spotify.id)
    # Both mystery charges are one item, with the classifier's (unsure) guess offered.
    assert review["title"] == "Pick a category for SQ *KOVA CAFE"
    assert len(review["transaction_ids"]) == 2 and review["amount"] == 30.0
    assert review["suggestion"]["category"] == "Coffee Shops"
    assert review["actions"] == ["recategorize", "create_rule", "dismiss"]


def test_a_duplicate_that_is_also_an_outlier_is_said_once(db, user):
    _sync(db, user, *_everyday(), _t("d1", 2, -900.0, "Delta"), _t("d2", 1, -900.0, "Delta"))
    items = job.compute_items(db, user.id, TODAY)
    assert [i["type"] for i in items] == ["duplicate"]


def test_handled_items_never_come_back(db, user):
    _sync(db, user, _t("m", 1, -9.0, "SQ *MYSTERY", None))
    key = job.compute_items(db, user.id, TODAY)[0]["key"]
    db.add(BriefingItemState(user_id=user.id, item_key=key, status="dismissed"))
    db.commit()
    assert job.compute_items(db, user.id, TODAY) == []


def test_one_briefing_per_day_and_the_model_writes_only_the_intro(db, user, monkeypatch):
    _sync(db, user, _t("m", 1, -9.0, "SQ *MYSTERY", None))
    fake = FakeAgentClient(completions=["One charge needs a category.\nIgnored second line."])
    monkeypatch.setattr(job, "_client", fake)

    first = job.get_or_create_briefing(db, user.id, notify=True)
    again = job.get_or_create_briefing(db, user.id, notify=True)

    assert first.id == again.id and first.day == TODAY
    assert first.intro == "One charge needs a category."
    log = db.query(InsightLog).filter(InsightLog.type == "daily_briefing").one()
    assert log.message == "Pick a category for SQ *MYSTERY."
    assert log.dedupe_key == f"daily_briefing:{TODAY.isoformat()}"


def test_briefing_without_the_model_and_with_nothing_to_say(db, user, monkeypatch):
    class Down:
        def complete(self, system, user_message):
            raise RuntimeError("no provider")

    monkeypatch.setattr(job, "_client", Down())
    _sync(db, user, _t("m", 1, -9.0, "SQ *MYSTERY", None))
    assert job.get_or_create_briefing(db, user.id).intro is None

    other = _other_user(db)
    empty = job.get_or_create_briefing(db, other.id, notify=True)
    assert empty.items == [] and empty.intro is None
    assert db.query(InsightLog).filter(InsightLog.user_id == other.id).count() == 0


def _other_user(db):
    from uuid import uuid4

    from app.db.models import User

    u = User(email=f"{uuid4()}@example.com")
    db.add(u)
    db.commit()
    return u


def test_a_review_item_fixed_elsewhere_shows_as_done(client, db, user):
    categories = seed_default_categories(db)
    _sync(db, user, _t("m", 1, -9.0, "SQ *MYSTERY", None))
    job.get_or_create_briefing(db, user.id)

    client.patch(f"/transactions/{_row(db, 'm').id}", json={"category_id": str(categories["groceries"].id)})

    briefing = client.get("/briefing/today").json()["briefing"]
    assert briefing["items"][0]["status"] == "done"
    assert briefing["open_count"] == 0 and briefing["teaser"] == "Nothing needs you today."


# --- actions -----------------------------------------------------------------


def _act(client, key, action, confirm, **extra):
    return client.post("/briefing/actions", json={"item_key": key, "action": action, "confirm": confirm, **extra})


def test_recategorize_previews_then_applies_the_suggestion(client, db, user):
    categories = seed_default_categories(db)
    _sync(db, user, _t("a", 1, -9.0, "SQ *KOVA CAFE", None), _t("b", 8, -7.0, "SQ *KOVA CAFE", None))
    db.add(MerchantCategoryGuess(merchant_key="sq *kova cafe", category_id=categories["coffee_shops"].id, source="jev", model="t", confidence=0.5))
    db.commit()
    key = client.get("/briefing/today").json()["briefing"]["items"][0]["key"]

    preview = _act(client, key, "recategorize", False)
    assert preview.status_code == 200
    assert preview.json() == {"summary": "Move 2 charges from SQ *KOVA CAFE to Coffee Shops.", "applied": False, "category": "Coffee Shops"}
    assert _row(db, "a").category_source == "fallback"

    done = _act(client, key, "recategorize", True).json()
    assert done["summary"] == "Moved 2 charges from SQ *KOVA CAFE to Coffee Shops."
    db.expire_all()
    for txn_id in ("a", "b"):
        assert (_row(db, txn_id).bankr_category_id, _row(db, txn_id).category_source) == (categories["coffee_shops"].id, "manual")
    assert done["briefing"]["items"][0]["status"] == "done"


def test_create_rule_from_a_review_item(client, db, user):
    categories = seed_default_categories(db)
    _sync(db, user, _t("a", 1, -9.0, "SQ *MYSTERY", None), _t("b", 40, -9.0, "SQ *MYSTERY", None))
    key = client.get("/briefing/today").json()["briefing"]["items"][0]["key"]
    groceries = str(categories["groceries"].id)

    preview = _act(client, key, "create_rule", False, category_id=groceries).json()
    assert preview["would_change"] == 2
    assert db.query(Rule).count() == 0

    done = _act(client, key, "create_rule", True, category_id=groceries).json()
    assert done["applied_to"] == 2
    rule = db.query(Rule).one()
    assert (rule.merchant_contains, rule.set_category_id) == ("SQ *MYSTERY", categories["groceries"].id)
    db.expire_all()
    assert _row(db, "b").category_source == "rule"


def test_mark_expected_and_dismiss_are_remembered(client, db, user):
    _sync(db, user, *_everyday(), _t("big", 1, -950.0, "Apple Store"), _t("m", 1, -9.0, "SQ *MYSTERY", None))
    items = client.get("/briefing/today").json()["briefing"]["items"]
    unusual, review = items

    assert "won't flag it again" in _act(client, unusual["key"], "mark_expected", False).json()["summary"]
    assert db.query(BriefingItemState).count() == 0
    _act(client, unusual["key"], "mark_expected", True)
    _act(client, review["key"], "dismiss", True)

    states = dict(db.query(BriefingItemState.item_key, BriefingItemState.status))
    assert states == {unusual["key"]: "expected", review["key"]: "dismissed"}
    # Tomorrow's briefing leaves them out.
    assert job.compute_items(db, user.id, TODAY + timedelta(days=1)) == []


def test_actions_are_checked(client, db, user):
    _sync(db, user, *_everyday(), _t("big", 1, -950.0, "Apple Store"))
    key = client.get("/briefing/today").json()["briefing"]["items"][0]["key"]

    assert _act(client, key, "recategorize", True).status_code == 422  # not an action an unusual charge has
    assert _act(client, "unusual:nope", "dismiss", True).status_code == 404
    review_key = "review:x"
    assert _act(client, review_key, "dismiss", True).status_code == 404


def test_actions_only_reach_the_users_own_items(client, db, user):
    other = _other_user(db)
    db.add(DailyBriefing(user_id=other.id, day=TODAY, items=[job._item("unusual:theirs", "unusual", "t", "d", merchant="X")]))
    db.commit()
    assert _act(client, "unusual:theirs", "dismiss", True).status_code == 404


# --- cancel links and emails -------------------------------------------------


def test_help_for_a_renewal_has_the_curated_cancel_page_and_an_email(client, db, user):
    _subscription(db, user, "Netflix", 15.49, 15.49, next_in_days=1)
    key = client.get("/briefing/today").json()["briefing"]["items"][0]["key"]

    out = client.get("/briefing/help", params={"item_key": key}).json()

    assert out["cancel"] == {"url": "https://www.netflix.com/cancelplan", "title": "Manage your Netflix subscription", "source": "curated"}
    [email] = out["emails"]
    assert email["subject"] == "Cancel my Netflix subscription"
    assert "$15.49" in email["body"] and "[Your name]" in email["body"]


def test_unknown_merchants_are_searched_once_and_cached(db, user, monkeypatch):
    _subscription(db, user, "Kova Coffee Club", 30.0, 30.0, next_in_days=1)
    job.get_or_create_briefing(db, user.id)
    key = job.compute_items(db, user.id, TODAY)[0]["key"]
    search = FakeWebSearchClient(
        [
            SearchResult("Reddit thread", "https://www.reddit.com/r/x", "..."),
            SearchResult("Cancel your membership", "https://kova.example/account/cancel", "..."),
        ]
    )

    first = actions.item_help(db, user.id, key, search)
    second = actions.item_help(db, user.id, key, search)

    assert first["cancel"] == {"url": "https://kova.example/account/cancel", "title": "Cancel your membership", "source": "search"}
    assert second["cancel"] == first["cancel"]
    assert search.queries == ["how to cancel kova coffee club subscription"]
    assert db.query(MerchantCancelLink).one().merchant_key == "kova coffee club"


def test_refund_email_for_a_duplicate_lists_both_charges(db, user):
    _sync(db, user, _t("dup1", 3, -64.0, "Uber Eats"), _t("dup2", 1, -64.0, "Uber Eats"))
    job.get_or_create_briefing(db, user.id)
    key = job.compute_items(db, user.id, TODAY)[0]["key"]

    out = actions.item_help(db, user.id, key, None)

    assert out["cancel"] is None
    [email] = out["emails"]
    assert email["subject"] == "Refund request: Uber Eats charge"
    assert email["body"].count("- $64.00 on ") == 2
    assert "refund the duplicate charge of $64.00" in email["body"]


# --- chat --------------------------------------------------------------------


def test_agent_tool_returns_the_open_items(db, user):
    from app.agent import tools

    _sync(db, user, _t("m", 1, -9.0, "SQ *MYSTERY", None))
    result = tools.get_daily_briefing(db, user.id)
    assert [i["title"] for i in result["open_items"]] == ["Pick a category for SQ *MYSTERY"]
    assert result["handled_count"] == 0 and "data_as_of" in result
