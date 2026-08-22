"""Shared FastAPI dependency providers.

get_aggregator is its own function (rather than instantiating PlaidClient()
inline in route handlers) so tests can override it with a fake adapter via
app.dependency_overrides, without hitting Plaid's API. It's also the reason
swapping aggregators (originally Teller, now Plaid, after Teller shut down
its API in July 2026) touched only this file and one new adapter module.
"""

from app.integrations.bank_aggregator import BankAggregatorClient
from app.integrations.plaid_client import PlaidClient


def get_aggregator() -> BankAggregatorClient:
    return PlaidClient()
