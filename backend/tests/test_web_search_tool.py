from app.agent.tools import web_search
from app.integrations.web_search import SearchResult
from tests.fake_web_search import FakeWebSearchClient


def test_web_search_returns_results_from_the_injected_client():
    fake = FakeWebSearchClient(
        results=[
            SearchResult(title="A", url="https://a.example", snippet="snippet a"),
            SearchResult(title="B", url="https://b.example", snippet="snippet b"),
        ]
    )

    result = web_search("high yield savings rates", client=fake)

    assert fake.queries == ["high yield savings rates"]
    assert result["query"] == "high yield savings rates"
    assert result["results"] == [
        {"title": "A", "url": "https://a.example", "snippet": "snippet a"},
        {"title": "B", "url": "https://b.example", "snippet": "snippet b"},
    ]
    assert "error" not in result


def test_web_search_respects_max_results():
    fake = FakeWebSearchClient(
        results=[SearchResult(title=f"R{i}", url=f"https://e.example/{i}", snippet="") for i in range(5)]
    )

    result = web_search("query", max_results=2, client=fake)

    assert len(result["results"]) == 2


def test_web_search_without_a_configured_client_returns_a_clear_error():
    result = web_search("query", client=None)

    assert "error" in result
    assert "not configured" in result["error"]
    assert "results" not in result


def test_web_search_surfaces_a_failed_search_as_an_error_not_a_crash():
    class BoomClient:
        def search(self, query, max_results=5):
            raise RuntimeError("timeout")

    result = web_search("query", client=BoomClient())

    assert "error" in result
    assert "timeout" in result["error"]


class _FakeResponse:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


def test_openrouter_search_reads_url_citations_and_sends_only_the_query(monkeypatch):
    from app.integrations import web_search

    sent = {}

    def fake_post(url, headers, json, timeout):
        sent.update(url=url, json=json)
        return _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "annotations": [
                                {"type": "url_citation", "url_citation": {"title": "Rates", "url": "https://a.test", "content": "4.1%\n APY  today"}},
                                {"type": "something_else"},
                            ],
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr(web_search.httpx, "post", fake_post)
    client = web_search.OpenRouterSearchClient(api_key="k", model="some/model")

    results = client.search("current savings rates", max_results=3)

    assert results == [web_search.SearchResult(title="Rates", url="https://a.test", snippet="4.1% APY today")]
    assert sent["json"]["messages"] == [{"role": "user", "content": "current savings rates"}]
    assert sent["json"]["plugins"] == [{"id": "web", "engine": "exa", "max_results": 3}]


def test_build_web_search_client_prefers_brave_then_openrouter(monkeypatch):
    from app.config import settings
    from app.integrations import web_search

    monkeypatch.setattr(settings, "agent_provider", "openrouter")
    monkeypatch.setattr(settings, "openrouter_api_key", "or-key")
    monkeypatch.setattr(settings, "brave_search_api_key", "")
    assert isinstance(web_search.build_web_search_client(), web_search.OpenRouterSearchClient)

    monkeypatch.setattr(settings, "brave_search_api_key", "brave-key")
    assert isinstance(web_search.build_web_search_client(), web_search.BraveSearchClient)

    monkeypatch.setattr(settings, "brave_search_api_key", "")
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    assert web_search.build_web_search_client() is None
