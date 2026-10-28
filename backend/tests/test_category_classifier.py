import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings, settings
from app.db.models import MerchantCategoryGuess, Rule, Transaction
from app.db.seed_categories import seed_default_categories
from app.integrations.bank_aggregator import AggregatorTransaction
from app.integrations.plaid_client import _to_aggregator_transaction
from app.integrations.web_search import SearchResult
from app.jobs import backfill_category_confidence as backfill
from app.services import sync_service
from app.services.category_classifier import (
    CATEGORY_DESCRIPTIONS,
    CategoryAnswer,
    JevCategoryClassifier,
    MerchantProfile,
    build_profile,
    category_choices,
    clean_bank_text,
    merchant_key,
)
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


class FakeClassifier:
    model = "fake"

    def __init__(self, answer="Food & Dining > Coffee Shops", confidence=0.95, fail=False):
        self.answer = answer
        self.confidence = confidence
        self.fail = fail
        self.calls = []
        self.choices = None

    def classify(self, profile, choices):
        self.calls.append(profile)
        self.choices = choices
        if self.fail:
            raise RuntimeError("jev is down")
        return CategoryAnswer(self.answer, self.confidence)


@pytest.fixture
def classifier(monkeypatch):
    fake = FakeClassifier()
    monkeypatch.setattr(sync_service, "get_classifier", lambda: fake)
    monkeypatch.setattr(backfill, "get_classifier", lambda: fake)
    return fake


def _txn(txn_id, amount=-6.0, *, merchant="Moongoat Greenhouse", raw="HOME_IMPROVEMENT_OTHER_HOME_IMPROVEMENT",
         confidence="LOW", account="acc_checking", **extra):
    return AggregatorTransaction(
        aggregator_transaction_id=txn_id,
        aggregator_account_id=account,
        amount=amount,
        date=date(2026, 10, 18),
        merchant_name=merchant,
        raw_category=raw,
        is_pending=False,
        category_confidence=confidence,
        payment_channel=extra.pop("payment_channel", "in store"),
        **extra,
    )


def _sync(db, user, *txns):
    aggregator = FakeAggregatorClient(transactions_by_account={"acc_checking": list(txns)})
    sync_user_accounts(db, user.id, "fake-token", aggregator=aggregator)
    return aggregator


def _category(db, txn_id):
    return db.query(Transaction).filter(Transaction.aggregator_transaction_id == txn_id).one().category.name


def test_low_confidence_expense_is_reclassified_and_confidence_stored(db, user, classifier):
    _sync(db, user, _txn("t1", original_description="SQ *MOONGOAT GREENHOUS", payment_processor="Square"))

    row = db.query(Transaction).one()
    assert row.aggregator_category_confidence == "LOW"
    assert row.category.name == "Coffee Shops"
    profile = classifier.calls[0]
    assert (profile.merchant_name, profile.amounts, profile.channel) == ("Moongoat Greenhouse", (6.0,), "in store")
    assert (profile.bank_description, profile.payment_processor) == ("SQ *MOONGOAT GREENHOUS", "Square")
    guess = db.query(MerchantCategoryGuess).one()
    assert (guess.merchant_key, guess.confidence) == ("moongoat greenhouse", 0.95)


def test_unsure_answer_is_cached_but_keeps_plaids_category(db, user, classifier):
    classifier.confidence = 0.6
    _sync(db, user, _txn("t1"))

    assert _category(db, "t1") == "Home Improvement"
    assert db.query(MerchantCategoryGuess).one().confidence == 0.6

    _sync(db, user, _txn("t2"))  # not asked again, and the cached answer still isn't trusted
    assert len(classifier.calls) == 1
    assert _category(db, "t2") == "Home Improvement"


def test_confident_rows_keep_plaids_mapping(db, user, classifier):
    _sync(db, user, _txn("t1", confidence="HIGH"), _txn("t2", confidence=None))

    assert classifier.calls == []
    assert {_category(db, "t1"), _category(db, "t2")} == {"Home Improvement"}


