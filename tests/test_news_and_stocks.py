"""
News and share prices — two capabilities MONDAY did not have, and the corpus
that proved it.

`fetch me latest news` and `tell me price of ifci stock` both came back "I'm not
sure how to do that yet". The intent classifier was not the problem: it called
both `browser` at 0.92 and 0.94, confidently and correctly. There was simply
nothing behind that class to run — no news skill and no stock skill existed, and
`browser` serves no skill at all, so stage 2 could not route them either.

Measured against `data/external/massive_en_us.csv`, the 10,631 real utterances
Amazon collected for MASSIVE, the gap was not two commands but two capabilities:
707 `news_query` utterances and 200 `qa_stock` ones, of which MONDAY routed 32%
and 42% — nearly all of them to `answer_question`, which looks a headline up on
Wikipedia. The patterns in `core/skills_live.py` are written from those
utterances rather than from imagination; `reports/massive_coverage.py` is the
measurement, and it is why the numbers in these docstrings can be checked.

Everything here runs offline: the feed and the quote endpoint are stubbed. What
is being tested is the parsing and the failure paths, not Google's uptime.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pytest

from agents.public_api_agent import PublicApiAgent
from core.planner import MasterPlanner
from ml.intent_classifier import predict_intent

# ── A real feed, trimmed ─────────────────────────────────────────────────────
# Shape taken from an actual Google News RSS response on 2026-08-18, including
# the detail that broke the first draft: the publisher appears BOTH in <source>
# and appended to <title>, so a naive read prints it twice.
RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Top stories - Google News</title>
  <item>
    <title>Budget session opens with a row over pensions - The Hindu</title>
    <link>https://news.google.com/read/1</link>
    <source url="https://thehindu.com">The Hindu</source>
  </item>
  <item>
    <title>City metro line three opens a year late - The Indian Express</title>
    <link>https://news.google.com/read/2</link>
    <source url="https://indianexpress.com">The Indian Express</source>
  </item>
  <item>
    <title>A headline with no publisher element</title>
    <link>https://news.google.com/read/3</link>
  </item>
</channel></rss>"""

EMPTY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Nothing</title></channel></rss>"""

SEARCH_JSON = {
    "quotes": [
        {"symbol": "IFCI.BO", "quoteType": "EQUITY", "score": 20001.0,
         "longname": "IFCI Limited", "exchDisp": "Bombay"},
        {"symbol": "IFCI.NS", "quoteType": "EQUITY", "score": 19000.0,
         "longname": "IFCI Limited", "exchDisp": "NSE"},
    ]
}

QUOTE_JSON = {
    "chart": {"result": [{"meta": {
        "currency": "INR",
        "symbol": "IFCI.NS",
        "fullExchangeName": "NSE",
        "regularMarketPrice": 80.33,
        "chartPreviousClose": 78.93,
    }}]}
}


class _Reply:
    """Stands in for the object `urlopen` returns, context manager and all."""

    def __init__(self, body: str, status: int = 200) -> None:
        self._body = body.encode("utf-8")
        self.status = status

    def __enter__(self) -> "_Reply":
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False

    def read(self) -> bytes:
        return self._body


@pytest.fixture
def agent(monkeypatch):
    """A `PublicApiAgent` whose HTTP is a lookup table keyed on the URL."""
    import agents.public_api_agent as module

    routes: Dict[str, Any] = {}

    def _urlopen(req: Any, timeout: float = 0) -> _Reply:
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for fragment, body in routes.items():
            if fragment in url:
                if isinstance(body, Exception):
                    raise body
                return _Reply(body)
        raise AssertionError(f"no stub for {url}")

    monkeypatch.setattr(module.urllib.request, "urlopen", _urlopen)
    api = PublicApiAgent()
    api.routes = routes          # type: ignore[attr-defined]
    return api


# ── News ─────────────────────────────────────────────────────────────────────
def test_headlines_come_back_with_their_publishers(agent):
    agent.routes["news.google.com/rss?"] = RSS
    result = agent.get_latest_news()

    assert result["success"] is True
    titles = [h["title"] for h in result["headlines"]]
    assert titles[0] == "Budget session opens with a row over pensions"
    assert result["headlines"][0]["source"] == "The Hindu"
    assert result["evidence"]["kind"] == "http_response"


def test_the_publisher_is_not_printed_twice(agent):
    """Google puts it in <source> AND on the end of <title>."""
    agent.routes["news.google.com/rss?"] = RSS
    message = agent.get_latest_news()["message"]
    assert message.count("The Hindu") == 1


def test_a_headline_without_a_source_element_still_reads(agent):
    agent.routes["news.google.com/rss?"] = RSS
    third = agent.get_latest_news()["headlines"][2]
    assert third["title"] == "A headline with no publisher element"
    assert third["source"] == ""


def test_a_topic_goes_to_the_search_feed(agent):
    """One method, two feeds — the topic feed is the same endpoint with a query,
    so there is no second code path to keep in step."""
    agent.routes["/rss/search?q=technology"] = RSS
    result = agent.get_latest_news("technology")
    assert result["success"] is True
    assert "technology" in result["message"]


def test_an_unreachable_feed_is_a_structured_failure(agent):
    """Not an empty success. The whole repository is an argument about this."""
    agent.routes["news.google.com"] = ConnectionError("no route to host")
    result = agent.get_latest_news()

    assert result["success"] is False
    assert result["error"] == "NEWS_FEED_UNAVAILABLE"
    assert "headlines" not in result


def test_an_empty_feed_does_not_report_success(agent):
    agent.routes["news.google.com/rss?"] = EMPTY_RSS
    result = agent.get_latest_news()
    assert result["success"] is False
    assert result["error"] == "NEWS_FEED_EMPTY"


def test_a_malformed_feed_is_a_failure_not_a_traceback(agent):
    agent.routes["news.google.com/rss?"] = "<rss><channel>truncated"
    result = agent.get_latest_news()
    assert result["success"] is False
    assert result["error"] == "NEWS_FEED_UNPARSEABLE"


def test_the_spoken_form_drops_the_numbering(agent):
    """`core/speech.py` would otherwise read "1." and the publisher out loud."""
    agent.routes["news.google.com/rss?"] = RSS
    result = agent.get_latest_news()
    assert "1." not in result["speech"]
    assert "The Hindu" not in result["speech"]


# ── Stocks ───────────────────────────────────────────────────────────────────
def test_a_company_name_is_resolved_to_a_ticker(agent):
    """People type "ifci". The quote endpoint wants "IFCI.NS"."""
    agent.routes["/v1/finance/search"] = json.dumps(SEARCH_JSON)
    found = agent.resolve_stock_symbol("ifci")
    assert found is not None
    assert found["symbol"] == "IFCI.NS"


def test_an_indian_listing_wins_a_tie(agent):
    """This machine is in India, and the BSE row scores higher at Yahoo. Both
    are the same company; the NSE listing is the one meant locally."""
    agent.routes["/v1/finance/search"] = json.dumps(SEARCH_JSON)
    assert agent.resolve_stock_symbol("ifci")["symbol"].endswith(".NS")


def test_a_quote_reports_the_price_and_the_move(agent):
    agent.routes["/v1/finance/search"] = json.dumps(SEARCH_JSON)
    agent.routes["/v8/finance/chart"] = json.dumps(QUOTE_JSON)
    result = agent.get_stock_price("ifci")

    assert result["success"] is True
    assert result["symbol"] == "IFCI.NS"
    assert result["price"] == pytest.approx(80.33)
    assert "₹80.33" in result["message"]
    assert "+1.77%" in result["message"]
    assert result["evidence"]["kind"] == "http_response"


def test_an_unknown_company_says_so(agent):
    agent.routes["/v1/finance/search"] = json.dumps({"quotes": []})
    result = agent.get_stock_price("not a company at all")
    assert result["success"] is False
    assert result["error"] == "STOCK_SYMBOL_NOT_FOUND"


def test_a_found_company_with_no_price_is_still_a_failure(agent):
    """"I found it but cannot price it" is a different problem from "no such
    company", and reporting either as a success would be the old defect."""
    agent.routes["/v1/finance/search"] = json.dumps(SEARCH_JSON)
    agent.routes["/v8/finance/chart"] = json.dumps({"chart": {"result": [{"meta": {}}]}})
    result = agent.get_stock_price("ifci")
    assert result["success"] is False
    assert result["error"] == "STOCK_QUOTE_UNAVAILABLE"


