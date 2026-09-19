"""PlaidClient.sync_transactions against a stubbed Plaid API: it must drain
every page (the old /transactions/get call silently stopped at 100 rows)
and restart from the original cursor if Plaid reports a mid-pagination
mutation, per Plaid's /transactions/sync docs."""

import json
from datetime import date
from types import SimpleNamespace

import plaid
import pytest

from app.integrations import plaid_client


def _plaid_txn(txn_id, amount=12.5, pending_id=None):
    return SimpleNamespace(
        transaction_id=txn_id,
        account_id="acc",
        amount=amount,  # Plaid: positive = money out
        date=date(2026, 9, 1),
        merchant_name="Shell",
        name="SHELL OIL 123",
        personal_finance_category=SimpleNamespace(detailed="TRANSPORTATION_GAS"),
        category=None,
        pending=False,
        get=lambda key, default=None, _p=pending_id: _p if key == "pending_transaction_id" else default,
    )


def _page(added, next_cursor, has_more, removed=()):
    return SimpleNamespace(
        added=added,
        modified=[],
        removed=[SimpleNamespace(transaction_id=r) for r in removed],
        next_cursor=next_cursor,
        has_more=has_more,
    )


class _StubApi:
    def __init__(self, responses):
        self.responses = list(responses)
        self.cursors = []
        self.options_seen = []

    def transactions_sync(self, request):
        self.cursors.append(request.get("cursor"))
        self.options_seen.append(request.get("options"))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _mutation_error():
    error = plaid.ApiException(status=400, reason="Bad Request")
    error.body = json.dumps({"error_code": "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"})
    return error


def test_drains_every_page(monkeypatch):
    pages = [
        _page([_plaid_txn(f"t{i}") for i in range(500)], "c1", True),
        _page([_plaid_txn(f"t{i}") for i in range(500, 700)], "c2", True, removed=["old-pending"]),
        _page([], "c3", False),
    ]
    api = _StubApi(pages)
    monkeypatch.setattr(plaid_client, "_client", lambda: api)

    result = plaid_client.PlaidClient().sync_transactions("access", None)

    assert len(result.added) == 700
    assert result.removed_ids == ["old-pending"]
    assert result.next_cursor == "c3"
    assert api.cursors == [None, "c1", "c2"]
    first = result.added[0]
    assert first.amount == -12.5  # flipped to Bankr's money-in-positive convention
    assert first.raw_category == "TRANSPORTATION_GAS"

    # PFCv2 requested explicitly on every page -- category_mapper.py's
    # taxonomy is verified against v2 specifically, not v1.
    for options in api.options_seen:
        assert options.include_personal_finance_category is True
        assert str(options.personal_finance_category_version) == "v2"


def test_restarts_from_the_original_cursor_on_mutation(monkeypatch):
    api = _StubApi(
        [
            _page([_plaid_txn("stale")], "c1", True),
            _mutation_error(),
            _page([_plaid_txn("fresh")], "c9", False),
        ]
    )
    monkeypatch.setattr(plaid_client, "_client", lambda: api)

    result = plaid_client.PlaidClient().sync_transactions("access", "c0")

    assert [t.aggregator_transaction_id for t in result.added] == ["fresh"]  # stale page discarded
    assert api.cursors == ["c0", "c1", "c0"]
    assert result.next_cursor == "c9"


def test_other_plaid_errors_propagate(monkeypatch):
    error = plaid.ApiException(status=400, reason="Bad Request")
    error.body = json.dumps({"error_code": "ITEM_LOGIN_REQUIRED"})
    monkeypatch.setattr(plaid_client, "_client", lambda: _StubApi([error]))

    with pytest.raises(plaid.ApiException):
        plaid_client.PlaidClient().sync_transactions("access", None)
