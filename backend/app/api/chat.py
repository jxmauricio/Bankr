from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db.base import get_db
from app.db.models import User
from app.services import chat_service

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    conversation_id: UUID | None = None


class ChatSource(BaseModel):
    tool: str
    label: str


class ChatResponse(BaseModel):
    conversation_id: UUID
    reply: str
    sources: list[ChatSource] = []


class ConversationSummary(BaseModel):
    conversation_id: UUID
    preview: str
    last_message_at: datetime
    message_count: int


class ConversationMessage(BaseModel):
    role: str
    content: str
    sources: list[ChatSource] = []
    created_at: datetime


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    conversation_id = body.conversation_id or uuid4()
    reply, sources = chat_service.send_message(db, user.id, conversation_id, body.message)
    return ChatResponse(conversation_id=conversation_id, reply=reply, sources=sources)


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    return chat_service.list_conversations(db, user.id)


@router.get("/conversations/{conversation_id}", response_model=list[ConversationMessage])
def get_conversation(
    conversation_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    messages = chat_service.get_conversation(db, user.id, conversation_id)
    if not messages:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return messages
