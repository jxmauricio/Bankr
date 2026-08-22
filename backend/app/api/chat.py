from uuid import UUID, uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services.chat_service import send_message

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: UUID | None = None


class ChatResponse(BaseModel):
    conversation_id: UUID
    reply: str


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    conversation_id = body.conversation_id or uuid4()
    reply = send_message(db, user.id, conversation_id, body.message)
    return ChatResponse(conversation_id=conversation_id, reply=reply)
