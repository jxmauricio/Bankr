from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import Category, User
from app.services.category_service import (
    MAX_NAME_LENGTH,
    CategoryError,
    CategoryNotFound,
    create_category,
    delete_category,
    rename_category,
)
from app.services.sync_service import refresh_net_worth
from app.services.transaction_edit_service import category_tree

router = APIRouter(prefix="/categories", tags=["categories"])


class CreateCategoryRequest(BaseModel):
    name: str = Field(max_length=MAX_NAME_LENGTH * 2)  # trimmed and checked again by the service
    parent_id: UUID | None = None


class RenameCategoryRequest(BaseModel):
    name: str = Field(max_length=MAX_NAME_LENGTH * 2)


def _category_dict(category: Category) -> dict:
    return {
        "id": str(category.id),
        "name": category.name,
        "type": category.type,
        "parent_id": str(category.parent_category_id) if category.parent_category_id else None,
        "custom": True,
    }


@router.get("")
def list_categories(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return {"categories": category_tree(db, user.id)}


@router.post("", status_code=status.HTTP_201_CREATED)
def add_category(body: CreateCategoryRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        category = create_category(db, user.id, body.name, body.parent_id)
    except CategoryError as e:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    return _category_dict(category)


@router.patch("/{category_id}")
def edit_category(
    category_id: UUID,
    body: RenameCategoryRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        category = rename_category(db, user.id, category_id, body.name)
    except CategoryNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    except CategoryError as e:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    return _category_dict(category)


@router.delete("/{category_id}")
def remove_category(category_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        moved = delete_category(db, user.id, category_id)
    except CategoryNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "category not found")
    except CategoryError as e:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    refresh_net_worth(db, user.id)  # commits, and keeps spending-goal progress current
    return {"recategorized": moved}
