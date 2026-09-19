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

import hashlib
import hmac
import json
import logging
import time

import plaid
from jose import jwt as jose_jwt
from jose import jws
from jose.exceptions import JOSEError
from plaid.api import plaid_api
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.item_webhook_update_request import ItemWebhookUpdateRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.personal_finance_category_version import PersonalFinanceCategoryVersion
from plaid.model.products import Products
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.transactions_sync_request_options import TransactionsSyncRequestOptions
from plaid.model.webhook_verification_key_get_request import WebhookVerificationKeyGetRequest

from app.config import settings
from app.integrations.bank_aggregator import (
    AggregatorAccount,
    AggregatorTransaction,
    TransactionSyncResult,
)

# Plaid's max. The default is only 90 days, which would silently make any
# "this year" / year-over-year answer cover a single quarter. This lives on
# the *Link token*, not on /transactions/sync's own days_requested option --
# create_link_token below includes "transactions" in `products`, and
# Plaid's docs say that means transactions are initialized at Link time, so
# /transactions/sync's own days_requested "will have no effect" for this
# Item; only takes effect on an Item's very first sync either way.
HISTORY_DAYS_REQUESTED = 730
_SYNC_PAGE_SIZE = 500  # Plaid's max per /transactions/sync page
_MAX_PAGINATION_RESTARTS = 3

# Plaid rejects webhooks it considers stale by more than this; mirrored here
# so a replayed (captured-and-resent) webhook is rejected on our side too.
_WEBHOOK_MAX_AGE_SECONDS = 5 * 60

# Verification keys are keyed by `kid` and effectively static (Plaid rotates
# them rarely), so a process-lifetime cache avoids a webhook_verification_key_get
# round trip per webhook. {kid: (jwk_dict, expired_at | None)}.
_webhook_key_cache: dict[str, tuple[dict, int | None]] = {}

