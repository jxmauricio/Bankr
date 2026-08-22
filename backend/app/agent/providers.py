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
    def __init__(self, api_key: str, model: str):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    @staticmethod
    def _to_anthropic_tools(tool_specs: list[ToolSpec]) -> list[dict]:
        return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tool_specs]

    def run_turn(
        self, system: str, tools: list[ToolSpec], history: list[dict], call_tool: Callable[[str, dict], dict]
    ) -> str:
        anthropic_tools = self._to_anthropic_tools(tools)
        messages = list(history)

        while True:
            response = self._client.messages.create(
                model=self._model, max_tokens=1024, system=system, tools=anthropic_tools, messages=messages
            )
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
            max_tokens=200,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class OpenAICompatibleAgentClient:
    def __init__(self, api_key: str, base_url: str, model: str, default_headers: dict | None = None):
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers)
        self._model = model

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
                model=self._model, messages=messages, tools=openai_tools
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
        )
        return response.choices[0].message.content or ""


class OpenRouterAgentClient(OpenAICompatibleAgentClient):
    """OpenRouter (openrouter.ai) -- OpenAI-compatible, routes to many
    underlying providers/models by slug (e.g. "deepseek/deepseek-chat").
    Sends OpenRouter's recommended attribution headers (X-Title, and
    HTTP-Referer when a site URL is configured) so usage attributes
    correctly in their dashboard. Everything else (tool translation,
    run_turn, complete) is inherited unchanged from the generic
    OpenAI-compatible client."""

    def __init__(self, api_key: str, model: str, site_url: str = "", app_name: str = "Bankr"):
        headers = {"X-Title": app_name}
        if site_url:
            headers["HTTP-Referer"] = site_url
        super().__init__(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            model=model,
            default_headers=headers,
        )
