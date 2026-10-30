from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import proposal_service as ps

router = APIRouter(prefix="/proposals", tags=["proposals"])


@router.get("")
def list_proposals(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Changes a connected app (Claude, ChatGPT) proposed, waiting for the user."""
    return {"proposals": [ps.as_dict(p) for p in ps.list_pending(db, user.id)]}


@router.post("/{proposal_id}/confirm")
def confirm_proposal(proposal_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ps.as_dict(ps.confirm(db, user.id, proposal_id))
    except ps.ProposalNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
    except ps.ProposalError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))


@router.post("/{proposal_id}/dismiss")
def dismiss_proposal(proposal_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    try:
        return ps.as_dict(ps.dismiss(db, user.id, proposal_id))
    except ps.ProposalNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "proposal not found")