logger = logging.getLogger(__name__)

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
        request_kwargs = {
            "client_name": "Bankr",
            "language": "en",
            "country_codes": [CountryCode("US")],
            "products": [Products("transactions")],
            "user": LinkTokenCreateRequestUser(client_user_id=user_id),
            "transactions": LinkTokenTransactions(days_requested=HISTORY_DAYS_REQUESTED),
        }
        # Omitted, not empty-stringed, when unset: the field is a plain
        # (non-nullable) str on Plaid's model, and linking without a
        # webhook is a valid, fully-functional choice (see settings.plaid_webhook_url).
        if settings.plaid_webhook_url:
            request_kwargs["webhook"] = settings.plaid_webhook_url
        response = client.link_token_create(LinkTokenCreateRequest(**request_kwargs))
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
                    name=account.official_name or account.name,
                    mask=account.mask,
                )
            )
        return accounts

    def sync_transactions(self, access_token: str, cursor: str | None) -> TransactionSyncResult:
        """Drain /transactions/sync from `cursor` until has_more is false.

        Replaces /transactions/get, which returned only its first page
        (100 transactions by default) and never reported pending->posted
        replacements -- together, silently truncated history and
        double-counted charges.

        Per Plaid's docs (plaid.com/docs/api/products/transactions/#transactionssync):
        - If the data changes mid-pagination, the whole pagination must
          restart from the *original* cursor, discarding the pages already
          fetched -- not just retry the one failed request.
        - `days_requested` belongs on /link/token/create, not here: since
          create_link_token includes "transactions" in `products` (i.e.
          transactions are initialized at Link time, not lazily), Plaid
          says days_requested on /transactions/sync itself "will have no
          effect" for this Item and must be set on Link token creation
          instead -- see HISTORY_DAYS_REQUESTED above.
        - `include_personal_finance_category`/`personal_finance_category_version`
          are requested explicitly rather than relying on an account's
          default: category_mapper.py's whole taxonomy is verified against
          PFCv2 specifically, so an account that defaulted to v1 would
          silently miscategorize everything.
        - Calling this immediately after Item creation (see
          sync_service.sync_user_accounts, called synchronously from
          POST /linked-accounts) is expected to sometimes return empty
          arrays if history isn't ready yet -- not an error; webhooks are
          how you *also* find out when more becomes available, not a
          prerequisite for calling this at all."""
        client = _client()
        options = TransactionsSyncRequestOptions(
            include_personal_finance_category=True,
            personal_finance_category_version=PersonalFinanceCategoryVersion("v2"),
        )
        for _ in range(_MAX_PAGINATION_RESTARTS):
            result = TransactionSyncResult(next_cursor=cursor)
            page_cursor = cursor
            try:
                while True:
                    request_kwargs = {"access_token": access_token, "count": _SYNC_PAGE_SIZE, "options": options}
                    if page_cursor:
                        request_kwargs["cursor"] = page_cursor
                    response = client.transactions_sync(TransactionsSyncRequest(**request_kwargs))
                    result.added.extend(_to_aggregator_transaction(t) for t in response.added)
                    result.modified.extend(_to_aggregator_transaction(t) for t in response.modified)
                    result.removed_ids.extend(r.transaction_id for r in response.removed)
                    page_cursor = response.next_cursor
                    if not response.has_more:
                        break
            except plaid.ApiException as e:
                if _plaid_error_code(e) == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":
                    continue
                raise
            result.next_cursor = page_cursor
            return result
        raise RuntimeError("Plaid transactions kept changing during pagination; try the sync again")

    def get_item_id(self, access_token: str) -> str:
        client = _client()
        response = client.item_get(ItemGetRequest(access_token=access_token))
        return response.item.item_id

    def update_item_webhook(self, access_token: str, webhook_url: str) -> None:
        client = _client()
        client.item_webhook_update(ItemWebhookUpdateRequest(access_token=access_token, webhook=webhook_url))

    def verify_webhook_signature(self, payload: bytes, signature_header: str) -> bool:
        """Verify the `Plaid-Verification` header per Plaid's documented
        algorithm (plaid.com/docs/api/webhooks/webhook-verification):

        1. Read `kid`/`alg` from the JWT header (unverified) -- alg must be
           ES256, Plaid's only signing algorithm for this.
        2. Fetch (or reuse a cached) EC public key for that `kid` via
           webhook_verification_key_get.
        3. Verify the JWT's signature against that key.
        4. Reject a payload older than 5 minutes (`iat`) -- replay defense.
        5. Compare a SHA-256 of the *raw* body against the JWT's
           request_body_sha256 claim, in constant time -- this is what ties
           the verified signature to this exact body rather than just to
           some validly-signed JWT.

        Every failure mode returns False rather than raising, since the
        caller's only correct response to any of them is the same: reject
        the webhook. Reasons are logged so a bad key/secret configuration
        is diagnosable without leaking anything to the caller."""
        try:
            header = jose_jwt.get_unverified_header(signature_header)
        except JOSEError:
            logger.warning("plaid webhook: unparseable Plaid-Verification header")
            return False

        if header.get("alg") != "ES256":
            logger.warning("plaid webhook: unexpected alg %r", header.get("alg"))
            return False

        kid = header.get("kid")
        if not kid:
            logger.warning("plaid webhook: verification header has no kid")
            return False

        key = self._webhook_verification_key(kid)
        if key is None:
            logger.warning("plaid webhook: no verification key for kid %s", kid)
            return False

        try:
            claims_json = jws.verify(signature_header, key, algorithms=["ES256"])
            claims = json.loads(claims_json)
        except (JOSEError, ValueError):
            logger.warning("plaid webhook: signature verification failed")
            return False

        if abs(time.time() - claims.get("iat", 0)) > _WEBHOOK_MAX_AGE_SECONDS:
            logger.warning("plaid webhook: iat outside the %ss freshness window", _WEBHOOK_MAX_AGE_SECONDS)
            return False

        expected_hash = claims.get("request_body_sha256", "")
        actual_hash = hashlib.sha256(payload).hexdigest()
        if not hmac.compare_digest(expected_hash, actual_hash):
            logger.warning("plaid webhook: request_body_sha256 mismatch")
            return False

        return True

    def _webhook_verification_key(self, kid: str) -> dict | None:
        cached = _webhook_key_cache.get(kid)
        if cached is not None:
            jwk, expired_at = cached
            if expired_at is None or expired_at > time.time():
                return jwk
            del _webhook_key_cache[kid]

        client = _client()
        try:
            response = client.webhook_verification_key_get(WebhookVerificationKeyGetRequest(key_id=kid))
        except plaid.ApiException:
            logger.exception("plaid webhook: webhook_verification_key_get failed for kid %s", kid)
            return None

        key = response.key
        jwk = {"kty": key.kty, "crv": key.crv, "kid": key.kid, "x": key.x, "y": key.y, "alg": key.alg, "use": key.use}
        _webhook_key_cache[kid] = (jwk, key.expired_at)
        return jwk


def _plaid_error_code(error: plaid.ApiException) -> str | None:
    try:
        return json.loads(error.body).get("error_code")
    except (TypeError, ValueError, AttributeError):
        return None


def _to_aggregator_transaction(txn) -> AggregatorTransaction:
    category = None
    if txn.personal_finance_category:
        # `detailed` (e.g. "FOOD_AND_DRINK_GROCERIES") is more specific than
        # `primary` -- category_mapper.py falls back to primary-level
        # matching for anything it doesn't recognize at the detailed level.
        category = txn.personal_finance_category.detailed
    elif txn.category:
        category = txn.category[0]

    return AggregatorTransaction(
        aggregator_transaction_id=txn.transaction_id,
        aggregator_account_id=txn.account_id,
        # Plaid's sign convention is the opposite of Bankr's internal one:
        # positive = money out (expense), negative = money in (income).
        # Flip it here, once, at the edge.
        amount=-float(txn.amount),
        date=txn.date,
        merchant_name=txn.merchant_name or txn.name,
        raw_category=category,
        is_pending=txn.pending,
        pending_transaction_id=txn.get("pending_transaction_id"),
    )
