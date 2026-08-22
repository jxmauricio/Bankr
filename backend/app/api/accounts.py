import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_aggregator
from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import LinkedAccount, User
from app.integrations.bank_aggregator import BankAggregatorClient
from app.jobs.insights_job import run_insights_job
from app.services.crypto import decrypt_token
from app.services.sync_service import sync_user_accounts

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/linked-accounts", tags=["accounts"])


def _trigger_insights(db: Session, user_id: UUID) -> None:
    # Best-effort: a failure phrasing insights (e.g. no OPENROUTER_API_KEY
    # configured yet) shouldn't fail the sync response the client is waiting on.
    try:
        run_insights_job(db, user_id)
    except Exception:
        logger.exception("insights job failed for user %s", user_id)


class LinkTokenResponse(BaseModel):
    link_token: str


@router.post("/link-token", response_model=LinkTokenResponse)
def create_link_token(
    user: User = Depends(get_current_user),
    aggregator: BankAggregatorClient = Depends(get_aggregator),
) -> LinkTokenResponse:
    """The iOS app calls this first, then hands the returned token to the
    Plaid Link SDK to launch the hosted bank-login UI."""
    return LinkTokenResponse(link_token=aggregator.create_link_token(str(user.id)))


class LinkAccountRequest(BaseModel):
    # Public token returned to the client by the Plaid Link SDK once the user
    # finishes authenticating with their bank -- see ios/README.md. The
    # backend exchanges this for a durable access token; Plaid Link itself
    # never hands the client anything long-lived.
    public_token: str


class LinkAccountResponse(BaseModel):
    linked_account_count: int
    transactions_synced: int
    net_worth: float


@router.post("", response_model=LinkAccountResponse)
def link_account(
    body: LinkAccountRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    aggregator: BankAggregatorClient = Depends(get_aggregator),
) -> LinkAccountResponse:
    access_token = aggregator.exchange_public_token(body.public_token)
    result = sync_user_accounts(db, user.id, access_token, aggregator=aggregator)
    _trigger_insights(db, user.id)
    return LinkAccountResponse(
        linked_account_count=len(result.linked_accounts),
        transactions_synced=result.transactions_synced,
        net_worth=float(result.net_worth_snapshot.net_worth),
    )


@router.post("/sync", response_model=LinkAccountResponse)
def resync_all_accounts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    aggregator: BankAggregatorClient = Depends(get_aggregator),
) -> LinkAccountResponse:
    """Re-sync every already-linked account using its stored access token."""
    linked_accounts = db.query(LinkedAccount).filter(LinkedAccount.user_id == user.id).all()
    # Multiple LinkedAccount rows can share one aggregator enrollment/Item
    # token (one token covers every account the user granted access to under
    # that bank login), so dedupe before re-syncing to avoid redundant calls.
    unique_tokens = {decrypt_token(linked.access_token_ref) for linked in linked_accounts}

    total_transactions = 0
    latest_result = None
    for access_token in unique_tokens:
        latest_result = sync_user_accounts(db, user.id, access_token, aggregator=aggregator)
        total_transactions += latest_result.transactions_synced

    if latest_result is None:
        return LinkAccountResponse(linked_account_count=0, transactions_synced=0, net_worth=0.0)

    _trigger_insights(db, user.id)
    return LinkAccountResponse(
        linked_account_count=len(linked_accounts),
        transactions_synced=total_transactions,
        net_worth=float(latest_result.net_worth_snapshot.net_worth),
    )
