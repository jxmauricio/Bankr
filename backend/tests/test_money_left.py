"""Expected income for a window, including paydays still ahead."""

from datetime import date

from app.services.cash_flow_plan import _short_payer, dates_in_range


def test_biweekly_pay_hits_twice_in_november():
    days = dates_in_range(date(2026, 11, 7), "biweekly", date(2026, 11, 1), date(2026, 11, 30))
    assert days == [date(2026, 11, 7), date(2026, 11, 21)]


def test_payroll_memo_shortens_to_employer():
    assert _short_payer("Alarm.com-OSV PAYROLL328 260930 61OSV002K0h Theodore Alo") == "Alarm.com"


def test_custom_income_then_delete(client):
    empty = client.get("/dashboard/money-left").json()
    assert empty["income_total"] == 0
    assert empty["left"] == 0
    assert empty["window"] == "this_month"

    plan = client.put(
        "/dashboard/money-left/incomes",
        json={"name": "Freelance", "amount": 500, "cadence": "weekly"},
    ).json()
    row = next(i for i in plan["incomes"] if i["name"] == "Freelance")
    assert row["origin"] == "custom"
    assert row["occurrences"] >= 1
    assert plan["income_total"] == round(row["amount"] * row["occurrences"], 2)
    assert plan["left"] == plan["income_total"]

    skipped = client.put(
        "/dashboard/money-left/incomes",
        json={"id": row["id"], "name": "Freelance", "amount": 500, "cadence": "weekly", "included": False},
    ).json()
    assert skipped["income_total"] == 0

    gone = client.delete(f"/dashboard/money-left/incomes/{row['id']}").json()
    assert gone["incomes"] == []
    assert gone["left"] == 0
    assert gone["budgeted"] == 0
    assert gone["unbudgeted_spent"] == 0


def test_money_left_is_pay_minus_budget_minus_unbudgeted_spend(client, monkeypatch):
    from datetime import datetime, timezone

    from app.api.deps import get_aggregator
    from app.main import app
    from app.services import money_query
    from tests.fake_aggregator import FakeAggregatorClient

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    app.dependency_overrides[get_aggregator] = lambda: FakeAggregatorClient()
    client.post("/linked-accounts", json={"public_token": "public-fake-token"})

    none = client.get("/dashboard/money-left").json()
    assert none["spent"] == 165.50
    assert none["budgeted"] == 0
    assert none["unbudgeted_spent"] == 165.50
    assert none["left"] == round(none["income_total"] - 165.50, 2)

    client.post(
        "/goals",
        json={"type": "track_spending", "category": "Housing", "target_amount": 500, "window": "this_month"},
    )
    housing = client.get("/dashboard/money-left").json()
    assert housing["budgeted"] == 500
    assert housing["unbudgeted_spent"] == 165.50  # groceries + ramen, not housing
    assert housing["left"] == round(housing["income_total"] - 500 - 165.50, 2)

    client.post(
        "/goals",
        json={"type": "track_spending", "category": "Food & Dining", "target_amount": 200, "window": "this_month"},
    )
    food = client.get("/dashboard/money-left").json()
    assert food["budgeted"] == 700
    assert food["unbudgeted_spent"] == 0
    assert food["left"] == round(food["income_total"] - 700, 2)


def test_budget_groups_subscriptions_and_gyms(client, db, user, monkeypatch):
    from datetime import date, datetime, timezone

    from app.db.models import RecurringSeries
    from app.db.seed_categories import seed_default_categories
    from app.services import money_query
    from app.services.recurring_service import merchant_key

    monkeypatch.setattr(money_query, "_now", lambda: datetime(2026, 8, 20, 16, tzinfo=timezone.utc))
    cats = seed_default_categories(db)
    db.add_all(
        [
            RecurringSeries(
                user_id=user.id,
                merchant_key=merchant_key("Netflix"),
                direction="out",
                display_name="Netflix",
                category_id=cats["entertainment_and_recreation"].id,
                kind="subscription",
                cadence="monthly",
                typical_amount=15.49,
                last_amount=15.49,
                last_date=date(2026, 8, 5),
                next_expected_date=date(2026, 9, 5),
                occurrences=6,
                status="confirmed",
            ),
            RecurringSeries(
                user_id=user.id,
                merchant_key=merchant_key("Spotify"),
                direction="out",
                display_name="Spotify",
                category_id=cats["entertainment_and_recreation"].id,
                kind="subscription",
                cadence="monthly",
                typical_amount=12.99,
                last_amount=12.99,
                last_date=date(2026, 8, 2),
                next_expected_date=date(2026, 9, 2),
                occurrences=6,
                status="confirmed",
            ),
            RecurringSeries(
                user_id=user.id,
                merchant_key=merchant_key("Equinox"),
                direction="out",
                display_name="Equinox",
                category_id=cats["fitness"].id,
                kind="bill",
                cadence="monthly",
                typical_amount=60,
                last_amount=60,
                last_date=date(2026, 8, 1),
                next_expected_date=date(2026, 9, 1),
                occurrences=6,
                status="confirmed",
            ),
        ]
    )
    db.commit()

    plan = client.get("/dashboard/money-left").json()
    groups = {g["name"]: g for g in plan["recurring_groups"]}
    assert set(groups) == {"Subscriptions", "Fitness"}
    assert [v["name"] for v in groups["Subscriptions"]["vendors"]] == ["Netflix", "Spotify"]
    assert groups["Subscriptions"]["limit"] == 28.48
    assert [v["name"] for v in groups["Fitness"]["vendors"]] == ["Equinox"]
    assert groups["Fitness"]["limit"] == 60.0
    assert plan["budgeted"] == 88.48

    netflix = groups["Subscriptions"]["vendors"][0]["series_id"]
    client.patch(f"/recurring/{netflix}", json={"in_budget": False})
    after = client.get("/dashboard/money-left").json()
    grouped = {g["name"]: g for g in after["recurring_groups"]}
    assert [v["name"] for v in grouped["Subscriptions"]["vendors"]] == ["Spotify"]
    assert grouped["Subscriptions"]["limit"] == 12.99
    assert after["budgeted"] == 72.99
