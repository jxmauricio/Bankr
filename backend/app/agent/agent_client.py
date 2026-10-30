"""Vendor-agnostic interface for the LLM behind Bankr's agent.

Three backends implement this (see providers.py): OpenRouterAgentClient (the
default -- routes to whatever model OPENROUTER_MODEL names), Anthropic's
native Messages API, and a generic OpenAI-/chat-completions-shaped client
that also covers DeepSeek, Kimi (Moonshot), GPT-5-mini, or anything else that
speaks that wire format directly. claude_agent.py and insights_job.py depend
only on this Protocol, never on a vendor SDK directly, so switching
providers/models is a config change (AGENT_PROVIDER), not a code change.
Same shape as the BankAggregatorClient adapter in
app/integrations/bank_aggregator.py.
"""

from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema for the tool's input


class AgentClient(Protocol):
    def run_turn(
        self,
        system: str,
        tools: list[ToolSpec],
        history: list[dict],
        call_tool: Callable[[str, dict], dict],
        on_text: Callable[[str | None], None] | None = None,
        on_usage: Callable[[dict], None] | None = None,
        system_context: str = "",
    ) -> str:
        """Resolve one user turn to completion, including any tool calls,
        and return the final assistant text. When on_text is given, reply
        text is passed to it piece by piece as the model writes it; on_text(None)
        means "discard what you were sent", because the model went on to call
        a tool instead of answering. When on_usage is given, it gets each model
        round's usage as {"input", "output", "reasoning", "cached",
        "cache_write", "cost"} (any may be missing or None -- not every
        provider reports them); "input" is the whole prompt, cached part
        included. `system` must be the same text on every call so providers
        can cache it; `system_context` is per-turn text (today's date) that
        goes after it, outside the cached prefix. `history` is a plain
        [{"role": "user"|"assistant", "content": str}, ...] list -- no
        vendor-specific tool_use/tool_result blocks leak across turns (see
        chat_service.py, which persists only final text per turn)."""
        ...

    def complete(self, system: str, user_message: str) -> str:
        """A single-shot completion with no tool use -- used to phrase
        already-detected insights (see jobs/insights_job.py)."""
        ...


def build_agent_client() -> AgentClient:
    from app.config import settings
    from app.agent.providers import AnthropicAgentClient, OpenAICompatibleAgentClient, OpenRouterAgentClient

    if settings.agent_provider == "openrouter":
        return OpenRouterAgentClient(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            site_url=settings.openrouter_site_url,
            app_name=settings.openrouter_app_name,
            provider_sort=settings.openrouter_provider_sort,
            max_output_tokens=settings.agent_max_output_tokens,
            extended_thinking=settings.agent_extended_thinking,
            thinking_budget_tokens=settings.agent_thinking_budget_tokens,
            prompt_caching=settings.agent_prompt_caching,
        )
    if settings.agent_provider == "openai_compatible":
        return OpenAICompatibleAgentClient(
            api_key=settings.agent_api_key,
            base_url=settings.agent_base_url,
            model=settings.agent_model,
            max_output_tokens=settings.agent_max_output_tokens,
        )
    return AnthropicAgentClient(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        extended_thinking=settings.agent_extended_thinking,
        thinking_budget_tokens=settings.agent_thinking_budget_tokens,
        prompt_caching=settings.agent_prompt_caching,
    )
