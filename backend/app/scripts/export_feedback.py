"""Dump rated chat replies as JSON lines, so a bad answer can become an
eval task (tests/evals/tasks.py).

    python -m app.scripts.export_feedback                    # every rating
    python -m app.scripts.export_feedback --rating down --since 2026-10-01 > bad.jsonl

One line per rated reply: the question, the earlier turns it followed (as
an eval Task's history), the reply, the rating and reason, the sources
behind the reply (every tool call with its label and the dollar figures it
returned), and which figures were cited or unverified. No email or other
account details are included. Runs against whatever DATABASE_URL points at.
"""

import argparse
import json
import sys
from datetime import date, datetime, time, timezone

from sqlalchemy.orm import Session

from app.api.chat import _citations, _uncited_figures
from app.db.base import SessionLocal
from app.db.models import ChatFeedback, ChatMessage

# Earlier turns kept as history, like an eval Task's: enough for a follow-up.
HISTORY_MESSAGES = 4


def export_feedback(db: Session, rating: str | None = None, since: date | None = None) -> list[dict]:
    """Rated replies, oldest rating first."""
    query = db.query(ChatFeedback, ChatMessage).join(ChatMessage, ChatMessage.id == ChatFeedback.message_id)
    if rating:
        query = query.filter(ChatFeedback.rating == rating)
    if since:
        query = query.filter(ChatFeedback.created_at >= datetime.combine(since, time.min, tzinfo=timezone.utc))
    rows = []
    for feedback, reply in query.order_by(ChatFeedback.created_at).all():
        earlier = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.user_id == reply.user_id,
                ChatMessage.conversation_id == reply.conversation_id,
                ChatMessage.created_at < reply.created_at,
            )
            .order_by(ChatMessage.created_at.desc())
            .limit(HISTORY_MESSAGES + 1)
            .all()
        )
        earlier.reverse()
        question = earlier.pop() if earlier and earlier[-1].role == "user" else None
        sources = reply.tool_calls or []
        citations = _citations(reply.content, sources)
        rows.append(
            {
                "message_id": str(reply.id),
                "conversation_id": str(reply.conversation_id),
                "rating": feedback.rating,
                "reason": feedback.reason,
                "rated_at": feedback.created_at.isoformat(),
                "question": question.content if question else None,
                "history": [{"role": m.role, "content": m.content} for m in earlier],
                "reply": reply.content,
                "sources": sources,
                "citations": citations,
                "uncited_figures": _uncited_figures(reply.content, sources, citations),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export rated Bankr chat replies as JSON lines.")
    parser.add_argument("--rating", choices=["up", "down"], help="only this rating")
    parser.add_argument("--since", type=date.fromisoformat, help="only ratings on or after YYYY-MM-DD")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        rows = export_feedback(db, rating=args.rating, since=args.since)
    for row in rows:
        print(json.dumps(row, default=str))
    print(f"Exported {len(rows)} rated repl{'y' if len(rows) == 1 else 'ies'}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
