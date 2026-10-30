"""Prompt caching, checked at the request-kwargs level without hitting a
real LLM API (same approach as test_extended_thinking.py): Claude requests
carry cache_control markers on the static prefix, the per-turn date stays
outside it, and every client reports cached tokens."""

import logging
from types import SimpleNamespace

from app.agent.agent_client import ToolSpec
from app.agent.providers import CACHE_CONTROL, AnthropicAgentClient, OpenAICompatibleAgentClient, OpenRouterAgentClient

_TOOLS = [
    ToolSpec(name="get_net_worth", description="", parameters={"type": "object", "properties": {}}),
    ToolSpec(name="get_spending", description="", parameters={"type": "object", "properties": {}}),
]
_DATE = "\n\nToday is Friday, October 30, 2026 in the user's timezone."


def _anthropic_text(text: str, **usage):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn", usage=SimpleNamespace(**usage)
    )


def _openai_text(text: str, usage=None):
    message = SimpleNamespace(model_dump=lambda exclude_none=True: {"role": "assistant", "content": text})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _capture(monkeypatch, target, responses):
    calls = []

    def fake_create(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(target, "create", fake_create)
    return calls


def test_anthropic_marks_the_static_prompt_and_last_tool_and_leaves_the_date_uncached(monkeypatch):
    client = AnthropicAgentClient(api_key="key", model="claude-sonnet-5")
    calls = _capture(monkeypatch, client._client.messages, [_anthropic_text("hi")])

    client.run_turn("STATIC PROMPT", _TOOLS, [{"role": "user", "content": "hello"}], lambda n, a: {}, system_context=_DATE)

    [request] = calls
    assert request["system"] == [
        {"type": "text", "text": "STATIC PROMPT", "cache_control": CACHE_CONTROL},
        {"type": "text", "text": _DATE},
    ]
    assert request["tools"][-1]["cache_control"] == CACHE_CONTROL
    assert "cache_control" not in request["tools"][0]
    # The question itself is marked too, so the next round reads it back.
    assert request["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "hello", "cache_control": CACHE_CONTROL}]}
    ]


def test_anthropic_moves_the_message_marker_to_the_newest_message_each_round(monkeypatch):
    """Tool results are cached for the next round, and only the last message
    ever carries a marker -- Anthropic allows four breakpoints per request."""
    client = AnthropicAgentClient(api_key="key", model="claude-sonnet-5")
    tool_round = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", id="tu-1", name="get_net_worth", input={})],
        stop_reason="tool_use",
        usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )
    calls = _capture(monkeypatch, client._client.messages, [tool_round, _anthropic_text("done")])

    client.run_turn("STATIC", _TOOLS, [{"role": "user", "content": "hello"}], lambda n, a: {"net_worth": 1})

    first, second = calls
    assert first["system"] == second["system"] and first["tools"] == second["tools"]
    assert second["messages"][0] == {"role": "user", "content": "hello"}
    [tool_result] = second["messages"][-1]["content"]
    assert tool_result["type"] == "tool_result" and tool_result["cache_control"] == CACHE_CONTROL
    marked = [m for m in second["messages"] if isinstance(m["content"], list) and any(
        isinstance(b, dict) and "cache_control" in b for b in m["content"]
    )]
    assert len(marked) == 1


def test_anthropic_without_caching_sends_one_plain_system_string(monkeypatch):
    client = AnthropicAgentClient(api_key="key", model="claude-sonnet-5", prompt_caching=False)
    calls = _capture(monkeypatch, client._client.messages, [_anthropic_text("hi")])

    client.run_turn("STATIC", _TOOLS, [{"role": "user", "content": "hello"}], lambda n, a: {}, system_context=_DATE)

    [request] = calls
    assert request["system"] == "STATIC" + _DATE
    assert all("cache_control" not in t for t in request["tools"])
    # (The same list the client goes on to append its reply to.)
    assert request["messages"][0] == {"role": "user", "content": "hello"}


