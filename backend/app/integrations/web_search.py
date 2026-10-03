"""Web search adapter -- lets the chat agent (app/agent/tools.py's
web_search tool) look up anything time-sensitive it wasn't trained on or
that changes over time (current savings/mortgage rates, inflation, general
cost-of-living context, ...).

Same adapter-boundary shape as BankAggregatorClient and AgentClient: callers
depend on the WebSearchClient Protocol below, never on a specific search
provider's API directly, so swapping providers is a matter of adding one new
adapter class, not a rewrite. Two implementations exist (Brave
Search, or OpenRouter's web plugin when the agent already runs on OpenRouter
and no Brave key is set, so search needs no extra account).
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
_SNIPPET_MAX_CHARS = 400


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


class WebSearchClient(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        """Return up to max_results web results for the query."""
        ...


class BraveSearchClient:
    """https://api.search.brave.com/app/documentation/web-search/get-started"""

    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        response = httpx.get(
            _BRAVE_SEARCH_URL,
            params={"q": query, "count": max_results},
            headers={"Accept": "application/json", "X-Subscription-Token": self._api_key},
            timeout=10.0,
        )
        response.raise_for_status()
        results = response.json().get("web", {}).get("results", [])
        return [
            SearchResult(
                title=result.get("title", ""),
                url=result.get("url", ""),
                snippet=result.get("description", ""),
            )
            for result in results[:max_results]
        ]


class OpenRouterSearchClient:
    """OpenRouter's web plugin (https://openrouter.ai/docs/features/web-search),
    used purely as a search API: one request carrying only the query the
    agent wrote -- never the user's message or any account data -- and the
    results are read from the response's url_citation annotations. max_tokens
    is tiny because the generated text is thrown away; what's billed is the
    search itself (Exa, about $0.007 per request) plus a trivial completion.
    Reuses OPENROUTER_API_KEY, so no separate search account is needed."""

    def __init__(self, api_key: str, model: str, app_name: str = "Bankr", site_url: str = ""):
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}", "X-Title": app_name}
        if site_url:
            self._headers["HTTP-Referer"] = site_url

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        response = httpx.post(
            _OPENROUTER_CHAT_URL,
            headers=self._headers,
            json={
                "model": self._model,
                "messages": [{"role": "user", "content": query}],
                "plugins": [{"id": "web", "engine": "exa", "max_results": max_results}],
                "max_tokens": 16,
            },
            timeout=30.0,
        )
        response.raise_for_status()
        message = (response.json().get("choices") or [{}])[0].get("message", {})
        results = []
        for annotation in message.get("annotations") or []:
            if annotation.get("type") != "url_citation":
                continue
            citation = annotation.get("url_citation", {})
            results.append(
                SearchResult(
                    title=citation.get("title", ""),
                    url=citation.get("url", ""),
                    snippet=" ".join((citation.get("content") or "").split())[:_SNIPPET_MAX_CHARS],
                )
            )
        return results[:max_results]


def build_web_search_client() -> WebSearchClient | None:
    """Brave if its key is set, else OpenRouter's web plugin when the agent
    already runs on OpenRouter. None when neither is available --
    app/agent/tools.py's web_search degrades to a clear error result rather
    than the app crashing at startup, same as the rest of Bankr's optional
    integrations."""
    from app.config import settings

    if settings.brave_search_api_key:
        return BraveSearchClient(api_key=settings.brave_search_api_key)
    if settings.agent_provider == "openrouter" and settings.openrouter_api_key:
        return OpenRouterSearchClient(
            api_key=settings.openrouter_api_key,
            model=settings.openrouter_model,
            app_name=settings.openrouter_app_name,
            site_url=settings.openrouter_site_url,
        )
    return None
