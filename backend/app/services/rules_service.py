"""Categorization rules: "always put <merchant> under <category>".

Rules run on every synced transaction after category_mapper's default,
and can be applied to existing history. Neither ever touches a row the user
categorized by hand (category_overridden) or a split parent.
"""

from uuid import UUID

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models import Category, LinkedAccount, Rule, Transaction

MAX_RULES = 200


class RuleError(ValueError):
    pass


class RuleNotFound(LookupError):
    pass


def user_rules(db: Session, user_id: UUID) -> list[Rule]:
    """In match order: highest priority first, then newest."""
    return (
        db.query(Rule)
        .filter(Rule.user_id == user_id)
        .order_by(Rule.priority.desc(), Rule.created_at.desc())
        .all()
    )


def _matches(rule: Rule, txn: Transaction) -> bool:
    needle = rule.merchant_contains.lower()
    names = (txn.original_merchant_name, txn.merchant_name)
    if not any(n and needle in n.lower() for n in names):
        return False
    size = abs(float(txn.amount))
    if rule.amount_min is not None and size < float(rule.amount_min):
        return False
    if rule.amount_max is not None and size > float(rule.amount_max):
        return False
    if rule.linked_account_id is not None and rule.linked_account_id != txn.linked_account_id:
        return False
    return True


def apply_rules(txn: Transaction, rules: list[Rule]) -> Rule | None:
    """Apply the first matching rule to txn in place; returns it, or None."""
    if txn.category_overridden or txn.is_split or txn.split_parent_id is not None:
        return None
    for rule in rules:
        if _matches(rule, txn):
            txn.bankr_category_id = rule.set_category_id
            if rule.set_merchant_name and not txn.merchant_overridden:
                txn.merchant_name = rule.set_merchant_name
            return rule
    return None


def _candidates(db: Session, user_id: UUID, rule: Rule):
    needle = f"%{rule.merchant_contains}%"
    return (
        db.query(Transaction)
        .join(LinkedAccount, Transaction.linked_account_id == LinkedAccount.id)
        .filter(
            LinkedAccount.user_id == user_id,
            Transaction.category_overridden.is_(False),
            Transaction.is_split.is_(False),
            Transaction.split_parent_id.is_(None),
            or_(Transaction.original_merchant_name.ilike(needle), Transaction.merchant_name.ilike(needle)),
        )
    )


def preview_rule(db: Session, user_id: UUID, merchant_contains: str, category_id: UUID) -> int:
    """How many past transactions a new rule would recategorize."""
    rule = Rule(merchant_contains=merchant_contains, set_category_id=category_id)
    return (
        _candidates(db, user_id, rule)
        .filter(or_(Transaction.bankr_category_id.is_(None), Transaction.bankr_category_id != category_id))
        .with_entities(func.count(Transaction.id))
        .scalar()
    )


def apply_rule_to_existing(db: Session, user_id: UUID, rule: Rule) -> int:
    """Run the user's rules (so a higher-priority rule still wins) over every
    past transaction `rule` could match. Returns how many changed."""
    rules = user_rules(db, user_id)
    changed = 0
    for txn in _candidates(db, user_id, rule).all():
        before = (txn.bankr_category_id, txn.merchant_name)
        apply_rules(txn, rules)
        if (txn.bankr_category_id, txn.merchant_name) != before:
            changed += 1
    db.flush()
    return changed


def _validate(db: Session, user_id: UUID, fields: dict) -> None:
    if "merchant_contains" in fields:
        fields["merchant_contains"] = (fields["merchant_contains"] or "").strip()
        if len(fields["merchant_contains"]) < 2:
            raise RuleError("merchant_contains needs at least 2 characters")
    if fields.get("set_category_id") is not None and db.get(Category, fields["set_category_id"]) is None:
        raise RuleError("unknown category")
    if fields.get("linked_account_id") is not None:
        owned = (
            db.query(LinkedAccount)
            .filter(LinkedAccount.id == fields["linked_account_id"], LinkedAccount.user_id == user_id)
            .count()
        )
        if not owned:
            raise RuleError("unknown account")
    if "set_merchant_name" in fields:
        fields["set_merchant_name"] = (fields["set_merchant_name"] or "").strip() or None
    lo, hi = fields.get("amount_min"), fields.get("amount_max")
    if lo is not None and hi is not None and lo > hi:
        raise RuleError("amount_min is more than amount_max")


def create_rule(db: Session, user_id: UUID, **fields) -> Rule:
    if db.query(Rule).filter(Rule.user_id == user_id).count() >= MAX_RULES:
        raise RuleError(f"you can have up to {MAX_RULES} rules")
    _validate(db, user_id, fields)
    rule = Rule(user_id=user_id, **fields)
    db.add(rule)
    db.flush()
    return rule


def get_rule(db: Session, user_id: UUID, rule_id: UUID) -> Rule:
    rule = db.query(Rule).filter(Rule.id == rule_id, Rule.user_id == user_id).one_or_none()
    if rule is None:
        raise RuleNotFound(rule_id)
    return rule


def update_rule(db: Session, rule: Rule, **fields) -> Rule:
    _validate(db, rule.user_id, fields)
    for key, value in fields.items():
        setattr(rule, key, value)
    db.flush()
    return rule
