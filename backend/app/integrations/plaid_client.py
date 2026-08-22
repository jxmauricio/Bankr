"""Plaid adapter: implements BankAggregatorClient against Plaid's API.

Plaid's linking flow differs from Teller's (the aggregator this app
originally ran on, before it shut down its API in July 2026): there is a
server-side token exchange step, not just an on-device Connect flow.

  1. Backend calls create_link_token() so the iOS Plaid Link SDK can launch
     Plaid's hosted bank-login UI.
  2. Link returns a public_token to the client, which posts it to
     POST /linked-accounts.
  3. Backend exchanges it for a durable access_token via
     exchange_public_token() -- only the backend ever holds the access_token,
     matching the "never touches the client" rule from the original design.

Field names below are verified against the installed plaid-python==42.0.0
SDK's request/response model classes, not assumed from memory.
"""

from datetime import date, timedelta

import plaid
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

from app.config import settings
from app.integrations.bank_aggregator import AggregatorAccount, AggregatorTransaction

_PLAID_HOSTS = {
    "sandbox": plaid.Environment.Sandbox,
    "production": plaid.Environment.Production,
}


def _client() -> plaid_api.PlaidApi:
    configuration = plaid.Configuration(
        host=_PLAID_HOSTS.get(settings.plaid_env, plaid.Environment.Sandbox),
        api_key={"clientId": settings.plaid_client_id, "secret": settings.plaid_secret},
    )
    return plaid_api.PlaidApi(plaid.ApiClient(configuration))


def _map_account_type(plaid_type: str, plaid_subtype: str | None) -> str:
    """Plaid's top-level `type` is depository/credit/loan/investment/other --
    checking vs. savings only shows up in `subtype`. Normalize so
    sync_service.py's LIABILITY_ACCOUNT_TYPES ({"credit", "loan"}) still
    matches correctly."""
    if plaid_type == "depository":
        return plaid_subtype or "checking"
    return plaid_type


class PlaidClient:
    def create_link_token(self, user_id: str) -> str:
        client = _client()
        request = LinkTokenCreateRequest(
            client_name="Bankr",
            language="en",
            country_codes=[CountryCode("US")],
            products=[Products("transactions")],
            user=LinkTokenCreateRequestUser(client_user_id=user_id),
        )
        response = client.link_token_create(request)
        return response.link_token

    def exchange_public_token(self, public_token: str) -> str:
        client = _client()
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(request)
        return response.access_token

    def list_accounts(self, access_token: str) -> list[AggregatorAccount]:
        client = _client()
        response = client.accounts_get(AccountsGetRequest(access_token=access_token))
        institution_name = response.item.institution_name or "Linked Bank"

        accounts = []
        for account in response.accounts:
            balances = account.balances
            accounts.append(
                AggregatorAccount(
                    aggregator_account_id=account.account_id,
                    institution_name=institution_name,
                    account_type=_map_account_type(
                        account.type.value,
                        account.subtype.value if account.subtype else None,
                    ),
                    current_balance=float(balances.current or 0),
                    available_balance=float(balances.available) if balances.available is not None else None,
                )
            )
        return accounts

    def list_transactions(
        self, access_token: str, aggregator_account_id: str, since: date | None = None
    ) -> list[AggregatorTransaction]:
        client = _client()
        start_date = since or (date.today() - timedelta(days=90))
        request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date,
            end_date=date.today(),
            options=TransactionsGetRequestOptions(account_ids=[aggregator_account_id]),
        )
        response = client.transactions_get(request)

        transactions = []
        for txn in response.transactions:
            category = None
            if txn.personal_finance_category:
                # `detailed` (e.g. "FOOD_AND_DRINK_GROCERIES") is more
                # specific than `primary` -- category_mapper.py falls back
                # to primary-level matching for anything it doesn't
                # recognize at the detailed level.
                category = txn.personal_finance_category.detailed
            elif txn.category:
                category = txn.category[0]

            transactions.append(
                AggregatorTransaction(
                    aggregator_transaction_id=txn.transaction_id,
                    aggregator_account_id=txn.account_id,
                    # Plaid's sign convention is the opposite of Bankr's
                    # internal one: positive = money out (expense), negative
                    # = money in (income). Flip it here, once, at the edge.
                    amount=-float(txn.amount),
                    date=txn.date,
                    merchant_name=txn.merchant_name or txn.name,
                    raw_category=category,
                    is_pending=txn.pending,
                )
            )
        return transactions

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        # Plaid signs webhooks with a JWT in the Plaid-Verification header,
        # verified against a rotating key from client.webhook_verification_key_get().
        # Wire this up once webhook delivery is implemented (see
        # app/jobs/insights_job.py and backend/README.md "Not yet wired up").
        raise NotImplementedError
