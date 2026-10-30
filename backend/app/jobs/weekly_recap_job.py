"""Weekly recap: what came in, what went out, and what that did to each goal.

Same split as insights_job: every number is computed here in plain Python
from money_query and the goal helpers, and Claude only writes the short
"Bankr's take" paragraph from those numbers. If the model can't be reached
the recap is still saved, without the paragraph.

Recaps are made on demand (the app asks for the latest one), or by
app/jobs/notifications_job.py when it pushes one. The week is Monday-Sunday
in the user's time zone; Sunday's own week counts from RECAP_READY_HOUR,
when the push goes out.
"""

import json
import logging
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agent import tools
from app.agent.agent_client import build_agent_client
from app.db.models import InsightLog, NetWorthSnapshot, User, WeeklyRecap
from app.services import money_query as mq
from app.services.goal_service import SAVE, TRACK_SPENDING

logger = logging.getLogger(__name__)

_client = build_agent_client()

RECAP_READY_HOUR = 18
TOP_CATEGORIES = 5
TOP_ROWS = 3
# Weeks before this one that make up "usual" for a category.
USUAL_WEEKS = 4
WEEKS_PER_MONTH = 52 / 12


def _money(value) -> float:
    return round(float(value or 0), 2)


def _format_money(amount: float) -> str:
    return f"${abs(amount):,.2f}"


def latest_week(db: Session, user_id: UUID) -> mq.Window:
    """The newest week that's ready: this one from Sunday evening, else last week."""
    user = db.get(User, user_id)
    now = mq._now().astimezone(mq.user_zone(user.timezone if user else None))
    today = now.date()
    if today.weekday() == 6 and now.hour >= RECAP_READY_HOUR:
        end = today
    else:
        end = today - timedelta(days=today.weekday() + 1)
    return week_starting(end - timedelta(days=6))


def week_starting(start: date) -> mq.Window:
    return mq.Window(start, start + timedelta(days=6), "custom")


def has_history_for(db: Session, user_id: UUID, week: mq.Window) -> bool:
    earliest = mq._earliest_transaction_date(db, user_id)
    return earliest is not None and earliest <= week.end


def _assets_on(db: Session, user_id: UUID, day: date) -> float | None:
    snapshot = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.user_id == user_id, NetWorthSnapshot.date <= day)
        .order_by(NetWorthSnapshot.date.desc())
        .first()
    )
    return float(snapshot.total_assets) if snapshot else None


def _goal_facts(db: Session, user_id: UUID, week: mq.Window) -> list[dict]:
    """Each active goal and what this week did to it. A savings goal's
    progress is assets minus where they started (goal_service), so the
    week's change is the change in assets across it."""
    goals = []
    latest = _assets_on(db, user_id, date.max)
    before = _assets_on(db, user_id, week.start - timedelta(days=1))
    after = _assets_on(db, user_id, week.end)
    for goal in tools.get_goal_progress(db, user_id)["goals"]:
        if goal["type"] == SAVE:
            saved = goal["current_progress_amount"]
            if latest is not None and after is not None:
                # Progress as of the week's end, not the latest sync.
                saved -= latest - after
            goals.append(
                {
                    "id": goal["id"],
                    "type": SAVE,
                    "name": goal["name"],
                    "target_amount": goal["target_amount"],
                    "saved": _money(saved),
                    "change": _money(after - before) if before is not None and after is not None else None,
                    "target_date": goal["target_date"],
                    "on_pace": goal.get("on_pace"),
                }
            )
        elif goal["type"] == TRACK_SPENDING:
            week_spent = None
            if goal.get("category"):
                try:
                    week_spent = mq.spend_query(db, user_id, week, mq.resolve_category(db, goal["category"], user_id))[
                        "total_spent"
                    ]
                except mq.QueryError:
                    pass
            goals.append(
                {
                    "id": goal["id"],
                    "type": TRACK_SPENDING,
                    "name": goal["name"],
                    "category": goal.get("category"),
                    "window_label": goal.get("window_label"),
                    # Null, not 0, for a tracker with no limit: a "$0 limit" reads as a target.
                    "target_amount": goal["target_amount"] or None,
                    "spent": goal["current_progress_amount"],
                    "remaining": goal.get("remaining_amount"),
                    "over_budget": goal.get("over_budget", False),
                    "on_pace": goal.get("on_pace"),
                    "week_spent": week_spent,
                }
            )
    return goals


