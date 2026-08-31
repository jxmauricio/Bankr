"""Persists chat turns around claude_agent.run_agent_turn, and the read side
of that same data: list_conversations/get_conversation, so a user can browse
and reopen a past conversation (GET /chat/conversations[/:id] in
app/api/chat.py).

Only the final (role, text) pair is persisted as conversation history per
turn, not intermediate tool_use/tool_result exchanges -- run_agent_turn
resolves those internally and they're vendor-specific besides (see
app/agent/agent_client.py). The model re-calls tools as needed on the next
question rather than needing yesterday's tool call replayed, so this keeps
ChatMessage.content a plain string and history a plain role/content list,
portable across LLM backends. The *labels* of which tools backed a given
reply are a separate, lightweight thing we do keep (ChatMessage.tool_calls),
purely for the user-facing "sources" trail -- never fed back into history.
"""

from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agent.claude_agent import run_agent_turn
from app.db.models import ChatMessage

_PREVIEW_MAX_CHARS = 120


def _conversation_history(db: Session, user_id: UUID, conversation_id: UUID) -> list[dict]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in rows]


def send_message(db: Session, user_id: UUID, conversation_id: UUID, message_text: str) -> tuple[str, list[dict]]:
    """Returns (reply text, sources) -- see run_agent_turn for what sources is."""
    history = _conversation_history(db, user_id, conversation_id)
    history.append({"role": "user", "content": message_text})

    db.add(ChatMessage(user_id=user_id, conversation_id=conversation_id, role="user", content=message_text))
    db.commit()

    assistant_text, sources = run_agent_turn(db, user_id, history)

    db.add(
        ChatMessage(
            user_id=user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=assistant_text,
            tool_calls=sources or None,
        )
    )
    db.commit()
    return assistant_text, sources


def list_conversations(db: Session, user_id: UUID) -> list[dict]:
    """One row per conversation this user has had, newest activity first,
    with a preview drawn from their first message -- enough to recognize a
    past conversation in a history list without loading its full contents."""
    groups = (
        db.query(
            ChatMessage.conversation_id,
            func.max(ChatMessage.created_at).label("last_message_at"),
            func.count(ChatMessage.id).label("message_count"),
        )
        .filter(ChatMessage.user_id == user_id)
        .group_by(ChatMessage.conversation_id)
        .order_by(func.max(ChatMessage.created_at).desc())
        .all()
    )

    result = []
    for conversation_id, last_message_at, message_count in groups:
        first_message = (
            db.query(ChatMessage.content)
            .filter(
                ChatMessage.user_id == user_id,
                ChatMessage.conversation_id == conversation_id,
                ChatMessage.role == "user",
            )
            .order_by(ChatMessage.created_at)
            .first()
        )
        preview = (first_message[0] if first_message else "")[:_PREVIEW_MAX_CHARS]
        result.append(
            {
                "conversation_id": conversation_id,
                "preview": preview,
                "last_message_at": last_message_at,
                "message_count": message_count,
            }
        )
    return result


def get_conversation(db: Session, user_id: UUID, conversation_id: UUID) -> list[dict]:
    """Full message history for one conversation (role, content, the same
    "sources" trail send_message returns, timestamp) -- used to resume a
    past conversation in the UI. Scoped to user_id, so asking for another
    user's conversation_id just comes back empty, same as it not existing."""
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return [
        {
            "role": row.role,
            "content": row.content,
            "sources": row.tool_calls or [],
            "created_at": row.created_at,
        }
        for row in rows
    ]
