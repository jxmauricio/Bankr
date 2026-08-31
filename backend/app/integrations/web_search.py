"""Web search adapter -- lets the chat agent (app/agent/tools.py's
web_search tool) look up anything time-sensitive it wasn't trained on or
that changes over time (current savings/mortgage rates, inflation, general
cost-of-living context, ...).

Same adapter-boundary shape as BankAggregatorClient and AgentClient: callers
depend on the WebSearchClient Protocol below, never on a specific search
provider's API directly, so swapping providers is a matter of adding one new
adapter class, not a rewrite. Only one implementation exists today (Brave
Search), since nothing has forced a second one yet -- unlike the aggregator,
which really did need to move providers once already.
"""

from dataclasses import dataclass
from typing import Protocol

import httpx

_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


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


def build_web_search_client() -> WebSearchClient | None:
    """None when no key is configured -- app/agent/tools.py's web_search
    degrades to a clear error result rather than the app crashing at
    startup, same as the rest of Bankr's optional integrations."""
    from app.config import settings

    if not settings.brave_search_api_key:
        return None
    return BraveSearchClient(api_key=settings.brave_search_api_key)
