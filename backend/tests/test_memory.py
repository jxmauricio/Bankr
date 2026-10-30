"""What Bankr remembers about the user: saved only by the user (in Settings
or by confirming a card), shown to the agent after the static prompt,
never holding account numbers or credentials, and never another user's."""

from uuid import uuid4

import pytest

from app.agent import claude_agent, tools
from app.agent.claude_agent import SYSTEM_PROMPT, run_agent_turn
from app.db.models import MemoryFact, User
from app.services import memory_service
from app.services.memory_service import FactError, add_fact, check_fact, user_facts
from tests.fake_agent_client import FakeAgentClient


class RecordingAgentClient(FakeAgentClient):
    def __init__(self, tool_calls=()):
        super().__init__()
        self.tool_calls = list(tool_calls)
        self.results: list[dict] = []
        self.system = ""
        self.static_system = ""

    def run_turn(self, system, tools, history, call_tool, system_context="", **_):
        # The whole prompt as the model reads it, and the cacheable part alone.
        self.system = system + system_context
        self.static_system = system
        for name, tool_input in self.tool_calls:
            self.results.append(call_tool(name, tool_input))
        return "ok"


def _other_user(db) -> User:
    other = User(email=f"{uuid4()}@example.com", apple_sub=str(uuid4()))
    db.add(other)
    db.commit()
    return other


def _turn(db, user, monkeypatch, tool_calls=()):
    client = RecordingAgentClient(tool_calls)
    monkeypatch.setattr(claude_agent, "_client", client)
    _, sources = run_agent_turn(db, user.id, [{"role": "user", "content": "?"}])
    return client, sources


# --- Service ---------------------------------------------------------------


def test_add_list_update_and_order_by_kind(db, user):
    add_fact(db, user.id, "Wants to keep dining under control", "priority")
    pay = add_fact(db, user.id, "  Paid every   other Friday ", "income")
    db.commit()

    facts = user_facts(db, user.id)
    assert [f.text for f in facts] == ["Paid every other Friday", "Wants to keep dining under control"]
    assert pay.source == "user"

    memory_service.update_fact(db, pay, text="Paid on the 1st and 15th")
    assert user_facts(db, user.id)[0].text == "Paid on the 1st and 15th"
    assert pay.updated_at >= pay.created_at


def test_replaces_overwrites_instead_of_adding(db, user):
    old = add_fact(db, user.id, "Paid every other Friday", "income")
    new = add_fact(db, user.id, "Paid on the 15th", "income", source="agent", replaces_id=old.id)
    assert new.id == old.id
    assert [(f.text, f.source) for f in user_facts(db, user.id)] == [("Paid on the 15th", "agent")]


def test_caps_length_count_and_duplicates(db, user, monkeypatch):
    with pytest.raises(FactError, match="characters"):
        check_fact("x" * (memory_service.MAX_FACT_CHARS + 1), "other")
    with pytest.raises(FactError, match="some text"):
        check_fact("   ", "other")
    with pytest.raises(FactError, match="kind"):
        check_fact("Has a dog", "pets")

    add_fact(db, user.id, "Has a dog", "household")
    with pytest.raises(FactError, match="already"):
        add_fact(db, user.id, "has a DOG", "household")

    monkeypatch.setattr(memory_service, "MAX_FACTS", 2)
    add_fact(db, user.id, "Rents, doesn't own", "household")
    with pytest.raises(FactError, match="up to 2"):
        add_fact(db, user.id, "Prefers short answers", "preference")


@pytest.mark.parametrize(
    "text",
    [
        "My checking account number is 123456789012",
        "Card 4111 1111 1111 1111",
        "Card 4111-1111-1111-1111",
        "SSN 123-45-6789",
        "My password is hunter2",
        "Bank login is jdoe / pw",
        "Routing number is on my checks",
        "PIN is 4321",
        "Passport expires next year",
        "Phone 4155550123",
    ],
)
def test_rejects_sensitive_identifiers(db, user, text):
    with pytest.raises(FactError, match="doesn't remember"):
        add_fact(db, user.id, text, "other")
    assert db.query(MemoryFact).count() == 0


@pytest.mark.parametrize(
    "text",
    [
        "Earns $120,000 a year",
        "Saving $1,500,000 for retirement by 2055",
        "Rent is due on the 1st",
        "Next paycheck 2026-11-06, then every other Friday",
        "Chase card ending 1234 is for groceries",
    ],
)
def test_keeps_ordinary_facts_with_numbers(db, user, text):
    assert add_fact(db, user.id, text, "other").text == text


# --- Prompt assembly ---------------------------------------------------------


def test_no_block_when_nothing_is_remembered(db, user, monkeypatch):
    client, _ = _turn(db, user, monkeypatch)
    assert "What you know about the user" not in client.system


