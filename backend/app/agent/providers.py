"""AgentClient implementations -- see agent_client.py for why this exists.

AnthropicAgentClient talks to Claude's native Messages API. Its message
threading (assistant content blocks echoed back, tool results as content
blocks inside a user turn) is Anthropic-specific and stays entirely inside
this class -- callers only ever see plain history dicts in and a final
string out.

OpenAICompatibleAgentClient talks to anything that speaks the
/chat/completions + function-calling wire format: DeepSeek, Kimi (Moonshot),
GPT-5-mini, Gemini's OpenAI-compat endpoint, etc. Point it at the right
AGENT_BASE_URL/AGENT_MODEL/AGENT_API_KEY.

OpenRouterAgentClient is a thin subclass of the above, pinned to
openrouter.ai's base URL and carrying OpenRouter's recommended attribution
headers -- it's the default provider (see AGENT_PROVIDER in config.py).
"""

import json
from typing import Callable

import anthropic
import openai

from app.agent.agent_client import ToolSpec


class AnthropicAgentClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        extended_thinking: bool = False,
        thinking_budget_tokens: int = 2048,
    ):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._extended_thinking = extended_thinking
        self._thinking_budget_tokens = thinking_budget_tokens

    @staticmethod
    def _to_anthropic_tools(tool_specs: list[ToolSpec]) -> list[dict]:
        return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tool_specs]

    def _thinking_kwargs(self, output_tokens: int) -> dict:
        """max_tokens covers thinking + text combined and must exceed
        budget_tokens, so bump it on top of the caller's intended output
        budget rather than replacing it. `thinking` goes through extra_body
        since it predates this pinned anthropic SDK version's typed params
        (still a valid Messages API field either way)."""
        if not self._extended_thinking:
            return {"max_tokens": output_tokens}
        return {
            "max_tokens": self._thinking_budget_tokens + output_tokens,
            "extra_body": {"thinking": {"type": "enabled", "budget_tokens": self._thinking_budget_tokens}},
        }

    def run_turn(
        self, system: str, tools: list[ToolSpec], history: list[dict], call_tool: Callable[[str, dict], dict]
    ) -> str:
        anthropic_tools = self._to_anthropic_tools(tools)
        messages = list(history)

        while True:
            response = self._client.messages.create(
                model=self._model,
                system=system,
                tools=anthropic_tools,
                messages=messages,
                **self._thinking_kwargs(1024),
            )
            # Preserve the response's own content blocks unmodified (thinking
            # included) -- Claude requires the thinking blocks that led to a
            # tool call to come back exactly as issued on the next turn.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                return "".join(block.text for block in response.content if block.type == "text")

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = call_tool(block.name, block.input)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
            messages.append({"role": "user", "content": tool_results})

    def complete(self, system: str, user_message: str) -> str:
        response = self._client.messages.create(
            model=self._model,
            system=system,
            messages=[{"role": "user", "content": user_message}],
            **self._thinking_kwargs(200),
        )
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAICompatibleAgentClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        default_headers: dict | None = None,
        extra_body: dict | None = None,
    ):
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers)
        self._model = model
        # Provider-specific extras (e.g. OpenRouter's `reasoning` param) that
        # aren't part of the OpenAI-compatible spec every endpoint speaks --
        # left unset for a plain /chat/completions target so this stays a
        # true generic passthrough there.
        self._extra_body = extra_body

    @staticmethod
    def _to_openai_tools(tool_specs: list[ToolSpec]) -> list[dict]:
        return [
            {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
            for t in tool_specs
        ]

    def run_turn(
        self, system: str, tools: list[ToolSpec], history: list[dict], call_tool: Callable[[str, dict], dict]
    ) -> str:
        openai_tools = self._to_openai_tools(tools)
        messages = [{"role": "system", "content": system}] + list(history)

        while True:
            response = self._client.chat.completions.create(
                model=self._model, messages=messages, tools=openai_tools, extra_body=self._extra_body
            )
            message = response.choices[0].message
            messages.append(message.model_dump(exclude_none=True))

            if not message.tool_calls:
                return message.content or ""

            for tool_call in message.tool_calls:
                args = json.loads(tool_call.function.arguments or "{}")
                result = call_tool(tool_call.function.name, args)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)})

    def complete(self, system: str, user_message: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_message}],
            extra_body=self._extra_body,
        )
        return response.choices[0].message.content or ""


class OpenRouterAgentClient(OpenAICompatibleAgentClient):
    """OpenRouter (openrouter.ai) -- OpenAI-compatible, routes to many
    underlying providers/models by slug (e.g. "deepseek/deepseek-chat").
    Sends OpenRouter's recommended attribution headers (X-Title, and
    HTTP-Referer when a site URL is configured) so usage attributes
    correctly in their dashboard. Everything else (tool translation,
    run_turn, complete) is inherited unchanged from the generic
    OpenAI-compatible client, aside from optionally requesting reasoning
    tokens via OpenRouter's unified `reasoning` param -- normalized across
    every reasoning-capable model OpenRouter proxies, but only actually
    reasons if OPENROUTER_MODEL itself supports it; otherwise it's ignored."""

    def __init__(
        self,
        api_key: str,
        model: str,
        site_url: str = "",
        app_name: str = "Bankr",
        extended_thinking: bool = False,
        thinking_budget_tokens: int = 2048,
    ):
        headers = {"X-Title": app_name}
        if site_url:
            headers["HTTP-Referer"] = site_url
        extra_body = {"reasoning": {"max_tokens": thinking_budget_tokens}} if extended_thinking else None
        super().__init__(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            model=model,
            default_headers=headers,
            extra_body=extra_body,
        )
