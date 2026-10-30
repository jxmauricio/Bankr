"""What Bankr remembers about the user across conversations.

The chat only resends its last 20 messages (chat_service.MAX_HISTORY_MESSAGES),
so a pay schedule mentioned last week is gone by now. MemoryFacts are the
durable part: a short list of facts the agent sees on every turn
(claude_agent._memory_context). The user owns the list -- they add, edit
and delete facts in Settings, and the agent can only draft one
(tools.propose_memory) for them to confirm on a card.

Kept small and cheap: at most MAX_FACTS facts of MAX_FACT_CHARS each, so the
block costs a few hundred tokens at most. And kept free of anything that
would hurt if the prompt leaked: check_fact rejects account and card
numbers, credentials and government IDs before anything is stored.
"""

import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import MemoryFact

MAX_FACTS = 30
MAX_FACT_CHARS = 200

# Shown in Settings and in the agent's block, in this order.
KINDS = {
    "income": "Pay & income",
    "priority": "Priority",
    "household": "Household",
    "preference": "Preference",
    "other": "Other",
}
SOURCES = ("user", "agent")


class FactError(ValueError):
    pass


class FactNotFound(LookupError):
    pass


# 8+ digits in a row, allowing single spaces or dashes between them: card,
# account and routing numbers, SSNs written without dashes, phone numbers.
# Dollar amounts never match -- their commas split the run into threes.
_LONG_NUMBER = re.compile(r"(?<![\d$.,])\d(?:[ -]?\d){7,}(?!\d)")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_SENSITIVE_WORDS = re.compile(
    r"\b("
    r"passwords?|passcodes?|passphrases?|pins?|pin numbers?|"
    r"ssn|social security|tax id|itin|ein|"
    r"routing numbers?|account numbers?|acct (?:no|num|number|#)|card numbers?|"
    r"cvv|cvc|security codes?|expiration date|expiry|"
    r"api keys?|secret keys?|access tokens?|credentials?|log ?in|username|"
    r"driver'?s licen[cs]e|passport|security questions?|mother'?s maiden name"
    r")\b",
    re.IGNORECASE,
)


def check_fact(text: str, kind: str) -> tuple[str, str]:
    """The cleaned (text, kind), or FactError saying why it can't be kept."""
    text = " ".join((text or "").split())
    if not text:
        raise FactError("A memory needs some text.")
    if len(text) > MAX_FACT_CHARS:
        raise FactError(f"Keep it under {MAX_FACT_CHARS} characters.")
    kind = (kind or "other").strip().lower()
    if kind not in KINDS:
        raise FactError(f"kind must be one of {', '.join(KINDS)}")
    if _SSN.search(text) or _LONG_NUMBER.search(_ISO_DATE.sub("", text)) or _SENSITIVE_WORDS.search(text):
        raise FactError(
            "Bankr doesn't remember account or card numbers, passwords, or ID numbers. "
            "Leave those out and try again."
        )
    return text, kind


def user_facts(db: Session, user_id: UUID) -> list[MemoryFact]:
    order = list(KINDS)
    facts = db.query(MemoryFact).filter(MemoryFact.user_id == user_id).order_by(MemoryFact.created_at).all()
    return sorted(facts, key=lambda f: order.index(f.kind) if f.kind in order else len(order))


def get_fact(db: Session, user_id: UUID, fact_id: UUID) -> MemoryFact:
    fact = db.query(MemoryFact).filter(MemoryFact.id == fact_id, MemoryFact.user_id == user_id).one_or_none()
    if fact is None:
        raise FactNotFound()
    return fact


def find_fact(db: Session, user_id: UUID, text: str) -> MemoryFact | None:
    """The user's fact with this exact text (ignoring case and spacing)."""
    wanted = " ".join((text or "").split()).lower()
    return next((f for f in user_facts(db, user_id) if f.text.lower() == wanted), None)


def check_new_fact(db: Session, user_id: UUID, text: str, kind: str, replaces: MemoryFact | None = None) -> tuple[str, str]:
    """check_fact, plus room in the list and no exact duplicate."""
    text, kind = check_fact(text, kind)
    existing = find_fact(db, user_id, text)
    if existing is not None and existing is not replaces:
        raise FactError("Bankr already remembers that.")
    if replaces is None and db.query(MemoryFact).filter(MemoryFact.user_id == user_id).count() >= MAX_FACTS:
        raise FactError(f"Bankr remembers up to {MAX_FACTS} things. Delete one in Settings to add another.")
    return text, kind


def add_fact(
    db: Session, user_id: UUID, text: str, kind: str, source: str = "user", replaces_id: UUID | None = None
) -> MemoryFact:
    """Save a fact, or with replaces_id overwrite that one (an updated pay
    schedule replaces the old one rather than contradicting it). Flushes,
    doesn't commit."""
    if source not in SOURCES:
        raise FactError(f"source must be one of {', '.join(SOURCES)}")
    replaces = get_fact(db, user_id, replaces_id) if replaces_id else None
    text, kind = check_new_fact(db, user_id, text, kind, replaces)
    if replaces is not None:
        replaces.text, replaces.kind, replaces.source = text, kind, source
        replaces.updated_at = datetime.now(timezone.utc)
        db.flush()
        return replaces
    fact = MemoryFact(user_id=user_id, text=text, kind=kind, source=source)
    db.add(fact)
    db.flush()
    return fact


def update_fact(db: Session, fact: MemoryFact, text: str | None = None, kind: str | None = None) -> MemoryFact:
    new_text, new_kind = check_fact(fact.text if text is None else text, fact.kind if kind is None else kind)
    duplicate = find_fact(db, fact.user_id, new_text)
    if duplicate is not None and duplicate.id != fact.id:
        raise FactError("Bankr already remembers that.")
    fact.text, fact.kind = new_text, new_kind
    fact.updated_at = datetime.now(timezone.utc)
    db.flush()
    return fact


def fact_dict(fact: MemoryFact) -> dict:
    return {
        "id": str(fact.id),
        "kind": fact.kind,
        "text": fact.text,
        "source": fact.source,
        "created_at": fact.created_at.isoformat() if fact.created_at else None,
        "updated_at": fact.updated_at.isoformat() if fact.updated_at else None,
    }
