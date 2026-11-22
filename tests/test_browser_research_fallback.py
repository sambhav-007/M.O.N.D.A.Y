"""Regression tests for research when DuckDuckGo rate-limits the app."""

import json

from agents.browser_agent import BrowserAgent


class FakeResponse:
    def __init__(self, status_code, url, text):
        self.status_code = status_code
        self.url = url
        self.text = text


def test_research_uses_attributed_wikipedia_results_after_ddg_challenge(monkeypatch):
    calls = []
    wikipedia_response = json.dumps({
        "query": {
            "search": [
                {
                    "title": "Artificial intelligence",
                    "snippet": (
                        "<span class='searchmatch'>Artificial</span> intelligence "
                        "includes systems that learn and reason."
                    ),
                },
                {
                    "title": "History of artificial intelligence",
                    "snippet": "The field's history began with early research.",
                },
            ],
        },
    })

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url):
            calls.append(url)
            if "duckduckgo.com" in url:
                return FakeResponse(202, url, "challenge")
            return FakeResponse(200, url, wikipedia_response)

    monkeypatch.setattr("agents.browser_agent.httpx.Client", FakeClient)
    result = BrowserAgent().research_topic("artificial intelligence")

    assert result["success"] is True
    assert result["sources_consulted"] == 2
    assert "Artificial intelligence" in result["report"]
    assert "https://en.wikipedia.org/wiki/Artificial_intelligence" in result["report"]
    assert "artificial+intelligence" in calls[0]
    assert "w/api.php" in calls[-1]


def test_wikipedia_search_parser_strips_html_from_snippets():
    response = json.dumps({
        "query": {
            "search": [{
                "title": "Test topic",
                "snippet": "<span>Useful</span> <b>description</b>",
            }],
        },
    })

    result = BrowserAgent._parse_wikipedia_search(response, 5)

    assert result == [{
        "title": "Test topic",
        "snippet": "Useful description",
        "url": "https://en.wikipedia.org/wiki/Test_topic",
    }]


def test_wikipedia_search_parser_rejects_malformed_json_shapes():
    assert BrowserAgent._parse_wikipedia_search('{"query": []}', 5) == []


def test_research_reports_search_failure_when_all_providers_fail(monkeypatch):
    class FailedClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def get(self, url):
            return FakeResponse(503, url, "unavailable")

    monkeypatch.setattr("agents.browser_agent.httpx.Client", FailedClient)
    result = BrowserAgent().research_topic("example topic")

    assert result["success"] is False
    assert result["error"] == "WEB_SEARCH_HTTP_503"
    assert "WEB_SEARCH_HTTP_503" in result["message"]
