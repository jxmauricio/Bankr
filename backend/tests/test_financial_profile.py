from uuid import uuid4

from app.agent import claude_agent
from app.agent.claude_agent import SYSTEM_PROMPT, run_agent_turn
from app.db.models import User
from app.services.financial_profile import render_markdown, save_profile
from tests.fake_agent_client import FakeAgentClient


class RecordingAgentClient(FakeAgentClient):
    def __init__(self):
        super().__init__()
        self.system = ""
        self.static_system = ""

    def run_turn(self, system, tools, history, call_tool, system_context="", **_):
        self.system = system + system_context
        self.static_system = system
        return "ok"


def test_questions_render_markdown():
    md = render_markdown(
        {
            "path": "questions",
            "answers": {
                "age": 28,
                "occupation": "salaried",
                "monthly_income": 4200,
                "cash": 2400,
                "emergency_fund": 3500,
                "housing": "rent",
                "housing_payment": 1800,
                "debts": [{"name": "Student loans", "owed": 18000, "paid_off": 6000}],
                "investments": [{"name": "401(k)", "amount": 12000}],
                "goals": [{"name": "Trip", "target": 8000, "saved": 3200}],
                "knowledge": "somewhat",
                "lifestyle": "balanced",
            },
        }
    )
    assert md.startswith("# financial_profile.md")
    assert "Age: 28" in md
    assert "Salaried" in md
    assert "$4,200" in md
    assert "Cash on hand: $2,400" in md
    assert "Emergency fund: $3,500" in md
    assert "Housing: Rent $1,800 / month" in md
    assert "Student loans: still owed $18,000, paid off $6,000" in md
    assert "401(k): $12,000" in md
    assert "Trip: $3,200 of $8,000" in md
    assert "Somewhat" in md
    assert "Balanced" in md


def test_story_render_markdown():
    md = render_markdown({"path": "story", "story": "I freelance and want a house."})
    assert "Path: story" in md
    assert "I freelance and want a house." in md


def test_put_questions_and_chat_reads_profile_first(client, db, user, monkeypatch):
    r = client.put(
        "/financial-profile",
        json={
            "path": "questions",
            "answers": {
                "age": 31,
                "occupation": "contractor",
                "monthly_income": 5500.5,
                "cash": 900,
                "emergency_fund": 2500,
                "debts": [],
                "investments": [],
                "goals": [{"name": "Trip", "target": 4000, "saved": 1100}],
                "knowledge": "nothing",
                "lifestyle": "ball",
            },
        },
    )
    assert r.status_code == 200
    assert r.json()["completed"] is True
    assert "# financial_profile.md" in r.json()["markdown"]

    rec = RecordingAgentClient()
    monkeypatch.setattr(claude_agent, "_client", rec)
    run_agent_turn(db, user.id, [{"role": "user", "content": "?"}])
    assert rec.static_system == SYSTEM_PROMPT
    tail = rec.system[len(SYSTEM_PROMPT) :]
    assert tail.index("financial_profile.md") < tail.index("Today is")
    assert "Contractor" in tail
    assert "Cash on hand: $900" in tail
    assert "Emergency fund: $2,500" in tail
    assert "Trip: $1,100 of $4,000" in tail
    assert "Let's Ball Out" in tail


def test_put_story(client, db, user):
    r = client.put("/financial-profile", json={"path": "story", "story": "Paid weekly, saving for a dog."})
    assert r.status_code == 200
    got = client.get("/financial-profile").json()
    assert got["completed"] is True
    assert "saving for a dog" in got["markdown"]


def test_short_story_rejected(client, user):
    r = client.put("/financial-profile", json={"path": "story", "story": "hi"})
    assert r.status_code == 422


def test_other_users_profile_stays_out_of_chat(db, user, monkeypatch):
    other = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(other)
    db.commit()
    save_profile(db, other, "story", "Other person's secret plan", None)
    db.commit()

    rec = RecordingAgentClient()
    monkeypatch.setattr(claude_agent, "_client", rec)
    run_agent_turn(db, user.id, [{"role": "user", "content": "?"}])
    assert "secret plan" not in rec.system