def test_income_transfers_cash_and_people_are_never_sent(db, user, classifier):
    # No merchant to look up: Plaid's tag is all there is to go on.
    _sync(
        db,
        user,
        _txn("pay", 2000.0, merchant="Employer", raw="INCOME_SALARY"),
        _txn("xfer", -500.0, merchant="Ally Savings", raw="TRANSFER_OUT_SAVINGS"),
        _txn("zelle", -500.0, merchant="Zelle", raw="TRANSFER_OUT_TRANSFER_OUT_FROM_APPS"),
        _txn("atm", -60.0, merchant="ATM Withdrawal", raw="TRANSFER_OUT_WITHDRAWAL"),
    )

    assert classifier.calls == []
    assert _category(db, "pay") == "Paychecks"
    assert _category(db, "xfer") == "Transfer"
    assert _category(db, "zelle") == "Miscellaneous"
    assert _category(db, "atm") == "Cash & ATM"


def test_choices_exclude_income_transfer_and_loan_payments(db, user, classifier):
    _sync(db, user, _txn("t1"))

    assert "Food & Dining > Coffee Shops" in classifier.choices
    assert "Shopping > Shopping" in classifier.choices
    labels = {label.split(" > ")[-1] for label in classifier.choices}
    assert not {"Paychecks", "Transfer", "Credit Card Payment", "Mortgage", "Loan Repayment", "Cash & ATM"} & labels
    assert not [label for label in classifier.choices if label.startswith("Business")]
    assert all(classifier.choices.values())  # every choice comes with a description


def test_one_call_per_merchant_and_cache_reused_on_later_syncs(db, user, classifier):
    _sync(db, user, _txn("t1"), _txn("t2"), _txn("t3", merchant="MOONGOAT  greenhouse"))
    assert len(classifier.calls) == 1
    assert {_category(db, t) for t in ("t1", "t2", "t3")} == {"Coffee Shops"}

    _sync(db, user, _txn("t4"))
    assert len(classifier.calls) == 1
    assert _category(db, "t4") == "Coffee Shops"


def test_classifier_failure_keeps_plaids_mapping(db, user, classifier):
    classifier.fail = True
    _sync(db, user, _txn("t1"))

    assert _category(db, "t1") == "Home Improvement"
    assert db.query(MerchantCategoryGuess).count() == 0


def test_answer_outside_the_choices_is_ignored(db, user, classifier):
    classifier.answer = "Groceries > Gelato"
    _sync(db, user, _txn("t1"))

    assert _category(db, "t1") == "Home Improvement"
    assert db.query(MerchantCategoryGuess).count() == 0


def test_user_rule_beats_the_classifier(db, user, classifier):
    merchandise = seed_default_categories(db)["general_shopping"]
    db.add(Rule(user_id=user.id, merchant_contains="moongoat", set_category_id=merchandise.id))
    db.commit()

    _sync(db, user, _txn("t1"))

    assert classifier.calls == []
    assert _category(db, "t1") == "Shopping"


def test_user_override_beats_the_classifier(db, user, classifier):
    _sync(db, user, _txn("t1", confidence="HIGH"))
    row = db.query(Transaction).one()
    row.category_source = "manual"
    db.commit()

    _sync(db, user, _txn("t1"))

    assert classifier.calls == []
    assert _category(db, "t1") == "Home Improvement"


def test_known_software_merchants_are_never_sent(db, user, classifier):
    _sync(db, user, _txn("t1", merchant="GitHub", raw="GENERAL_SERVICES_OTHER_GENERAL_SERVICES"))

    assert classifier.calls == []
    assert _category(db, "t1") == "Shopping"


def test_disabled_by_default(db, user, monkeypatch):
    # The code's default, not whatever a local .env turns on: with it on,
    # this would call the real Jev.
    assert Settings.model_fields["jev_categorization_enabled"].default is False
    monkeypatch.setattr(settings, "jev_categorization_enabled", False)
    _sync(db, user, _txn("t1"))

    row = db.query(Transaction).one()
    assert row.aggregator_category_confidence == "LOW"
    assert row.category.name == "Home Improvement"