def test_no_company_named_asks_rather_than_guessing(agent):
    result = agent.get_stock_price("")
    assert result["success"] is False
    assert result["error"] == "STOCK_NO_SYMBOL"


# ── Routing: the commands that started this ──────────────────────────────────
@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    p.router.llm = None          # stage 1 and 2 only; a model is not a capability
    return p


def _route(planner, command):
    intent, confidence, _ = predict_intent(planner.classifier, command)
    return planner.router.route(command, intent=intent, confidence=confidence)


@pytest.mark.parametrize("command", [
    "fetch me latest news",
    "latest news",
    "news",
    "tell me the news",
    "show me the latest headlines",
    "what's the latest news",
    "tell me the latest technology news",
    "give me the news about cricket",
])
def test_news_commands_reach_the_news(planner, command):
    decision = _route(planner, command)
    assert decision.routed, f"{command!r} still routes nowhere"
    assert decision.skill.name == "latest_news"


@pytest.mark.parametrize("command", [
    "tell me price of ifci stock",
    "ifci share price",
    "stock price of google",
    "show me the stock price for google",
    "what is the share price of infosys",
    "how are apple shares doing",
])
def test_stock_commands_reach_the_quote(planner, command):
    decision = _route(planner, command)
    assert decision.routed, f"{command!r} still routes nowhere"
    assert decision.skill.name == "stock_price"


def test_the_company_name_is_captured_not_recovered_afterwards(planner):
    """The slot carries it. `"ifci" in command` is the mistake this repo deleted
    ~350 lines of."""
    assert _route(planner, "tell me price of ifci stock").slots == {"symbol": "ifci"}


def test_crypto_still_wins_its_own_commands(planner):
    """`bitcoin price` must not be captured by `{symbol} price`-shaped patterns.
    Two skills quietly claiming one command is the ambiguity stage 1 refuses."""
    assert _route(planner, "bitcoin price").skill.name == "crypto_price"
    assert _route(planner, "what is the ethereum price").skill.name == "crypto_price"


def test_a_knowledge_question_is_not_swallowed_by_the_news(planner):
    """`{topic} news` is a broad pattern. It must not eat everything nearby."""
    assert _route(planner, "what is the capital of france").skill.name == "answer_question"
    assert _route(planner, "who is ada lovelace").skill.name == "answer_question"


def test_both_skills_are_read_only_and_tier_1(planner):
    """A price lookup and a headline read change nothing, so neither should sit
    behind a confirmation — and neither may be Tier 2 by accident."""
    for name in ("latest_news", "stock_price"):
        skill = planner.router.registry.get(name)
        assert skill.read_only is True
        assert skill.tier == 1
        assert skill.offline is False, f"{name} needs the network and must say so"
