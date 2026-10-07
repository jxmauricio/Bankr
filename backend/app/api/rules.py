from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import Category, Rule, User
from app.services.rules_service import (
    RuleError,
    RuleNotFound,
    apply_rule_to_existing,
    create_rule,
    get_rule,
    preview_rule,
    update_rule,
    user_rules,
)
from app.services.sync_service import refresh_net_worth

router = APIRouter(prefix="/rules", tags=["rules"])


class RuleFields(BaseModel):
    merchant_contains: str | None = Field(default=None, max_length=120)
    amount_min: float | None = Field(default=None, ge=0)
    amount_max: float | None = Field(default=None, ge=0)
    linked_account_id: UUID | None = None
    set_category_id: UUID | None = None
    set_merchant_name: str | None = Field(default=None, max_length=120)
    priority: int | None = None


class CreateRuleRequest(RuleFields):
    merchant_contains: str = Field(max_length=120)
    set_category_id: UUID
    apply_to_existing: bool = False


def _rule_dict(db: Session, rule: Rule, applied: int | None = None) -> dict:
    category = db.get(Category, rule.set_category_id)
    out = {
        "id": str(rule.id),
        "merchant_contains": rule.merchant_contains,
        "amount_min": float(rule.amount_min) if rule.amount_min is not None else None,
        "amount_max": float(rule.amount_max) if rule.amount_max is not None else None,
        "linked_account_id": str(rule.linked_account_id) if rule.linked_account_id else None,
        "set_category_id": str(rule.set_category_id),
        "set_category": category.name if category else None,
        "set_merchant_name": rule.set_merchant_name,
        "priority": rule.priority,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }
    if applied is not None:
        out["applied_to"] = applied
    return out


@router.get("")
def list_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"rules": [_rule_dict(db, r) for r in user_rules(db, user.id)]}


@router.get("/preview")
def preview(
    merchant_contains: str = Query(min_length=2, max_length=120),
    category_id: UUID = Query(),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    return {"would_change": preview_rule(db, user.id, merchant_contains.strip(), category_id)}


@router.post("", status_code=status.HTTP_201_CREATED)
def add_rule(body: CreateRuleRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    fields = body.model_dump(exclude={"apply_to_existing"}, exclude_none=True)
    try:
        rule = create_rule(db, user.id, **fields)
    except RuleError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    applied = apply_rule_to_existing(db, user.id, rule) if body.apply_to_existing else None
    refresh_net_worth(db, user.id)  # commits, and keeps spending-goal progress current
    return _rule_dict(db, rule, applied)


@router.patch("/{rule_id}")
def edit_rule(
    rule_id: UUID, body: RuleFields, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        rule = get_rule(db, user.id, rule_id)
        update_rule(db, rule, **body.model_dump(exclude_unset=True))
    except RuleNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    except RuleError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    return _rule_dict(db, rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    try:
        rule = get_rule(db, user.id, rule_id)
    except RuleNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "rule not found")
    db.delete(rule)
    db.commit()
