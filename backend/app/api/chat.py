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


class GoalProposal(BaseModel):
    type: str
    target_amount: float
    target_date: str | None = None
    replaces_existing: bool = False
    at_limit: bool = False
    active_count: int = 0
    slots_remaining: int = 5


class ChatResponse(BaseModel):
    conversation_id: UUID
    reply: str
    sources: list[ChatSource] = []
    goal_proposal: GoalProposal | None = None


class ConversationSummary(BaseModel):
    conversation_id: UUID
    preview: str
    last_message_at: datetime
    message_count: int


class ConversationMessage(BaseModel):
    role: str
    content: str
    sources: list[ChatSource] = []
    goal_proposal: GoalProposal | None = None
    created_at: datetime


def _public_sources(raw: list[dict] | None) -> list[dict]:
    return [{"tool": entry["tool"], "label": entry["label"]} for entry in (raw or [])]


def _goal_proposal(raw: list[dict] | None) -> dict | None:
    for entry in reversed(raw or []):
        proposal = entry.get("proposal")
        if proposal:
            return proposal
    return None


@router.post("", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    conversation_id = body.conversation_id or uuid4()
    reply, sources = chat_service.send_message(db, user.id, conversation_id, body.message)
    return ChatResponse(
        conversation_id=conversation_id,
        reply=reply,
        sources=_public_sources(sources),
        goal_proposal=_goal_proposal(sources),
    )


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
    return [
        {
            "role": row["role"],
            "content": row["content"],
            "sources": _public_sources(row.get("sources")),
            "goal_proposal": _goal_proposal(row.get("sources")),
            "created_at": row["created_at"],
        }
        for row in messages
    ]
