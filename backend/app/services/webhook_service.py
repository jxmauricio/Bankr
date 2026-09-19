"""Handles a verified inbound Plaid webhook payload.

Signature verification happens in the route (app/api/webhooks.py), against
the aggregator adapter (see PlaidClient.verify_webhook_signature) -- this
module only ever sees a payload that's already been proven to come from
Plaid, and focuses on what to *do* about it.

Only three webhook codes are handled; everything else is logged and
ignored, which is the correct behavior for a webhook endpoint (Plaid adds
new codes over time, and an unrecognized one is not an error):

- TRANSACTIONS / SYNC_UPDATES_AVAILABLE, HISTORICAL_UPDATE,
  INITIAL_UPDATE, DEFAULT_UPDATE: new data is ready -- run the same
  sync_user_accounts the Refresh button and initial link use. TRANSACTIONS
  / TRANSACTIONS_REMOVED is folded in here too: sync_transactions already
  reports its own `removed` list, so an extra sync catches whatever
  triggered the webhook either way.
- ITEM / ERROR with error_code ITEM_LOGIN_REQUIRED: the bank login needs
  the user to re-auth (password change, revoked MFA, ...). Mark every
  account under that Item as erroring rather than silently going stale --
  see get_net_worth's `excluded_accounts`, which is what surfaces this to
  the user.
- ITEM / LOGIN_REPAIRED: the user fixed it via Plaid's update-mode Link
  flow; flip accounts back to active and sync once.

A webhook for an item_id Bankr doesn't recognize (a stale item, a
never-fully-linked one, or a test payload) is a no-op, not an error --
Plaid should still get a 2xx so it doesn't retry forever.
"""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import LinkedAccount
from app.integrations.bank_aggregator import BankAggregatorClient
from app.jobs.insights_job import run_insights_job_safely
from app.services.crypto import decrypt_token
from app.services.sync_service import sync_user_accounts

logger = logging.getLogger(__name__)

_SYNC_WEBHOOK_CODES = {
    "SYNC_UPDATES_AVAILABLE",
    "HISTORICAL_UPDATE",
    "INITIAL_UPDATE",
    "DEFAULT_UPDATE",
    "TRANSACTIONS_REMOVED",
}


def handle_plaid_webhook(db: Session, payload: dict, aggregator: BankAggregatorClient) -> None:
    webhook_type = payload.get("webhook_type")
    webhook_code = payload.get("webhook_code")
    item_id = payload.get("item_id")

    if not item_id:
        logger.info("plaid webhook %s/%s has no item_id, ignoring", webhook_type, webhook_code)
        return

    accounts = db.query(LinkedAccount).filter(LinkedAccount.item_id == item_id).all()
    if not accounts:
        logger.info("plaid webhook %s/%s for unknown item_id %s, ignoring", webhook_type, webhook_code, item_id)
        return
    user_id: UUID = accounts[0].user_id  # every account under one Item belongs to the same user

    if webhook_type == "TRANSACTIONS" and webhook_code in _SYNC_WEBHOOK_CODES:
        _sync(db, user_id, accounts[0], item_id, aggregator)
        return

    if webhook_type == "ITEM" and webhook_code == "ERROR":
        error_code = ((payload.get("error") or {}).get("error_code"))
        if error_code == "ITEM_LOGIN_REQUIRED":
            for account in accounts:
                account.status = "error"
            db.commit()
        else:
            logger.info("plaid webhook ITEM/ERROR for item %s: %s", item_id, error_code)
        return

    if webhook_type == "ITEM" and webhook_code == "LOGIN_REPAIRED":
        for account in accounts:
            account.status = "active"
        db.commit()
        _sync(db, user_id, accounts[0], item_id, aggregator)
        return

    logger.info("unhandled plaid webhook %s/%s for item %s", webhook_type, webhook_code, item_id)


def _sync(db: Session, user_id: UUID, an_account: LinkedAccount, item_id: str, aggregator: BankAggregatorClient) -> None:
    access_token = decrypt_token(an_account.access_token_ref)
    sync_user_accounts(db, user_id, access_token, aggregator=aggregator, item_id=item_id)
    run_insights_job_safely(db, user_id)
