"""What Bankr remembers about the user: the list in Settings, and the
endpoint a confirmed "Remember this?" card in chat posts to."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services.memory_service import (
    KINDS,
    MAX_FACT_CHARS,
    MAX_FACTS,
    FactError,
    FactNotFound,
    add_fact,
    fact_dict,
    get_fact,
    update_fact,
    user_facts,
)

router = APIRouter(prefix="/memory", tags=["memory"])


class CreateFactRequest(BaseModel):
    text: str = Field(max_length=500)  # trimmed and capped at MAX_FACT_CHARS by the service
    kind: str = "other"
    # "agent" when it comes from confirming a card the agent drafted.
    source: str = "user"
    # Overwrite this fact instead of adding one (an updated pay schedule).
    replaces_id: UUID | None = None


class UpdateFactRequest(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    kind: str | None = None


@router.get("")
def list_facts(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {
        "facts": [fact_dict(f) for f in user_facts(db, user.id)],
        "kinds": KINDS,
        "max_facts": MAX_FACTS,
        "max_chars": MAX_FACT_CHARS,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def create_fact(body: CreateFactRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        fact = add_fact(db, user.id, body.text, body.kind, body.source, body.replaces_id)
    except FactNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
    except FactError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    return fact_dict(fact)


@router.patch("/{fact_id}")
def edit_fact(
    fact_id: UUID, body: UpdateFactRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    try:
        fact = update_fact(db, get_fact(db, user.id, fact_id), body.text, body.kind)
    except FactNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
    except FactError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    return fact_dict(fact)


@router.delete("/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fact(fact_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    try:
        fact = get_fact(db, user.id, fact_id)
    except FactNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
    db.delete(fact)
    db.commit()
