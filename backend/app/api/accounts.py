from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_aggregator
from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import LinkedAccount, User
from app.integrations.bank_aggregator import BankAggregatorClient
from app.jobs.insights_job import run_insights_job_safely
from app.services.account_removal import BankNotFound, RemovalError, disconnect_bank, list_bank_logins
from app.services.crypto import decrypt_token
from app.services.sync_service import sync_user_accounts

router = APIRouter(prefix="/linked-accounts", tags=["accounts"])


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
    run_insights_job_safely(db, user.id)
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

    run_insights_job_safely(db, user.id)
    return LinkAccountResponse(
        linked_account_count=len(linked_accounts),
        transactions_synced=total_transactions,
        net_worth=float(latest_result.net_worth_snapshot.net_worth),
    )


class LinkedBankAccount(BaseModel):
    name: str | None
    mask: str | None
    account_type: str


class LinkedBank(BaseModel):
    # Any one of the bank's account ids; DELETE /linked-accounts/{id} removes
    # the whole bank login that account belongs to.
    id: UUID
    institution_name: str
    status: str  # active | error
    accounts: list[LinkedBankAccount]


@router.get("", response_model=list[LinkedBank])
def list_linked_banks(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[LinkedBank]:
    """The user's connected banks, one entry per bank login."""
    return [
        LinkedBank(
            id=login.accounts[0].id,
            institution_name=login.accounts[0].institution_name,
            status="error" if any(a.status != "active" for a in login.accounts) else "active",
            accounts=[LinkedBankAccount(name=a.name, mask=a.mask, account_type=a.account_type) for a in login.accounts],
        )
        for login in list_bank_logins(db, user.id)
    ]


@router.delete("/{linked_account_id}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_linked_bank(
    linked_account_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    aggregator: BankAggregatorClient = Depends(get_aggregator),
) -> Response:
    """Disconnect a bank: removes the login at Plaid (ending its billing),
    then deletes its accounts and transactions here."""
    try:
        disconnect_bank(db, user.id, linked_account_id, aggregator)
    except BankNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bank not found")
    except RemovalError:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Couldn't disconnect this bank right now. Nothing was changed; try again."
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
