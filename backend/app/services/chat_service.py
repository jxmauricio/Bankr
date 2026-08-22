"""Persists chat turns around claude_agent.run_agent_turn.

Only the final (role, text) pair is persisted per turn, not intermediate
tool_use/tool_result exchanges -- run_agent_turn resolves those internally
and they're vendor-specific besides (see app/agent/agent_client.py). The
model re-calls tools as needed on the next question rather than needing
yesterday's tool call replayed, so this keeps ChatMessage.content a plain
string and history a plain role/content list, portable across LLM backends.
"""

from uuid import UUID

from sqlalchemy.orm import Session

from app.agent.claude_agent import run_agent_turn
from app.db.models import ChatMessage


def _conversation_history(db: Session, user_id: UUID, conversation_id: UUID) -> list[dict]:
    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.user_id == user_id, ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    return [{"role": row.role, "content": row.content} for row in rows]


def send_message(db: Session, user_id: UUID, conversation_id: UUID, message_text: str) -> str:
    history = _conversation_history(db, user_id, conversation_id)
    history.append({"role": "user", "content": message_text})

    db.add(ChatMessage(user_id=user_id, conversation_id=conversation_id, role="user", content=message_text))
    db.commit()

    assistant_text = run_agent_turn(db, user_id, history)

    db.add(ChatMessage(user_id=user_id, conversation_id=conversation_id, role="assistant", content=assistant_text))
    db.commit()
    return assistant_text
