from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import category_service as cs
from app.services.sync_service import refresh_net_worth
from app.services.transaction_edit_service import category_tree

router = APIRouter(prefix="/categories", tags=["categories"])

# Names are trimmed and checked again by the service.
_NAME = Field(max_length=cs.MAX_NAME_LENGTH * 2)


class CreateCategoryRequest(BaseModel):
    name: str = _NAME
    group_id: UUID | None = None  # a spending group; none: alone in a new group of its name


class CreateGroupRequest(BaseModel):
    name: str = _NAME


class RenameRequest(BaseModel):
    name: str = _NAME  # "" puts a built-in one's own name back


def _tree(db: Session, user: User) -> dict:
    return {"categories": category_tree(db, user.id)}


def _bad(e: cs.CategoryError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.get("")
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return _tree(db, user)


@router.post("", status_code=status.HTTP_201_CREATED)
def add_category(body: CreateCategoryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        category = cs.create_category(db, user.id, body.name, body.group_id)
    except cs.CategoryError as e:
        db.rollback()
        raise _bad(e)
    db.commit()
    return {"id": str(category.id), **_tree(db, user)}


@router.post("/groups", status_code=status.HTTP_201_CREATED)
def add_group(body: CreateGroupRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        group = cs.create_group(db, user.id, body.name)
    except cs.CategoryError as e:
        db.rollback()
        raise _bad(e)
    db.commit()
    return {"id": str(group.id), **_tree(db, user)}


@router.patch("/{item_id}")
def rename(item_id: UUID, body: RenameRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """A group or category, the user's own or a built-in one (for them only)."""
    try:
        cs.rename(db, user.id, item_id, body.name)
    except cs.CategoryNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    except cs.CategoryError as e:
        db.rollback()
        raise _bad(e)
    db.commit()
    return _tree(db, user)


@router.delete("/{item_id}")
def remove(item_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """One of the user's own groups or categories."""
    try:
        moved = cs.delete(db, user.id, item_id)
    except cs.CategoryNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    except cs.CategoryError as e:
        db.rollback()
        raise _bad(e)
    refresh_net_worth(db, user.id)  # commits, and keeps spending-goal progress current
    return {"recategorized": moved}
