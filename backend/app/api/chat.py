import json
import logging
import math
import queue
import re
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
    kind: str | None = None  # "income" lists income rows; default spending


class Searched(BaseModel):
    """What an empty search looked through (claude_agent._searched)."""

    what: str
    range: str
    accounts: list[str] = []


class ChatSource(BaseModel):
    tool: str
    label: str
    query: SourceQuery | None = None
    searched: Searched | None = None


class Citation(BaseModel):
    """A dollar figure in the reply text and the number of the source
    (1-based, in `sources` order) it was found in."""

    text: str
    source: int


class ViewLink(BaseModel):
    """A picture that didn't fit in the answer's one chart, as a link.
    view: transactions | cash_flow."""

    view: str
    label: str
    query: SourceQuery | None = None


class ClarifyChoice(BaseModel):
    label: str


class Clarify(BaseModel):
    question: str
    choices: list[ClarifyChoice]


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


class ChartPoint(BaseModel):
    label: str
    value: float
    share: float | None = None
    partial: bool = False
    query: SourceQuery | None = None


class ChartChange(BaseModel):
    difference: float
    percent_change: float | None = None
    direction: str


class ChartSpec(BaseModel):
    """A small chart under a reply, built server-side from a fresh query (see
    tools.show_chart). kind: breakdown | compare | trend."""

    kind: str
    title: str
    period: str | None = None
    unit: str = "usd"
    points: list[ChartPoint]
    change: ChartChange | None = None
    # The transactions the whole chart is drawn from (None for a net trend,
    # which links to Cash flow instead).
    query: SourceQuery | None = None
    group_by: str | None = None


class AnswerParts(BaseModel):
    """Everything that renders around a reply's text, derived from the
    turn's persisted tool calls (see _answer_parts)."""

    sources: list[ChatSource] = []
    citations: list[Citation] = []
    goal_proposal: GoalProposal | None = None
    charts: list[ChartSpec] = []
    links: list[ViewLink] = []
    clarify: Clarify | None = None


class ChatResponse(AnswerParts):
    conversation_id: UUID
    reply: str


class ConversationSummary(BaseModel):
    conversation_id: UUID
    preview: str
    last_message_at: datetime
    message_count: int


class ConversationMessage(AnswerParts):
    role: str
    content: str
    created_at: datetime


# Entries that aren't data sources: a chart shows itself below the reply, and
# a clarifying question shows as its choices.
_INTERNAL_TOOLS = ("show_chart", "ask_clarifying_question")


def _public_entries(raw: list[dict] | None) -> list[dict]:
    return [entry for entry in raw or [] if entry["tool"] not in _INTERNAL_TOOLS]


def _public_sources(raw: list[dict] | None) -> list[dict]:
    public = []
    for entry in _public_entries(raw):
        source = {"tool": entry["tool"], "label": entry["label"]}
        for key in ("query", "searched"):
            if entry.get(key):
                source[key] = entry[key]
        public.append(source)
    return public


# Same pattern the web client splits figures out of the text with
# (AssistantText.tsx), so both sides agree on what one figure is.
_MONEY = re.compile(r"-?\$[\d,]+(?:\.\d+)?")


def _citations(reply: str, raw: list[dict] | None) -> list[dict]:
    """Number every dollar figure in the reply to the source it came from:
    the first source (in call order) whose result holds that exact amount,
    else one that rounds to it when the figure has no cents ("about $71").
    A figure no source holds stays uncited, and the client shows it plainly
    rather than as a checked number."""
    entries = _public_entries(raw)
    citations, seen = [], set()
    for match in _MONEY.finditer(reply or ""):
        text = match.group()
        if text in seen:
            continue
        seen.add(text)
        amount = abs(float(text.replace("$", "").replace(",", "")))
        has_cents = "." in text
        for exact in (True, False):
            if not exact and has_cents:
                break
            number = next(
                (
                    i + 1
                    for i, entry in enumerate(entries)
                    if any((f == round(amount, 2)) if exact else (math.floor(f + 0.5) == amount) for f in entry.get("figures", []))
                ),
                None,
            )
            if number:
                citations.append({"text": text, "source": number})
                break
    return citations


def _goal_proposal(raw: list[dict] | None) -> dict | None:
    for entry in reversed(raw or []):
        proposal = entry.get("proposal")
        if proposal:
            return proposal
    return None


def _charts(raw: list[dict] | None) -> list[dict]:
    """At most one chart per reply (run_agent_turn turns any second one
    into a link); keep the last in case older rows had more."""
    charts = [entry["chart"] for entry in raw or [] if entry.get("chart")]
    return charts[-1:]


def _links(raw: list[dict] | None) -> list[dict]:
    links = []
    for entry in raw or []:
        link = entry.get("link")
        if link and link not in links:
            links.append(link)
    return links


def _clarify(raw: list[dict] | None) -> dict | None:
    for entry in reversed(raw or []):
        if entry.get("clarify"):
            return entry["clarify"]
    return None


def _answer_parts(reply: str, raw: list[dict] | None) -> dict:
    return {
        "sources": _public_sources(raw),
        "citations": _citations(reply, raw),
        "goal_proposal": _goal_proposal(raw),
        "charts": _charts(raw),
        "links": _links(raw),
        "clarify": _clarify(raw),
    }


@router.post("", response_model=ChatResponse, dependencies=[Depends(limit_chat_by_user)])
def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    conversation_id = body.conversation_id or uuid4()
    reply, sources = chat_service.send_message(db, user.id, conversation_id, body.message)
    return ChatResponse(conversation_id=conversation_id, reply=reply, **_answer_parts(reply, sources))


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
            response = ChatResponse(conversation_id=conversation_id, reply=reply, **_answer_parts(reply, sources))
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
            "created_at": row["created_at"],
            **_answer_parts(row["content"], row.get("sources")),
        }
        for row in messages
    ]
