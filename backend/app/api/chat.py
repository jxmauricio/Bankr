import json
import logging
import queue
import threading
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.auth import get_current_user
from app.db.base import get_db, get_session_factory
from app.db.models import User
from app.rate_limit import limit_chat_by_user
from app.services import chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

# Idle gap after which the stream sends an SSE comment, so a proxy doesn't
# close a connection that's just waiting on a slow model round.
_KEEPALIVE_SECONDS = 15


class ChatRequest(BaseModel):
    message: str
    conversation_id: UUID | None = None


class SourceQuery(BaseModel):
    """The exact transaction filter behind a figure, so the client can show
    the rows that add up to it (see claude_agent._source_query)."""

    start: str
    end: str
    category: str | None = None
    merchant: str | None = None


class ChatSource(BaseModel):
    tool: str
    label: str
    query: SourceQuery | None = None


class GoalProposal(BaseModel):
    type: str
    name: str | None = None
    target_amount: float = 0
    target_date: str | None = None
    category: str | None = None
    window: str | None = None
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
    public = []
    for entry in raw or []:
        source = {"tool": entry["tool"], "label": entry["label"]}
        if entry.get("query"):
            source["query"] = entry["query"]
        public.append(source)
    return public


def _goal_proposal(raw: list[dict] | None) -> dict | None:
    for entry in reversed(raw or []):
        proposal = entry.get("proposal")
        if proposal:
            return proposal
    return None


@router.post("", response_model=ChatResponse, dependencies=[Depends(limit_chat_by_user)])
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


@router.post("/stream", dependencies=[Depends(limit_chat_by_user)])
def chat_stream(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session_factory: sessionmaker = Depends(get_session_factory),
) -> StreamingResponse:
    """Same turn as POST /chat, delivered as Server-Sent Events so the client
    can show progress during a multi-round turn:

      event: status  data: {"label": "Looking up Dining spending…"}  (0..n)
      event: done    data: <the ChatResponse JSON>                    (once)
      event: error   data: {"message": "..."}                         (instead of done)

    The turn runs in a worker thread with its own DB session (this request's
    session is closed before the body streams). If the client disconnects the
    turn still finishes and is saved, so the reply is there when they reopen
    the conversation."""
    conversation_id = body.conversation_id or uuid4()
    user_id = user.id
    events: queue.Queue[tuple[str, dict] | None] = queue.Queue()

    def run_turn() -> None:
        try:
            with session_factory() as db:
                reply, sources = chat_service.send_message(
                    db,
                    user_id,
                    conversation_id,
                    body.message,
                    on_status=lambda label: events.put(("status", {"label": label})),
                )
            response = ChatResponse(
                conversation_id=conversation_id,
                reply=reply,
                sources=_public_sources(sources),
                goal_proposal=_goal_proposal(sources),
            )
            events.put(("done", response.model_dump(mode="json")))
        except Exception:
            logger.exception("Streaming chat turn failed")
            events.put(("error", {"message": "Bankr couldn't respond. Try again."}))
        finally:
            events.put(None)

    def stream():
        threading.Thread(target=run_turn, daemon=True).start()
        while True:
            try:
                item = events.get(timeout=_KEEPALIVE_SECONDS)
            except queue.Empty:
                yield ": keepalive\n\n"
                continue
            if item is None:
                return
            event, data = item
            yield f"event: {event}\ndata: {json.dumps(data)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
