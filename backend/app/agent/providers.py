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
import logging
import time
from typing import Callable

import anthropic
import openai

from app.agent.agent_client import ToolSpec

# Upper bound on model->tool->model round trips per user message. Each round
# is a paid API call, and nothing else stops a confused model from calling
# tools forever. Real questions need 1-3 rounds; past the cap, one last call
# with tools disabled makes the model answer from what it already gathered.
MAX_TOOL_ROUNDS = 8

# Sent with the last tool results before that final, tools-disabled call.
# Without it some models return nothing at all once they can't call a tool.
FINAL_ROUND_NUDGE = (
    "You've used all your tool calls for this question. Answer the user now from the tool results above."
)

# One silent extra call when the model used its output budget on reasoning
# (or otherwise returned no visible text). The chat UI never sees this; it
# only gets the retry's answer, or the empty-reply fallback if that is empty too.
EMPTY_RETRY_NUDGE = (
    "You returned no visible answer. Reply to the user now from the tool results above. "
    "Do not call tools."
)

logger = logging.getLogger(__name__)


def _log_round(round_number: int, model_seconds: float, tool_seconds: float, usage: dict, served_by: str | None) -> None:
    """One line per model round so production logs show where a slow chat
    turn spent its time: waiting on the model, or running tools. Reasoning
    tokens are counted separately because a model that reasons by default
    spends most of a round's time on output the user never sees."""
    logger.info(
        "agent round %d: model %.2fs, tools %.2fs, tokens in=%s out=%s reasoning=%s, cost=%s, served_by=%s",
        round_number,
        model_seconds,
        tool_seconds,
        usage.get("input"),
        usage.get("output"),
        usage.get("reasoning"),
        usage.get("cost"),
        served_by,
    )



