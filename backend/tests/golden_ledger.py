"""A hand-authored ledger with hand-computed answers to the MVP questions.

Frozen "today" is Saturday 2026-09-19, so:
  this_week  = Mon Sep 14 – Sat Sep 19      last_week  = Mon Sep 7 – Sun Sep 13
  this_month = Sep 1 – 19                   last_month = Aug 1 – 31

Every figure in EXPECTED was added up by hand from the rows below -- not
computed by the code under test -- and each trap that would make a naive
sum disagree with the bank is called out inline.
"""

from datetime import date, datetime, timezone

from app.integrations.bank_aggregator import AggregatorAccount, AggregatorTransaction
from tests.fake_aggregator import FakeAggregatorClient

FROZEN_NOW = datetime(2026, 9, 19, 16, 0, tzinfo=timezone.utc)  # noon in New York

ACCOUNTS = [
    AggregatorAccount("chk", "Chase", "checking", 4200.00, 4150.00, name="Total Checking", mask="1111"),
    AggregatorAccount("sav", "Chase", "savings", 10000.00, 10000.00, name="Savings", mask="2222"),
    AggregatorAccount("cc", "Chase", "credit", 850.00, 4150.00, name="Sapphire", mask="3333"),
]


def _t(txn_id, account, day, amount, merchant, raw, pending=False):
    return AggregatorTransaction(
        aggregator_transaction_id=txn_id,
        aggregator_account_id=account,
        amount=amount,
        date=day,
        merchant_name=merchant,
        raw_category=raw,
        is_pending=pending,
    )


TRANSACTIONS = [
    # --- income -----------------------------------------------------------
    _t("pay-aug1", "chk", date(2026, 8, 1), 3000.00, "Employer Inc", "INCOME_WAGES"),
    _t("pay-aug15", "chk", date(2026, 8, 15), 3000.00, "Employer Inc", "INCOME_WAGES"),
    _t("pay-sep1", "chk", date(2026, 9, 1), 3000.00, "Employer Inc", "INCOME_WAGES"),
    _t("pay-sep15", "chk", date(2026, 9, 15), 3000.00, "Employer Inc", "INCOME_WAGES"),
    # Month boundary: Aug 31 is last month, not this month.
    _t("interest-aug", "sav", date(2026, 8, 31), 4.12, "Chase", "INCOME_INTEREST_EARNED"),
    # --- transfers: neither income nor spending ----------------------------
    # TRAP: moving $500 to savings is not spending, and arriving in savings
    # is not income.
    _t("xfer-out", "chk", date(2026, 9, 2), -500.00, "Transfer to Savings", "TRANSFER_OUT_SAVINGS"),
    _t("xfer-in", "sav", date(2026, 9, 2), 500.00, "Transfer from Checking", "TRANSFER_IN_SAVINGS"),
    # TRAP: paying the card is not spending -- the card purchases below
    # already are. Counting it would add $640 of phantom spend.
    _t("ccpay-out", "chk", date(2026, 9, 10), -640.00, "Chase Card Payment", "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"),
    # TRAP: Plaid sometimes tags the card side "other payment" rather than
    # "credit card payment" -- still the same transfer.
    _t("ccpay-in", "cc", date(2026, 9, 10), 640.00, "Payment Thank You", "LOAN_PAYMENTS_OTHER_PAYMENT"),
    # TRAP: a friend paying you back isn't income.
    _t("venmo-in", "chk", date(2026, 9, 12), 40.00, "Venmo", "TRANSFER_IN_ACCOUNT_TRANSFER"),
    # --- housing & utilities -------------------------------------------------
    _t("rent-aug", "chk", date(2026, 8, 1), -1800.00, "Greystar", "RENT_AND_UTILITIES_RENT"),
    _t("rent-sep", "chk", date(2026, 9, 1), -1800.00, "Greystar", "RENT_AND_UTILITIES_RENT"),
    # TRAP: the *gas bill* -- must never show up in "how much on gas".
    _t("pge-aug", "chk", date(2026, 8, 12), -85.00, "PG&E", "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY"),
    _t("pge-sep", "chk", date(2026, 9, 5), -90.00, "PG&E", "RENT_AND_UTILITIES_GAS_AND_ELECTRICITY"),
    # --- groceries -----------------------------------------------------------
    _t("groc-aug3", "cc", date(2026, 8, 3), -120.50, "Trader Joe's", "FOOD_AND_DRINK_GROCERIES"),
    _t("groc-aug18", "cc", date(2026, 8, 18), -95.25, "Safeway", "FOOD_AND_DRINK_GROCERIES"),
    _t("groc-aug25", "cc", date(2026, 8, 25), -60.00, "Trader Joe's", "FOOD_AND_DRINK_GROCERIES"),
    _t("groc-sep4", "cc", date(2026, 9, 4), -88.40, "Safeway", "FOOD_AND_DRINK_GROCERIES"),
    _t("groc-sep11", "cc", date(2026, 9, 11), -102.30, "Trader Joe's", "FOOD_AND_DRINK_GROCERIES"),
    _t("groc-sep18", "cc", date(2026, 9, 18), -45.10, "Whole Foods", "FOOD_AND_DRINK_GROCERIES", pending=True),
    # --- dining ----------------------------------------------------------------
    _t("din-aug20", "cc", date(2026, 8, 20), -60.00, "Nopa", "FOOD_AND_DRINK_RESTAURANT"),
    # Sunday Sep 6 is the week *before* last week.
    _t("din-sep6", "cc", date(2026, 9, 6), -25.00, "Tacolicious", "FOOD_AND_DRINK_RESTAURANT"),
    _t("din-sep7", "cc", date(2026, 9, 7), -42.00, "Ramen Spot", "FOOD_AND_DRINK_RESTAURANT"),
    _t("din-sep9", "cc", date(2026, 9, 9), -5.75, "Blue Bottle", "FOOD_AND_DRINK_COFFEE"),
    _t("din-sep12", "cc", date(2026, 9, 12), -12.40, "Chipotle", "FOOD_AND_DRINK_FAST_FOOD"),
    # TRAP: a refund nets against the spend, like on the card statement.
    _t("din-sep12-refund", "cc", date(2026, 9, 12), 10.00, "Ramen Spot", "FOOD_AND_DRINK_RESTAURANT"),
    _t("din-sep13", "cc", date(2026, 9, 13), -36.00, "Zeitgeist", "FOOD_AND_DRINK_BEER_WINE_AND_LIQUOR"),
    # Monday Sep 14 is *this* week.
    _t("din-sep14", "cc", date(2026, 9, 14), -18.00, "Souvla", "FOOD_AND_DRINK_RESTAURANT"),
    # --- car gas & getting around -------------------------------------------------
    _t("gas-aug5", "cc", date(2026, 8, 5), -48.20, "Shell", "TRANSPORTATION_GAS"),
    _t("gas-aug19", "cc", date(2026, 8, 19), -52.80, "Chevron", "TRANSPORTATION_GAS"),
    _t("gas-aug28", "cc", date(2026, 8, 28), -45.00, "Shell", "TRANSPORTATION_GAS"),
    _t("gas-sep8", "cc", date(2026, 9, 8), -50.00, "Shell", "TRANSPORTATION_GAS"),
    _t("uber-aug22", "cc", date(2026, 8, 22), -35.00, "Uber", "TRANSPORTATION_TAXIS_AND_RIDE_SHARES"),
    # TRAP: a flight is Travel, not Transportation.
    _t("flight-aug22", "cc", date(2026, 8, 22), -420.00, "United", "TRAVEL_FLIGHTS"),
    _t("flight-refund", "cc", date(2026, 8, 30), 120.00, "United", "TRAVEL_FLIGHTS"),
    # --- shopping ----------------------------------------------------------------
    _t("amzn-sep6", "cc", date(2026, 9, 6), -64.99, "Amazon", "GENERAL_MERCHANDISE_ONLINE_MARKETPLACES"),
]