def test_backfill_fills_confidence_and_reclassifies(db, user, monkeypatch):
    aggregator = _sync(db, user, _txn("t1", confidence=None))
    assert db.query(Transaction).one().aggregator_category_confidence is None

    fake = FakeClassifier()
    monkeypatch.setattr(backfill, "get_classifier", lambda: fake)
    aggregator.transactions_by_account = {"acc_checking": [_txn("t1")]}
    result = backfill.backfill_category_confidence(db, user.id, aggregator)

    row = db.query(Transaction).one()
    assert row.aggregator_category_confidence == "LOW"
    assert row.category.name == "Coffee Shops"
    assert result["recategorized_by_classifier"] == 1


def test_merchant_key_normalizes():
    assert merchant_key("  MOONGOAT   Greenhouse ") == "moongoat greenhouse"
    assert merchant_key("") is None
    assert merchant_key(None) is None


def test_category_choices_are_the_spending_categories(db):
    choices = category_choices(seed_default_categories(db))
    assert choices["Food & Dining > Coffee Shops"] == "coffee_shops"  # categories carry their group
    assert choices["Shopping > Shopping"] == "general_shopping"
    assert "Food & Dining" not in choices  # a group is never a choice
    # 53 spending categories, minus Business' 9, the 4 loans, Cash, Fun Money and Other's 3.
    assert len(choices) == 53 - 9 - 4 - 1 - 1 - 3


def test_every_choice_has_a_description(db):
    keys = set(category_choices(seed_default_categories(db)).values())
    assert keys <= set(CATEGORY_DESCRIPTIONS)


def _profile(**fields):
    base = dict(merchant_key="m", merchant_name="Moongoat Greenhouse", bank_description="SQ *MOONGOAT GREENHOUS",
                channel="in store", city=None, region=None, payment_processor="Square", amounts=(6.0, 13.5))
    return MerchantProfile(**{**base, **fields})


def test_in_store_query_uses_bank_text_and_yelp_but_never_a_made_up_city():
    assert _profile().search_queries() == [('"MOONGOAT GREENHOUS" yelp', "fast"), ("Moongoat Greenhouse", "basic")]


def test_in_store_query_adds_the_city_plaid_returned():
    profile = _profile(merchant_name="Hangar", bank_description="HANGAR 18 ORANGE", city="Orange", region="CA")
    assert profile.search_queries() == [('"HANGAR 18 ORANGE" Orange CA yelp', "fast"), ("Hangar Orange CA", "basic")]


def test_online_merchants_get_no_place_or_yelp():
    by_text = _profile(merchant_name="Obsidian", bank_description="OBSIDIAN.MD", channel="in store")
    by_channel = _profile(merchant_name="Bilt", bank_description="BILT CARD HOUSING", channel="online", city="Irvine")
    assert by_text.search_queries() == [('"OBSIDIAN.MD"', "fast"), ("Obsidian", "basic")]
    assert by_channel.search_queries()[0] == ('"BILT CARD HOUSING"', "fast")


def test_clean_bank_text_drops_terminal_prefixes_numbers_and_dates():
    assert clean_bank_text("TST*CARROT & DAIKON - GA") == "CARROT & DAIKON"
    assert clean_bank_text("PAR*LEE'S SANDWICHES") == "LEE'S SANDWICHES"
    assert clean_bank_text("HOMEGOODS # 0728") == "HOMEGOODS"
    assert clean_bank_text("HARDLOOP 09-09-26") == "HARDLOOP"
    assert clean_bank_text("BILT CARD HOUSING PPD ID: 1844372402") == "BILT CARD HOUSING"
    assert clean_bank_text(None) is None


