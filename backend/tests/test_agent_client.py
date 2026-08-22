from app import config
from app.agent.agent_client import build_agent_client
from app.agent.providers import AnthropicAgentClient, OpenAICompatibleAgentClient, OpenRouterAgentClient


def test_build_agent_client_defaults_to_openrouter(monkeypatch):
    monkeypatch.setattr(config.settings, "agent_provider", "openrouter")
    monkeypatch.setattr(config.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(config.settings, "openrouter_model", "deepseek/deepseek-v4-flash-0731")
    monkeypatch.setattr(config.settings, "openrouter_site_url", "")
    monkeypatch.setattr(config.settings, "openrouter_app_name", "Bankr")

    client = build_agent_client()

    assert isinstance(client, OpenRouterAgentClient)
    assert client._model == "deepseek/deepseek-v4-flash-0731"
    assert str(client._client.base_url) == "https://openrouter.ai/api/v1/"
    assert client._client.default_headers["X-Title"] == "Bankr"
    assert "HTTP-Referer" not in client._client.default_headers


def test_openrouter_client_sets_referer_header_when_site_url_configured(monkeypatch):
    monkeypatch.setattr(config.settings, "agent_provider", "openrouter")
    monkeypatch.setattr(config.settings, "openrouter_api_key", "test-key")
    monkeypatch.setattr(config.settings, "openrouter_model", "deepseek/deepseek-v4-flash-0731")
    monkeypatch.setattr(config.settings, "openrouter_site_url", "https://bankr.example.com")
    monkeypatch.setattr(config.settings, "openrouter_app_name", "Bankr")

    client = build_agent_client()

    assert client._client.default_headers["HTTP-Referer"] == "https://bankr.example.com"


def test_build_agent_client_still_supports_anthropic(monkeypatch):
    monkeypatch.setattr(config.settings, "agent_provider", "anthropic")
    monkeypatch.setattr(config.settings, "anthropic_api_key", "test-key")
    monkeypatch.setattr(config.settings, "anthropic_model", "claude-sonnet-5")

    client = build_agent_client()

    assert isinstance(client, AnthropicAgentClient)


def test_build_agent_client_still_supports_generic_openai_compatible(monkeypatch):
    monkeypatch.setattr(config.settings, "agent_provider", "openai_compatible")
    monkeypatch.setattr(config.settings, "agent_api_key", "test-key")
    monkeypatch.setattr(config.settings, "agent_model", "deepseek-chat")
    monkeypatch.setattr(config.settings, "agent_base_url", "https://api.deepseek.com")

    client = build_agent_client()

    assert isinstance(client, OpenAICompatibleAgentClient)
    assert not isinstance(client, OpenRouterAgentClient)
