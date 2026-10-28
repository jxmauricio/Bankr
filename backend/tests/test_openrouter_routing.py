"""OpenRouter provider routing and the per-round timing log, checked at the
request-kwargs level without hitting a real LLM API (same approach as
test_extended_thinking.py)."""

import logging
from types import SimpleNamespace

from app.agent.providers import OpenRouterAgentClient


def _openai_text_response(text: str, **extra):
    message = SimpleNamespace(content=text, tool_calls=None, model_dump=lambda exclude_none=True: {"role": "assistant", "content": text})
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], **extra)


def _capture_create(monkeypatch, client, response):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return response

    monkeypatch.setattr(client._client.chat.completions, "create", fake_create)
    return captured


def test_openrouter_client_sends_provider_sort(monkeypatch):
    client = OpenRouterAgentClient(api_key="key", model="some/model", provider_sort="throughput")
    captured = _capture_create(monkeypatch, client, _openai_text_response("hi"))

    client.complete("system", "hello")

    assert captured["extra_body"] == {"usage": {"include": True}, "provider": {"sort": "throughput"}}


def test_openrouter_client_combines_provider_sort_with_reasoning(monkeypatch):
    client = OpenRouterAgentClient(
        api_key="key", model="some/model", extended_thinking=True, thinking_budget_tokens=1500, provider_sort="latency"
    )
    captured = _capture_create(monkeypatch, client, _openai_text_response("hi"))

    client.complete("system", "hello")

    assert captured["extra_body"] == {"usage": {"include": True}, "reasoning": {"max_tokens": 1500}, "provider": {"sort": "latency"}}


def test_run_turn_logs_timing_tokens_and_provider(monkeypatch, caplog):
    client = OpenRouterAgentClient(api_key="key", model="some/model")
    usage = SimpleNamespace(
        prompt_tokens=1200, completion_tokens=300, completion_tokens_details=SimpleNamespace(reasoning_tokens=250)
    )
    _capture_create(monkeypatch, client, _openai_text_response("hi", usage=usage, provider="SomeHost"))

    with caplog.at_level(logging.INFO, logger="app.agent.providers"):
        assert client.run_turn("system", [], [{"role": "user", "content": "hello"}], lambda name, args: {}) == "hi"

    [line] = [r.getMessage() for r in caplog.records if r.name == "app.agent.providers"]
    assert line.startswith("agent round 0: model ")
    assert "tokens in=1200 out=300 reasoning=250, cost=None, served_by=SomeHost" in line


def test_openrouter_client_caps_output_tokens(monkeypatch):
    """Without a cap OpenRouter reserves each provider's full output limit,
    which rules out most providers on a key with a spending limit."""
    client = OpenRouterAgentClient(api_key="key", model="some/model", max_output_tokens=4096)
    captured = _capture_create(monkeypatch, client, _openai_text_response("hi"))

    client.run_turn("system", [], [{"role": "user", "content": "hello"}], lambda name, args: {})

    assert captured["max_tokens"] == 4096