def test_build_profile_sums_up_the_merchants_rows():
    rows = [
        _txn("a", -5.5, original_description="SQ *MOONGOAT GREENHOUS", payment_processor="Square"),
        _txn("b", -13.5, original_description="SQ *MOONGOAT GREENHOUS", location_city="Costa Mesa", location_region="CA"),
        _txn("c", 2.0),  # a refund isn't a purchase amount
    ]
    profile = build_profile("moongoat greenhouse", rows)
    assert profile.amounts == (5.5, 13.5)
    assert profile.place == "Costa Mesa CA"
    assert profile.state()["median_amount_usd"] == 9.5
    assert profile.state()["payment_processor"] == "Square"


class FakeSearch:
    def __init__(self, results):
        self.results = results
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        return self.results


def _jev(same_business_scores, choice="Food & Drink > Coffee", confidence=0.97):
    """A JevCategoryClassifier against a fake Decisions API: the noul
    (same-business) answers come back in order, then the choice."""
    sent = []
    scores = iter(same_business_scores)

    def handler(request):
        body = json.loads(request.content)
        sent.append(body)
        question = body["questions"]["q"]
        if question["type"] == "noul":
            return httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": next(scores)}}})
        return httpx.Response(200, json={"answers": {"q": {"type": "choice", "choice": choice, "confidence": confidence}}})

    fast = FakeSearch([SearchResult("Hangar 24 Brewing", "u", "A craft brewery")])
    basic = FakeSearch([SearchResult("Moongoat Greenhouse", "u", "Coffee shop in Costa Mesa")])
    jev = JevCategoryClassifier("key", "typesafe/jev-1.13", http=httpx.Client(transport=httpx.MockTransport(handler)),
                                searches={"fast": fast, "basic": basic})
    return jev, sent, fast, basic


def test_jev_retries_when_the_first_search_found_another_business():
    jev, sent, fast, basic = _jev([0.1, 0.9])

    answer = jev.classify(_profile(), {"Food & Drink > Coffee": "Cafes", "Shopping": "Retail"})

    assert answer == CategoryAnswer("Food & Drink > Coffee", 0.97)
    assert fast.queries == ['"MOONGOAT GREENHOUS" yelp'] and basic.queries == ["Moongoat Greenhouse"]
    choice_state = sent[-1]["state"]
    assert "Coffee shop in Costa Mesa" in choice_state["web_search_results"]
    assert "Brewing" not in choice_state["web_search_results"]
    assert sent[-1]["questions"]["q"]["criteria"] == {"Food & Drink > Coffee": "Cafes", "Shopping": "Retail"}


def test_jev_drops_search_results_that_never_match():
    jev, sent, _, _ = _jev([0.1, 0.2])

    jev.classify(_profile(), {"Food & Drink > Coffee": "Cafes"})

    assert "web_search_results" not in sent[-1]["state"]
    assert sent[-1]["state"]["bank_description"] == "SQ *MOONGOAT GREENHOUS"


def test_plaid_transaction_carries_bank_text_location_and_terminal():
    plaid_txn = SimpleNamespace(
        transaction_id="t", account_id="a", amount=6.0, date=date(2026, 10, 24), merchant_name="Moongoat Greenhouse",
        name="MOONGOAT GREENHOUS", personal_finance_category=SimpleNamespace(detailed="X", confidence_level="LOW"),
        category=None, pending=False,
        get=lambda key, default=None: {
            "original_description": "SQ *MOONGOAT GREENHOUS",
            "location": SimpleNamespace(city="Costa Mesa", region="CA"),
            "payment_meta": SimpleNamespace(payment_processor=None),
            "counterparties": [SimpleNamespace(type="payment_terminal", name="Square")],
            "payment_channel": "in store",
        }.get(key, default),
    )
    txn = _to_aggregator_transaction(plaid_txn)
    assert (txn.original_description, txn.location_city, txn.location_region) == ("SQ *MOONGOAT GREENHOUS", "Costa Mesa", "CA")
    assert (txn.payment_processor, txn.category_confidence) == ("Square", "LOW")
