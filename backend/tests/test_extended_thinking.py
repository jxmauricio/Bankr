"""Verifies extended/reasoning thinking is wired into outbound API calls
correctly for the two providers that support it, without hitting a real
LLM API -- same spirit as test_agent_client.py, just one layer deeper
(the actual request kwargs, not just which class gets built)."""

from types import SimpleNamespace

from app.agent.providers import AnthropicAgentClient, OpenRouterAgentClient


def _text_response(text: str):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn")


def _openai_text_response(text: str):
    message = SimpleNamespace(content=text, tool_calls=None, model_dump=lambda exclude_none=True: {"role": "assistant", "content": text})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_anthropic_client_sends_thinking_params_when_enabled(monkeypatch):
    client = AnthropicAgentClient(
        api_key="key", model="claude-sonnet-5", extended_thinking=True, thinking_budget_tokens=3000
    )
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _text_response("hi")

    monkeypatch.setattr(client._client.messages, "create", fake_create)

    assert client.complete("system", "hello") == "hi"
    assert captured["max_tokens"] == 3000 + 200  # budget + the intended output size
    assert captured["extra_body"] == {"thinking": {"type": "enabled", "budget_tokens": 3000}}


def test_anthropic_client_omits_thinking_params_when_disabled(monkeypatch):
    client = AnthropicAgentClient(api_key="key", model="claude-sonnet-5")
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _text_response("hi")

    monkeypatch.setattr(client._client.messages, "create", fake_create)

    client.complete("system", "hello")

    assert captured["max_tokens"] == 200
    assert "extra_body" not in captured


def test_anthropic_run_turn_also_applies_thinking_budget(monkeypatch):
    client = AnthropicAgentClient(
        api_key="key", model="claude-sonnet-5", extended_thinking=True, thinking_budget_tokens=1500
    )
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _text_response("hi")

    monkeypatch.setattr(client._client.messages, "create", fake_create)

    client.run_turn("system", [], [{"role": "user", "content": "hi"}], call_tool=lambda name, args: {})

    assert captured["max_tokens"] == 1500 + 1024
    assert captured["extra_body"]["thinking"]["budget_tokens"] == 1500


def test_openrouter_client_requests_reasoning_when_enabled(monkeypatch):
    client = OpenRouterAgentClient(
        api_key="key", model="some/model", extended_thinking=True, thinking_budget_tokens=1500
    )
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _openai_text_response("hi")

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)

    assert client.complete("system", "hello") == "hi"
    assert captured["extra_body"] == {"reasoning": {"max_tokens": 1500}}


def test_openrouter_client_sends_no_reasoning_param_when_disabled(monkeypatch):
    client = OpenRouterAgentClient(api_key="key", model="some/model")
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return _openai_text_response("hi")

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)

    client.complete("system", "hello")

    assert captured["extra_body"] is None