def compute_recap_facts(db: Session, user_id: UUID, week: mq.Window) -> dict:
    flow = mq.cash_flow(db, user_id, week)
    money_in = _money(flow["income"] + flow["transfer_in"])
    money_out = _money(flow["spending"] + flow["transfer_out"])

    average = mq.average_cash_flow(db, user_id)
    typical_week = None if average["partial"] else _money(average["spending"] / WEEKS_PER_MONTH)

    earliest = mq._earliest_transaction_date(db, user_id)
    usual_window = mq.Window(week.start - timedelta(days=7 * USUAL_WEEKS), week.start - timedelta(days=1), "custom")
    usual: dict[str, float] = {}
    if earliest is not None and earliest <= usual_window.start:
        for group in mq.spend_query(db, user_id, usual_window, group_by="category")["groups"]:
            usual[group["name"]] = _money(group["amount"] / USUAL_WEEKS)
    groups = mq.spend_query(db, user_id, week, group_by="category")["groups"]
    categories = [
        {"name": g["name"], "amount": g["amount"], "usual": usual.get(g["name"], 0.0) if usual else None}
        for g in groups
    ]
    # A single leftover category keeps its name rather than becoming "1 others".
    if len(categories) > TOP_CATEGORIES + 1:
        rest = categories[TOP_CATEGORIES:]
        categories = categories[:TOP_CATEGORIES] + [
            {"name": f"{len(rest)} others", "amount": _money(sum(c["amount"] for c in rest)), "usual": None}
        ]

    spending_rows = mq.find_transactions(db, user_id, week, limit=1000)["transactions"]
    biggest = sorted((t for t in spending_rows if t["amount"] < 0), key=lambda t: t["amount"])[:TOP_ROWS]
    income_rows = mq.find_transactions(db, user_id, week, limit=1000, category_type="income")["transactions"]
    incoming = sorted((t for t in income_rows if t["amount"] > 0), key=lambda t: t["amount"], reverse=True)[:TOP_ROWS]

    return {
        **week.as_dict(),
        "money_in": money_in,
        "money_out": money_out,
        "kept": flow["net"],
        "income": flow["income"],
        "spending": flow["spending"],
        "transfer_in": flow["transfer_in"],
        "transfer_out": flow["transfer_out"],
        "pending_spending": flow["pending_spending"],
        "typical_week_spending": typical_week,
        "transaction_count": flow["spending_transaction_count"] + flow["income_transaction_count"],
        "categories": categories,
        "biggest_purchases": [
            {"merchant": t["merchant_name"] or "Unknown merchant", "amount": -t["amount"], "date": t["date"], "category": t["category"]}
            for t in biggest
        ],
        "money_in_items": [
            {"merchant": t["merchant_name"] or "Income", "amount": t["amount"], "date": t["date"], "category": t["category"]}
            for t in incoming
        ]
        + [{"merchant": s["name"], "amount": s["amount"], "date": None, "category": "Transfers"} for s in flow["transfer_in_sources"]],
        "goals": _goal_facts(db, user_id, week),
        "data_as_of": mq.data_freshness(db, user_id),
    }


def headline_for(facts: dict) -> str:
    kept = facts["kept"]
    if kept >= 0:
        return f"You kept {_format_money(kept)}"
    # Not "spent": money out includes transfers out (to savings, a brokerage).
    return f"{_format_money(kept)} more went out than came in"


def teaser_for(facts: dict) -> str:
    """The push / notification line under the headline: plain facts, no model."""
    parts = [f"Spent {_format_money(facts['spending'])}"]
    typical = facts.get("typical_week_spending")
    if typical:
        change = round((facts["spending"] - typical) / typical * 100)
        if change <= -5:
            parts[0] += f", {-change}% under usual"
        elif change >= 5:
            parts[0] += f", {change}% over usual"
    for goal in facts["goals"]:
        if goal["type"] == SAVE and goal["target_amount"]:
            parts.append(f"{goal['name']} is now at {round(goal['saved'] / goal['target_amount'] * 100)}%")
            break
    return ". ".join(parts) + "."


def _write_summary(facts: dict) -> str | None:
    try:
        return _client.complete(
            system=(
                "Write a short weekly money recap for the user: 2-4 friendly, plain sentences. "
                "Say how the week went, what drove it, and what it did for their goals, then "
                "one practical nudge if a goal or limit needs it. Use only the exact numbers given, "
                "with dollar signs. No markdown, no lists, no investment advice.\n"
                "`spending` is what they spent. `money_out` also counts transfers out (to savings, "
                "a brokerage, a friend), so never call it spending. `kept` is money_in minus "
                "money_out. A spending goal with a null target_amount has no limit: just track it."
            ),
            user_message=json.dumps(facts, default=str),
        ).strip() or None
    except Exception:
        logger.exception("weekly recap summary failed")
        return None


def get_or_create_recap(db: Session, user_id: UUID, week: mq.Window, notify: bool = False) -> WeeklyRecap:
    """The saved recap for this week, made now if there isn't one. `notify`
    also logs it as an unread notification (the latest week only: a past
    week someone pages back to shouldn't light up the bell)."""
    recap = _find(db, user_id, week.start)
    if recap is None:
        facts = compute_recap_facts(db, user_id, week)
        recap = WeeklyRecap(
            user_id=user_id,
            week_start=week.start,
            week_end=week.end,
            headline=headline_for(facts),
            facts=facts,
            summary=_write_summary(facts),
        )
        db.add(recap)
        try:
            db.commit()
        except IntegrityError:
            # Two requests made the same week at once; keep the first.
            db.rollback()
            recap = _find(db, user_id, week.start)
    if notify:
        log_notification(db, recap)
    return recap


def notification_for(db: Session, recap: WeeklyRecap) -> InsightLog | None:
    return (
        db.query(InsightLog)
        .filter(InsightLog.user_id == recap.user_id, InsightLog.dedupe_key == dedupe_key(recap.week_start))
        .one_or_none()
    )


def dedupe_key(week_start: date) -> str:
    return f"weekly_recap:{week_start.isoformat()}"


def _find(db: Session, user_id: UUID, week_start: date) -> WeeklyRecap | None:
    return (
        db.query(WeeklyRecap)
        .filter(WeeklyRecap.user_id == user_id, WeeklyRecap.week_start == week_start)
        .one_or_none()
    )


def log_notification(db: Session, recap: WeeklyRecap, delivered_via: str = "in_app") -> None:
    if notification_for(db, recap) is not None:
        return
    label = mq.format_range(recap.week_start, recap.week_end).rsplit(", ", 1)[0]
    db.add(
        InsightLog(
            user_id=recap.user_id,
            type="weekly_recap",
            message=f"{label}: {recap.headline[0].lower()}{recap.headline[1:]}. {teaser_for(recap.facts)}",
            dedupe_key=dedupe_key(recap.week_start),
            delivered_via=delivered_via,
        )
    )
    db.commit()