def test_anthropic_reports_cache_reads_and_writes_and_the_whole_prompt_as_input(monkeypatch, caplog):
    client = AnthropicAgentClient(api_key="key", model="claude-sonnet-5")
    _capture(
        monkeypatch,
        client._client.messages,
        [_anthropic_text("hi", input_tokens=40, output_tokens=7, cache_read_input_tokens=3000, cache_creation_input_tokens=200)],
    )
    usages = []

    with caplog.at_level(logging.INFO, logger="app.agent.providers"):
        client.run_turn("STATIC", _TOOLS, [{"role": "user", "content": "hello"}], lambda n, a: {}, on_usage=usages.append)

    assert usages == [{"input": 3240, "output": 7, "cached": 3000, "cache_write": 200}]
    [line] = [r.getMessage() for r in caplog.records if r.name == "app.agent.providers"]
    assert "tokens in=3240 out=7 reasoning=None cached=3000 cache_write=200," in line


def test_openrouter_claude_model_marks_the_static_system_part_only(monkeypatch):
    client = OpenRouterAgentClient(api_key="key", model="anthropic/claude-sonnet-5")
    calls = _capture(monkeypatch, client._client.chat.completions, [_openai_text("hi")])

    client.run_turn("STATIC", _TOOLS, [{"role": "user", "content": "hello"}], lambda n, a: {}, system_context=_DATE)

    [request] = calls
    assert request["messages"][0] == {
        "role": "system",
        "content": [
            {"type": "text", "text": "STATIC", "cache_control": CACHE_CONTROL},
            {"type": "text", "text": _DATE},
        ],
    }
    assert request["messages"][1] == {"role": "user", "content": "hello"}


def test_openrouter_other_models_get_the_same_plain_system_text_as_before(monkeypatch):
    """DeepSeek and friends cache a repeated prefix on their own; the request
    stays plain text with the date at the very end of it."""
    client = OpenRouterAgentClient(api_key="key", model="deepseek/deepseek-v4-flash-0731")
    calls = _capture(monkeypatch, client._client.chat.completions, [_openai_text("hi"), _openai_text("hi")])

    for _ in range(2):
        client.run_turn("STATIC", _TOOLS, [{"role": "user", "content": "hello"}], lambda n, a: {}, system_context=_DATE)

    first, second = calls
    assert first["messages"][0] == {"role": "system", "content": "STATIC" + _DATE}
    assert first["messages"] == second["messages"] and first["tools"] == second["tools"]
    assert "cache_control" not in repr(first)


def test_openrouter_caching_can_be_turned_off_for_claude_models(monkeypatch):
    client = OpenRouterAgentClient(api_key="key", model="anthropic/claude-sonnet-5", prompt_caching=False)
    calls = _capture(monkeypatch, client._client.chat.completions, [_openai_text("hi")])

    client.run_turn("STATIC", _TOOLS, [{"role": "user", "content": "hello"}], lambda n, a: {}, system_context=_DATE)

    assert calls[0]["messages"][0] == {"role": "system", "content": "STATIC" + _DATE}


def test_openai_compatible_reports_cached_tokens_and_cache_writes(monkeypatch, caplog):
    client = OpenAICompatibleAgentClient(api_key="key", base_url="https://example.test/v1", model="deepseek-chat")
    usage = SimpleNamespace(
        prompt_tokens=3200,
        completion_tokens=50,
        prompt_tokens_details=SimpleNamespace(cached_tokens=2944, cache_write_tokens=None),
    )
    _capture(monkeypatch, client._client.chat.completions, [_openai_text("hi", usage=usage)])
    usages = []

    with caplog.at_level(logging.INFO, logger="app.agent.providers"):
        client.run_turn("STATIC", [], [{"role": "user", "content": "hello"}], lambda n, a: {}, on_usage=usages.append)

    assert usages[0]["cached"] == 2944 and usages[0]["input"] == 3200
    [line] = [r.getMessage() for r in caplog.records if r.name == "app.agent.providers"]
    assert "cached=2944 cache_write=None" in line
