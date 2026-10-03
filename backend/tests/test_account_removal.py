"""Disconnecting a bank and deleting an account: Plaid goes first, local
data goes second, and a Plaid failure leaves everything in place."""

from datetime import date

from app.api.deps import get_aggregator
from app.db.models import (
    ChatMessage,
    Goal,
    InsightLog,
    LinkedAccount,
    NetWorthSnapshot,
    Transaction,
    User,
)
from app.integrations.bank_aggregator import AggregatorAccount, AggregatorTransaction
from app.main import app
from app.services.crypto import decrypt_token
from app.services.goal_service import create_goal
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


def _second_bank() -> FakeAggregatorClient:
    return FakeAggregatorClient(
        accounts=[
            AggregatorAccount(
                aggregator_account_id="acc_savings",
                institution_name="Other Bank",
                account_type="savings",
                current_balance=1000.0,
                available_balance=1000.0,
            )
        ],
        transactions_by_account={
            "acc_savings": [
                AggregatorTransaction(
                    aggregator_transaction_id="txn_interest",
                    aggregator_account_id="acc_savings",
                    amount=5.0,
                    date=date(2026, 8, 2),
                    merchant_name=None,
                    raw_category=None,
                    is_pending=False,
                )
            ]
        },
    )


def _link_two_banks(db, user):
    sync_user_accounts(db, user.id, "token-one", aggregator=FakeAggregatorClient())
    sync_user_accounts(db, user.id, "token-two", aggregator=_second_bank())


def _use(aggregator):
    app.dependency_overrides[get_aggregator] = lambda: aggregator
    return aggregator


def _account_id(db, institution):
    return db.query(LinkedAccount).filter(LinkedAccount.institution_name == institution).first().id


def test_list_groups_accounts_by_bank_login(db, user, client):
    _link_two_banks(db, user)

    banks = client.get("/linked-accounts").json()

    assert sorted(b["institution_name"] for b in banks) == ["Fake Bank", "Other Bank"]
    fake_bank = next(b for b in banks if b["institution_name"] == "Fake Bank")
    assert len(fake_bank["accounts"]) == 2
    assert fake_bank["status"] == "active"
    assert "access_token" not in str(banks)


def test_disconnect_removes_the_login_at_plaid_and_its_local_data(db, user, client):
    _link_two_banks(db, user)
    aggregator = _use(FakeAggregatorClient())

    response = client.delete(f"/linked-accounts/{_account_id(db, 'Fake Bank')}")

    assert response.status_code == 204
    # One call for the whole two-account login, with its real token.
    assert aggregator.removed_tokens == ["token-one"]
    remaining = db.query(LinkedAccount).all()
    assert [a.institution_name for a in remaining] == ["Other Bank"]
    assert decrypt_token(remaining[0].access_token_ref) == "token-two"
    assert [t.aggregator_transaction_id for t in db.query(Transaction).all()] == ["txn_interest"]


def test_disconnect_recomputes_todays_net_worth_and_keeps_history(db, user, client):
    _link_two_banks(db, user)
    # A snapshot from a previous day must survive.
    db.add(NetWorthSnapshot(user_id=user.id, date=date(2026, 1, 1), total_assets=1, total_liabilities=0, net_worth=1))
    db.commit()
    _use(FakeAggregatorClient())

    client.delete(f"/linked-accounts/{_account_id(db, 'Fake Bank')}")

    db.expire_all()
    today = db.query(NetWorthSnapshot).filter(NetWorthSnapshot.date == date.today()).one()
    assert float(today.net_worth) == 1000.0  # only the savings account is left
    assert db.query(NetWorthSnapshot).filter(NetWorthSnapshot.date == date(2026, 1, 1)).count() == 1


