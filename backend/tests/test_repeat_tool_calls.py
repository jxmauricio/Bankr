"""A model that forgets the window ("last month" -> no window at all) gets
this month back, and used to re-send the identical call until the round
cap, then return nothing. run_agent_turn now flags the default window,
answers a repeated call without re-running it, and never returns an empty
reply."""

from app.agent import claude_agent
from app.services.sync_service import sync_user_accounts
from tests.fake_aggregator import FakeAggregatorClient


class LoopingClient:
    """Sends the same tool calls in order, records what came back, then
    replies with final_text."""

    def __init__(self, calls: list[tuple[str, dict]], final_text: str = "Done."):
        self.calls = calls
        self.final_text = final_text
        self.results: list[dict] = []

    def run_turn(self, system, tools, history, call_tool, on_text=None):
        for name, tool_input in self.calls:
            self.results.append(call_tool(name, tool_input))
        return self.final_text


def _turn(db, user, monkeypatch, client):
    sync_user_accounts(db, user.id, "fake-token", aggregator=FakeAggregatorClient())
    monkeypatch.setattr(claude_agent, "_client", client)
    return claude_agent.run_agent_turn(db, user.id, [{"role": "user", "content": "groceries last month?"}])


def test_a_repeated_call_is_not_run_again_and_says_the_window_defaulted(db, user, monkeypatch):
    call = ("get_spending", {"category": "Groceries", "group_by": "merchant"})
    client = LoopingClient([call, call, call])

    _, sources = _turn(db, user, monkeypatch, client)

    first, *repeats = client.results
    assert "this_month (the default)" in first["window_note"]
    assert all(r["repeated_call"] for r in repeats)
    assert "this_month by default" in repeats[0]["message"]
    assert len(sources) == 1


def test_a_call_with_a_window_gets_no_default_note(db, user, monkeypatch):
    client = LoopingClient([("get_spending", {"window": "last_month", "category": "Groceries"})])

    _turn(db, user, monkeypatch, client)

    assert "window_note" not in client.results[0]


def test_same_tool_with_different_arguments_still_runs(db, user, monkeypatch):
    client = LoopingClient(
        [
            ("get_spending", {"category": "Groceries"}),
            ("get_spending", {"category": "Groceries", "window": "last_month"}),
        ]
    )

    _, sources = _turn(db, user, monkeypatch, client)

    assert not any(r.get("repeated_call") for r in client.results)
    assert len(sources) == 2


def test_an_empty_reply_becomes_the_fallback(db, user, monkeypatch):
    client = LoopingClient([("get_net_worth", {})], final_text="  ")

    reply, _ = _turn(db, user, monkeypatch, client)

    assert reply == claude_agent.EMPTY_REPLY_FALLBACK