EXPECTED = {
    # Q1: 4200 + 10000 - 850
    "net_worth": 13350.00,
    "total_assets": 14200.00,
    "total_liabilities": 850.00,
    # Q2 (Sep 1–19): paychecks only. Spend = rent 1800 + PG&E 90 +
    # groceries 235.80 + dining 129.15 + gas 50 + Amazon 64.99.
    "this_month_income": 6000.00,
    "this_month_spending": 2369.94,
    "this_month_net": 3630.06,
    # Q3: 88.40 + 102.30 + 45.10 (pending) vs 120.50 + 95.25 + 60.00;
    # same point last month (Aug 1–19) = 120.50 + 95.25.
    "groceries_this_month": 235.80,
    "groceries_this_month_pending": 45.10,
    "groceries_last_month": 275.75,
    "groceries_last_month_to_date": 215.75,
    # Q4 (Sep 7–13): 42 + 5.75 + 12.40 + 36 - 10 refund.
    "dining_last_week": 86.15,
    "dining_last_week_gross": 96.15,
    "dining_last_week_count": 5,
    # Q5 (Sep 1–19), biggest first; sums to this_month_spending. Dining =
    # 25 + 42 + 5.75 + 12.40 - 10 + 36 + 18.
    "this_month_by_category": [
        ("Rent & Housing", 1800.00),
        ("Groceries", 235.80),
        ("Dining", 129.15),
        ("Utilities", 90.00),
        ("Shopping", 64.99),
        ("Transportation", 50.00),
    ],
    # Q6 (Aug): 48.20 + 52.80 + 45.00 -- not the $85 PG&E gas bill, not Uber.
    "gas_last_month": 146.00,
    "transportation_last_month": 181.00,  # gas + Uber; flight excluded
    "travel_last_month": 300.00,  # 420 flight - 120 refund
}


def golden_aggregator() -> FakeAggregatorClient:
    by_account: dict[str, list[AggregatorTransaction]] = {}
    for txn in TRANSACTIONS:
        by_account.setdefault(txn.aggregator_account_id, []).append(txn)
    return FakeAggregatorClient(accounts=ACCOUNTS, transactions_by_account=by_account)
