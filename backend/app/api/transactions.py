from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, aliased

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import Category, User
from app.services import money_query as mq
from app.services.sync_service import refresh_net_worth
from app.services.transaction_edit_service import (
    TransactionEditError,
    TransactionNotFound,
    category_tree,
    get_owned_transaction,
    set_splits,
    update_transaction,
)

router = APIRouter(tags=["transactions"])


class UpdateTransactionRequest(BaseModel):
    category_id: UUID | None = None
    merchant_name: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)
    excluded: bool | None = None


class SplitPart(BaseModel):
    amount: float
    category_id: UUID
    note: str | None = Field(default=None, max_length=200)


class SetSplitsRequest(BaseModel):
    splits: list[SplitPart]


@router.get("/categories")
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"categories": category_tree(db)}


def _owned(db: Session, user: User, transaction_id: UUID):
    try:
        return get_owned_transaction(db, user.id, transaction_id)
    except TransactionNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "transaction not found")


def _row(db: Session, txn) -> dict:
    """The edited row in the same shape /dashboard/transactions lists it."""
    parent = aliased(Category)
    db.refresh(txn)
    name, ctype, parent_name = (
        db.query(Category.name, Category.type, parent.name)
        .outerjoin(parent, Category.parent_category_id == parent.id)
        .filter(Category.id == txn.bankr_category_id)
        .one_or_none()
        or (None, None, None)
    )
    splits = mq._splits_for(db, [txn.id]) if txn.is_split else {}
    return {**mq.transaction_row(txn, name, ctype, parent_name), "splits": splits.get(txn.id, [])}


@router.patch("/transactions/{transaction_id}")
def edit_transaction(
    transaction_id: UUID,
    body: UpdateTransactionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    txn = _owned(db, user, transaction_id)
    try:
        update_transaction(
            db,
            txn,
            category_id=body.category_id,
            merchant_name=body.merchant_name,
            notes=body.notes,
            excluded=body.excluded,
        )
    except TransactionEditError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    refresh_net_worth(db, user.id)  # commits, and keeps spending-goal progress current
    return _row(db, txn)


@router.put("/transactions/{transaction_id}/splits")
def replace_splits(
    transaction_id: UUID,
    body: SetSplitsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    txn = _owned(db, user, transaction_id)
    try:
        set_splits(db, txn, [p.model_dump() for p in body.splits])
    except TransactionEditError as e:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    refresh_net_worth(db, user.id)
    return _row(db, txn)
