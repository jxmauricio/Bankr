"""The OpenAI-compatible client's streamed tool loop, against canned stream
chunks instead of a real LLM API."""

from types import SimpleNamespace

from app.agent.agent_client import ToolSpec
from app.agent.providers import OpenRouterAgentClient

_TOOLS = [ToolSpec(name="get_net_worth", description="", parameters={"type": "object", "properties": {}})]


def _chunk(content=None, tool_calls=None, reasoning=None, usage=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls, reasoning=reasoning)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)], usage=usage, provider="SomeHost")


def _tool_call_piece(index, id=None, name=None, arguments=None):
    return SimpleNamespace(index=index, id=id, function=SimpleNamespace(name=name, arguments=arguments))


class _Stream:
    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return iter(self._chunks)

    def __exit__(self, *exc):
        return False


def test_streamed_tool_loop_sends_text_resets_and_keeps_reasoning(monkeypatch):
    client = OpenRouterAgentClient(api_key="key", model="some/model")
    rounds = [
        # Round 0: thinks, says a few words, then calls a tool in fragments.
        [
            _chunk(reasoning="Need the "),
            _chunk(reasoning="balance."),
            _chunk(content="Let me check."),
            _chunk(tool_calls=[_tool_call_piece(0, id="call-1", name="get_net", arguments='{"a"')]),
            _chunk(tool_calls=[_tool_call_piece(0, name="_worth", arguments=": 1}")]),
        ],
        # Round 1: the answer.
        [_chunk(content="You have "), _chunk(content="$2,100.")],
    ]
    requests = []

    def fake_create(**kwargs):
        requests.append(kwargs)
        return _Stream(rounds[len(requests) - 1])

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    received, tool_calls = [], []

    reply = client.run_turn(
        "system",
        _TOOLS,
        [{"role": "user", "content": "net worth?"}],
        call_tool=lambda name, args: tool_calls.append((name, args)) or {"net_worth": 2100},
        on_text=received.append,
    )

    assert reply == "You have $2,100."
    assert received == ["Let me check.", None, "You have ", "$2,100."]
    assert tool_calls == [("get_net_worth", {"a": 1})]
    assert all(r["stream"] is True for r in requests)
    # The first round's reasoning and tool call go back to the model as one message.
    assistant = requests[1]["messages"][2]
    assert assistant["reasoning"] == "Need the balance."
    assert assistant["tool_calls"] == [
        {"id": "call-1", "type": "function", "function": {"name": "get_net_worth", "arguments": '{"a": 1}'}}
    ]


def test_without_on_text_nothing_is_streamed(monkeypatch):
    client = OpenRouterAgentClient(api_key="key", model="some/model")
    requests = []

    def fake_create(**kwargs):
        requests.append(kwargs)
        message = SimpleNamespace(model_dump=lambda exclude_none=True: {"role": "assistant", "content": "hi"})
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)

    assert client.run_turn("system", _TOOLS, [{"role": "user", "content": "hello"}], call_tool=lambda n, a: {}) == "hi"
    assert "stream" not in requests[0]
