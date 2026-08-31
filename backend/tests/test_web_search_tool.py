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
