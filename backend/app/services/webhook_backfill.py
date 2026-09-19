"""Attach the configured webhook URL to every already-linked Item.

create_link_token only sets a webhook on a *newly* created Item -- an
account linked before PLAID_WEBHOOK_URL was set (or before it changed, e.g.
a fresh ngrok URL in dev) never gets one unless this runs. Safe to re-run
any time; Plaid's /item/webhook/update simply overwrites whatever webhook
URL was there before, same idempotent shape as category_backfill.py.
"""

from sqlalchemy.orm import Session

from app.db.models import LinkedAccount
from app.integrations.bank_aggregator import BankAggregatorClient
from app.services.crypto import decrypt_token


def attach_webhook_to_existing_items(db: Session, aggregator: BankAggregatorClient, webhook_url: str) -> int:
    """Returns the number of distinct bank logins (Items) updated."""
    # One access token can back several LinkedAccount rows (every account
    # under one bank login shares it) -- dedupe so each Item is only
    # updated once, same reasoning as api/accounts.py's resync loop.
    unique_tokens = {decrypt_token(la.access_token_ref) for la in db.query(LinkedAccount).all()}
    for access_token in unique_tokens:
        aggregator.update_item_webhook(access_token, webhook_url)
    return len(unique_tokens)
