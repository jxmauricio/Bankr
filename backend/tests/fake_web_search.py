from app.integrations.web_search import SearchResult


class FakeWebSearchClient:
    """Canned WebSearchClient for tests -- never touches Brave's API. Same
    role tests/fake_aggregator.py plays for Plaid."""

    def __init__(self, results: list[SearchResult] | None = None):
        self.results = results if results is not None else self._default_results()
        self.queries: list[str] = []

    @staticmethod
    def _default_results() -> list[SearchResult]:
        return [
            SearchResult(
                title="Current savings account rates",
                url="https://example.com/rates",
                snippet="Top savings accounts are currently yielding around 4.5% APY.",
            )
        ]

    def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        self.queries.append(query)
        return self.results[:max_results]