def test_disconnecting_the_last_bank_clears_net_worth_history(db, user, client):
    sync_user_accounts(db, user.id, "token-one", aggregator=FakeAggregatorClient())
    _use(FakeAggregatorClient())

    client.delete(f"/linked-accounts/{_account_id(db, 'Fake Bank')}")

    assert db.query(LinkedAccount).count() == 0
    assert db.query(NetWorthSnapshot).count() == 0
    # The web app's onboarding gate keys off this being null.
    assert client.get("/dashboard/net-worth").json()["current"] is None


def test_plaid_failure_leaves_everything_in_place(db, user, client):
    _link_two_banks(db, user)
    _use(FakeAggregatorClient(fail_remove_for={"token-one"}))

    response = client.delete(f"/linked-accounts/{_account_id(db, 'Fake Bank')}")

    assert response.status_code == 502
    assert db.query(LinkedAccount).count() == 3
    assert db.query(Transaction).count() == 4


def test_cannot_disconnect_another_users_bank(db, user, client):
    other = User(email="other@example.com")
    db.add(other)
    db.commit()
    sync_user_accounts(db, other.id, "their-token", aggregator=FakeAggregatorClient())
    their_account = db.query(LinkedAccount).filter(LinkedAccount.user_id == other.id).first()
    aggregator = _use(FakeAggregatorClient())

    response = client.delete(f"/linked-accounts/{their_account.id}")

    assert response.status_code == 404
    assert aggregator.removed_tokens == []
    assert db.query(LinkedAccount).filter(LinkedAccount.user_id == other.id).count() == 2


def _give_password(db, user, password="hunter22"):
    from app.auth import hash_password

    user.password_hash = hash_password(password)
    db.commit()


def test_delete_account_requires_the_right_password(db, user, client):
    _give_password(db, user)
    aggregator = _use(FakeAggregatorClient())

    response = client.request("DELETE", "/auth/account", json={"password": "wrong-password"})

    assert response.status_code == 403
    assert aggregator.removed_tokens == []
    assert db.get(User, user.id) is not None


def test_delete_account_erases_everything_and_removes_every_bank(db, user, client):
    from uuid import uuid4

    user_id = user.id  # `user` is expired once its row is gone
    _give_password(db, user)
    _link_two_banks(db, user)
    create_goal(db, user.id, "save", target_amount=1000.0, target_date=date(2027, 1, 1))
    db.add(InsightLog(user_id=user.id, type="goal_drift", message="m", delivered_via="in_app"))
    db.add(ChatMessage(user_id=user.id, conversation_id=uuid4(), role="user", content="hi"))
    db.commit()
    # A second user's data must be untouched.
    other = User(email="other@example.com")
    db.add(other)
    db.commit()
    sync_user_accounts(db, other.id, "their-token", aggregator=FakeAggregatorClient())
    aggregator = _use(FakeAggregatorClient())

    response = client.request("DELETE", "/auth/account", json={"password": "hunter22"})

    assert response.status_code == 204
    assert sorted(aggregator.removed_tokens) == ["token-one", "token-two"]
    db.expire_all()
    assert db.get(User, user_id) is None
    for model in (LinkedAccount, NetWorthSnapshot, Goal, InsightLog, ChatMessage):
        assert db.query(model).filter(model.user_id == user_id).count() == 0
    assert db.query(Transaction).count() == 3  # only the other user's
    assert db.query(LinkedAccount).filter(LinkedAccount.user_id == other.id).count() == 2


def test_delete_account_keeps_everything_when_plaid_fails_and_retry_succeeds(db, user, client):
    user_id = user.id
    _give_password(db, user)
    _link_two_banks(db, user)
    _use(FakeAggregatorClient(fail_remove_for={"token-two"}))

    failed = client.request("DELETE", "/auth/account", json={"password": "hunter22"})

    assert failed.status_code == 502
    assert db.get(User, user_id) is not None
    assert db.query(LinkedAccount).count() == 3

    _use(FakeAggregatorClient())
    retried = client.request("DELETE", "/auth/account", json={"password": "hunter22"})

    assert retried.status_code == 204
    assert db.get(User, user_id) is None