def test_facts_come_after_the_static_prompt_and_date(db, user, monkeypatch):
    add_fact(db, user.id, "Paid every other Friday", "income")
    add_fact(db, user.id, "Has two kids", "household")
    db.commit()

    client, _ = _turn(db, user, monkeypatch)

    # The static prefix is untouched, so a cached prompt still matches.
    assert client.static_system == SYSTEM_PROMPT
    assert client.system.startswith(SYSTEM_PROMPT)
    tail = client.system[len(SYSTEM_PROMPT):]
    assert tail.index("Today is") < tail.index("What you know about the user")
    assert "- Pay & income: Paid every other Friday" in tail
    assert "- Household: Has two kids" in tail
    assert "never a source for a dollar figure" in tail


def test_prompt_only_holds_this_users_facts(db, user, monkeypatch):
    other = _other_user(db)
    add_fact(db, other.id, "Paid monthly on the 30th", "income")
    add_fact(db, user.id, "Paid every other Friday", "income")
    db.commit()

    client, _ = _turn(db, user, monkeypatch)
    assert "Paid every other Friday" in client.system
    assert "30th" not in client.system


# --- propose_memory ----------------------------------------------------------


def test_propose_memory_drafts_a_card_without_saving(db, user, monkeypatch):
    client, sources = _turn(db, user, monkeypatch, [("propose_memory", {"text": "Paid every other Friday", "kind": "income"})])

    assert client.results[0]["status"] == "proposed"
    assert sources[0]["label"] == "Proposed something to remember"
    assert sources[0]["action"] == {
        "kind": "memory",
        "text": "Paid every other Friday",
        "fact_kind": "income",
        "fact_kind_label": "Pay & income",
        "replaces_id": None,
        "replaces_text": None,
    }
    assert db.query(MemoryFact).count() == 0


def test_propose_memory_refuses_sensitive_text(db, user):
    result = tools.propose_memory(db, user.id, text="Account number 000123456789", kind="other")
    assert "doesn't remember" in result["error"]
    assert "action" not in result


def test_propose_memory_can_replace_only_the_users_own_fact(db, user):
    old = add_fact(db, user.id, "Paid every other Friday", "income")
    other = _other_user(db)
    add_fact(db, other.id, "Paid weekly", "income")
    db.commit()

    result = tools.propose_memory(db, user.id, text="Paid on the 15th", kind="income", replaces="paid every other friday")
    assert result["action"]["replaces_id"] == str(old.id)
    assert result["action"]["replaces_text"] == "Paid every other Friday"

    assert "error" in tools.propose_memory(db, user.id, text="Paid on the 15th", kind="income", replaces="Paid weekly")


def test_confirming_the_card_saves_it(client, db, user):
    action = tools.propose_memory(db, user.id, text="Paid every other Friday", kind="income")["action"]

    r = client.post("/memory", json={"text": action["text"], "kind": action["fact_kind"], "source": "agent"})
    assert r.status_code == 201, r.text
    assert r.json()["source"] == "agent"
    assert [f.text for f in user_facts(db, user.id)] == ["Paid every other Friday"]


def test_chat_response_carries_the_memory_card(client, db, user, monkeypatch):
    monkeypatch.setattr(
        claude_agent,
        "_client",
        RecordingAgentClient([("propose_memory", {"text": "Paid every other Friday", "kind": "income"})]),
    )
    r = client.post("/chat", json={"message": "I get paid every other Friday"})
    assert r.status_code == 200, r.text
    assert r.json()["action_proposal"]["kind"] == "memory"
    assert db.query(MemoryFact).count() == 0


# --- API and scoping ---------------------------------------------------------


def test_settings_crud(client, db, user):
    r = client.post("/memory", json={"text": "Prefers short answers", "kind": "preference"})
    assert r.status_code == 201
    fact_id = r.json()["id"]

    listed = client.get("/memory").json()
    assert [f["text"] for f in listed["facts"]] == ["Prefers short answers"]
    assert listed["kinds"]["income"] == "Pay & income"

    r = client.patch(f"/memory/{fact_id}", json={"text": "Prefers bullet points"})
    assert r.json()["text"] == "Prefers bullet points"

    r = client.patch(f"/memory/{fact_id}", json={"text": "My password is hunter2"})
    assert r.status_code == 422

    assert client.delete(f"/memory/{fact_id}").status_code == 204
    assert client.get("/memory").json()["facts"] == []


def test_api_rejects_sensitive_text(client):
    r = client.post("/memory", json={"text": "Card 4111 1111 1111 1111", "kind": "other"})
    assert r.status_code == 422
    assert "doesn't remember" in r.json()["detail"]


def test_cannot_see_edit_delete_or_replace_another_users_fact(client, db, user):
    other = _other_user(db)
    theirs = add_fact(db, other.id, "Paid weekly", "income")
    db.commit()

    assert client.get("/memory").json()["facts"] == []
    assert client.patch(f"/memory/{theirs.id}", json={"text": "hacked"}).status_code == 404
    assert client.delete(f"/memory/{theirs.id}").status_code == 404
    r = client.post("/memory", json={"text": "Paid monthly", "kind": "income", "replaces_id": str(theirs.id)})
    assert r.status_code == 404
    db.expire_all()
    assert db.get(MemoryFact, theirs.id).text == "Paid weekly"