def _merge_piece(pieces: dict[int, dict], piece) -> None:
    """Fold one streamed reasoning_details fragment into the entry with the
    same index: text-like fields concatenate, anything else (type, format,
    signature) is kept from whichever fragment carried it."""
    piece = piece if isinstance(piece, dict) else piece.model_dump()
    entry = pieces.setdefault(piece.get("index", 0), {})
    for key, value in piece.items():
        if value is None:
            continue
        if key in ("text", "summary", "data") and isinstance(value, str):
            entry[key] = entry.get(key, "") + value
        else:
            entry.setdefault(key, value)

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
        self,
        system: str,
        tools: list[ToolSpec],
        history: list[dict],
        call_tool: Callable[[str, dict], dict],
        on_text: Callable[[str | None], None] | None = None,
        on_usage: Callable[[dict], None] | None = None,
    ) -> str:
        anthropic_tools = self._to_anthropic_tools(tools)
        messages = list(history)

        for round_number in range(MAX_TOOL_ROUNDS + 1):
            final_round = round_number == MAX_TOOL_ROUNDS
            started = time.monotonic()
            response = self._client.messages.create(
                model=self._model,
                system=system,
                tools=anthropic_tools,
                messages=messages,
                # tool_choice "none" postdates this pinned SDK's typed params
                # but is a valid Messages API value either way.
                **({"tool_choice": {"type": "none"}} if final_round and anthropic_tools else {}),
                **self._thinking_kwargs(1024),
            )
            model_seconds = time.monotonic() - started
            usage = {
                "input": getattr(getattr(response, "usage", None), "input_tokens", None),
                "output": getattr(getattr(response, "usage", None), "output_tokens", None),
            }
            if on_usage:
                on_usage(usage)
            # Preserve the response's own content blocks unmodified (thinking
            # included) -- Claude requires the thinking blocks that led to a
            # tool call to come back exactly as issued on the next turn.
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use" or final_round:
                _log_round(round_number, model_seconds, 0.0, usage, None)
                text = "".join(block.text for block in response.content if block.type == "text")
                if not text.strip():
                    text = self._retry_empty_reply(system, anthropic_tools, messages, on_usage)
                # Not streamed token by token here (OpenRouter is the default
                # provider); the listener gets the whole answer in one piece.
                if on_text and text:
                    on_text(text)
                return text

            started = time.monotonic()
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = call_tool(block.name, block.input)
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": str(result)})
            if round_number == MAX_TOOL_ROUNDS - 1:
                tool_results.append({"type": "text", "text": FINAL_ROUND_NUDGE})
            messages.append({"role": "user", "content": tool_results})
            _log_round(round_number, model_seconds, time.monotonic() - started, usage, None)

    def _retry_empty_reply(
        self,
        system: str,
        anthropic_tools: list[dict],
        messages: list[dict],
        on_usage: Callable[[dict], None] | None,
    ) -> str:
        """One more Messages call, tools off, no thinking budget. Hidden from the user."""
        logger.info("agent empty reply, retrying once")
        messages.append({"role": "user", "content": EMPTY_RETRY_NUDGE})
        started = time.monotonic()
        response = self._client.messages.create(
            model=self._model,
            system=system,
            tools=anthropic_tools,
            messages=messages,
            **({"tool_choice": {"type": "none"}} if anthropic_tools else {}),
            max_tokens=1024,
        )
        usage = {
            "input": getattr(getattr(response, "usage", None), "input_tokens", None),
            "output": getattr(getattr(response, "usage", None), "output_tokens", None),
        }
        if on_usage:
            on_usage(usage)
        _log_round(MAX_TOOL_ROUNDS + 1, time.monotonic() - started, 0.0, usage, None)
        return "".join(block.text for block in response.content if block.type == "text")

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
        max_output_tokens: int = 1024,
    ):
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, default_headers=default_headers)
        self._model = model
        self._max_tokens = max_output_tokens
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

    @staticmethod
    def _usage(response) -> dict:
        # Not every OpenAI-compatible endpoint reports usage (or its
        # reasoning breakdown), and timing logs must never break a turn.
        usage = getattr(response, "usage", None)
        if usage is None:
            return {}
        details = getattr(usage, "completion_tokens_details", None)
        prompt_details = getattr(usage, "prompt_tokens_details", None)
        return {
            "input": getattr(usage, "prompt_tokens", None),
            "output": getattr(usage, "completion_tokens", None),
            "reasoning": getattr(details, "reasoning_tokens", None),
            "cached": getattr(prompt_details, "cached_tokens", None),
            # Billed dollars for the call -- only OpenRouter reports this.
            "cost": getattr(usage, "cost", None),
        }

    def _create_round(self, request: dict, on_text: Callable[[str | None], None] | None) -> tuple[dict, dict, str | None]:
        """One model call, returned as (assistant message dict, usage,
        served_by). Without on_text it's a plain request; with it the call
        streams and each piece of reply text goes to on_text as it arrives."""
        if on_text is None:
            response = self._client.chat.completions.create(**request)
            # OpenRouter adds which upstream provider served the call; plain
            # OpenAI-compatible endpoints don't, so this is None there.
            served_by = getattr(response, "provider", None)
            return response.choices[0].message.model_dump(exclude_none=True), self._usage(response), served_by

        content: list[str] = []
        reasoning: list[str] = []
        reasoning_details: dict[int, dict] = {}
        tool_calls: dict[int, dict] = {}
        usage, served_by = {}, None
        with self._client.chat.completions.create(
            **request, stream=True, stream_options={"include_usage": True}
        ) as stream:
            for chunk in stream:
                served_by = getattr(chunk, "provider", None) or served_by
                if getattr(chunk, "usage", None):
                    usage = self._usage(chunk)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    content.append(delta.content)
                    on_text(delta.content)
                if getattr(delta, "reasoning", None):
                    reasoning.append(delta.reasoning)
                for detail in getattr(delta, "reasoning_details", None) or []:
                    _merge_piece(reasoning_details, detail)
                for call in delta.tool_calls or []:
                    slot = tool_calls.setdefault(
                        call.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                    )
                    slot["id"] = call.id or slot["id"]
                    if call.function:
                        slot["function"]["name"] += call.function.name or ""
                        slot["function"]["arguments"] += call.function.arguments or ""

        # Rebuild it the way a non-streamed response would have come back,
        # reasoning included -- some reasoning models need it echoed back on
        # the next round of a tool loop.
        message: dict = {"role": "assistant", "content": "".join(content)}
        if reasoning:
            message["reasoning"] = "".join(reasoning)
        if reasoning_details:
            message["reasoning_details"] = [reasoning_details[i] for i in sorted(reasoning_details)]
        if tool_calls:
            message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
        return message, usage, served_by

    def run_turn(
        self,
        system: str,
        tools: list[ToolSpec],
        history: list[dict],
        call_tool: Callable[[str, dict], dict],
        on_text: Callable[[str | None], None] | None = None,
        on_usage: Callable[[dict], None] | None = None,
    ) -> str:
        openai_tools = self._to_openai_tools(tools)
        messages = [{"role": "system", "content": system}] + list(history)

        for round_number in range(MAX_TOOL_ROUNDS + 1):
            final_round = round_number == MAX_TOOL_ROUNDS
            started = time.monotonic()
            message, usage, served_by = self._create_round(
                {
                    "model": self._model,
                    "max_tokens": self._max_tokens,
                    "messages": messages,
                    "tools": openai_tools,
                    # Only sent with tools present -- some endpoints reject
                    # tool_choice alongside an empty tools list.
                    **({"tool_choice": "none"} if final_round and openai_tools else {}),
                    "extra_body": self._extra_body,
                },
                on_text,
            )
            model_seconds = time.monotonic() - started
            if on_usage:
                on_usage(usage)
            messages.append(message)
            tool_calls = message.get("tool_calls")

            if not tool_calls or final_round:
                _log_round(round_number, model_seconds, 0.0, usage, served_by)
                content = message.get("content") or ""
                if not content.strip():
                    content = self._retry_empty_reply(messages, openai_tools, on_text, on_usage)
                return content

            if on_text and message.get("content"):
                # Text the model wrote before deciding to call a tool isn't the
                # answer; tell the listener to drop what it was shown.
                on_text(None)
            started = time.monotonic()
            for tool_call in tool_calls:
                args = json.loads(tool_call["function"]["arguments"] or "{}")
                result = call_tool(tool_call["function"]["name"], args)
                messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": json.dumps(result)})
            if round_number == MAX_TOOL_ROUNDS - 1:
                messages.append({"role": "user", "content": FINAL_ROUND_NUDGE})
            _log_round(round_number, model_seconds, time.monotonic() - started, usage, served_by)

    def _retry_extra_body(self) -> dict | None:
        return self._extra_body

    def _retry_empty_reply(
        self,
        messages: list[dict],
        openai_tools: list[dict],
        on_text: Callable[[str | None], None] | None,
        on_usage: Callable[[dict], None] | None,
    ) -> str:
        """One more completion, tools off. The first attempt streamed nothing,
        so the listener only sees this call's tokens."""
        logger.info("agent empty reply, retrying once")
        messages.append({"role": "user", "content": EMPTY_RETRY_NUDGE})
        started = time.monotonic()
        message, usage, served_by = self._create_round(
            {
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": messages,
                "tools": openai_tools,
                **({"tool_choice": "none"} if openai_tools else {}),
                "extra_body": self._retry_extra_body(),
            },
            on_text,
        )
        if on_usage:
            on_usage(usage)
        _log_round(MAX_TOOL_ROUNDS + 1, time.monotonic() - started, 0.0, usage, served_by)
        return message.get("content") or ""

    def complete(self, system: str, user_message: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
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
    reasons if OPENROUTER_MODEL itself supports it; otherwise it's ignored --
    and its `provider.sort` routing preference (OPENROUTER_PROVIDER_SORT)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        site_url: str = "",
        app_name: str = "Bankr",
        extended_thinking: bool = False,
        thinking_budget_tokens: int = 2048,
        provider_sort: str = "",
        max_output_tokens: int = 1024,
    ):
        headers = {"X-Title": app_name}
        if site_url:
            headers["HTTP-Referer"] = site_url
        # Usage accounting: adds the billed `cost` to each response's usage.
        extra_body: dict = {"usage": {"include": True}}
        if extended_thinking:
            extra_body["reasoning"] = {"max_tokens": thinking_budget_tokens}
        if provider_sort:
            # OpenRouter's provider routing: rank the providers serving this
            # model by this instead of its price-weighted default.
            extra_body["provider"] = {"sort": provider_sort}
        super().__init__(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            model=model,
            default_headers=headers,
            extra_body=extra_body,
            max_output_tokens=max_output_tokens,
        )

    def _retry_extra_body(self) -> dict:
        """The blank replies are DeepSeek spending the whole max_tokens on
        hidden reasoning. Turn that off for the retry so the budget is text."""
        extra = dict(self._extra_body or {})
        extra["reasoning"] = {"enabled": False}
        return extra
