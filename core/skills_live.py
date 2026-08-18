"""
M.O.N.D.A.Y. — tranche 4: live data, public APIs, and questions.

Everything here was reached, in the legacy chain, by a list of substrings
evaluated in a fixed order:

    elif any(k in cmd_lower for k in ["bitcoin", "btc", "ethereum", "eth", ...]):

That list contains `"eth"`, so *m-**eth**-od*, *som-**eth**-ing* and
*wh-**eth**-er* were all answered with the price of Ethereum. It is the single
most-cited defect in this repo's history and the reason the router exists.

Two things in this tranche are more than a move:

* **`my ip` now answers locally.** Geolocation sat above it in the chain and
  swallowed it, so asking for an IP address returned a *public* IP and a city
  looked up over the network — from a third-party service, on a machine whose
  own adapters can simply be read. `/help` has always described `my ip` as
  "local network details"; now it is. `where am i` and `my location` still go
  to the geolocation lookup, because that is what they ask for.
* **Arithmetic is evaluated, not `eval`-ed.** See `core/arithmetic.py`: the old
  branch read `^` as Python's XOR, so `calculate 2^3` answered **1**.
"""

from __future__ import annotations

from typing import Any, Dict

import simplematch

from core.arithmetic import ArithmeticRefused, evaluate, format_result
from core.contracts import AgentResult, SystemQuery
from core.skills import Skill, SkillRegistry

# The coins the price lookup knows, as a slot type rather than an alternation,
# so the matched coin is *captured* instead of being recovered from the command
# afterwards with the substring test this module exists to delete. The mechanism
# is `simplematch.register_type`; see `core/intent_patterns.py` for `{name:app}`,
# the other type in use.
_COIN_IDS = {
    "bitcoin": "bitcoin", "btc": "bitcoin",
    "ethereum": "ethereum", "eth": "ethereum",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "solana": "solana", "sol": "solana",
    "cardano": "cardano", "ada": "cardano",
    "litecoin": "litecoin", "ltc": "litecoin",
}
simplematch.register_type("coin", "|".join(sorted(_COIN_IDS, key=len, reverse=True)))


def register_live_skills(registry: SkillRegistry, planner: Any) -> None:
    """Registers the live-data skills against a planner's agents."""

    # ── Where the user is ────────────────────────────────────────────────────
    def geolocation(**_: Any) -> Dict[str, Any]:
        return planner.public_api_agent.get_geolocation()

    registry.register(Skill(
        name="geolocation",
        read_only=True,
        description="Approximate location from the public IP",
        patterns=[
            "where am i",
            "[(what is|whats|what's)] my (location|city|country)",
            "[(what is|whats|what's)] my public ip",
            "where is my ip",
            "what city am i in",
        ],
        handler=geolocation,
        tier=1,
        offline=False,
    ))

    # Local adapters, read from this machine. The geolocation branch used to
    # claim this command; a question about "my ip" is answerable without asking
    # a third party where the user lives.
    def network_info(**_: Any) -> Dict[str, Any]:
        return planner.computer_agent.get_network_info()

    registry.register(Skill(
        name="network_info",
        read_only=True,
        description="Local IP address and network adapters",
        patterns=[
            "my ip",
            "[(what is|whats|what's)] my [local] ip [address]",
            "ip address",
            "network (info|information|details)",
        ],
        handler=network_info,
        tier=1,
        offline=True,
    ))

    # ── Weather ──────────────────────────────────────────────────────────────
    # The old branch pulled the location with
    # `re.search(r'weather\\s+(?:in|for|at)?\\s+([^\\s,"]+)')`, which reads the
    # word after "weather" whatever it is — "weather today" looked up the
    # weather in a city called "today". A slot binds it to the preposition.
    def weather(location: str = "", **_: Any) -> Dict[str, Any]:
        return planner.public_api_agent.get_weather(location.strip().strip("\"'"))

    registry.register(Skill(
        name="weather",
        read_only=True,
        description="Current weather, here or in a named place",
        patterns=[
            "[(what is|whats|what's)] [the] weather",
            "[(what is|whats|what's)] [the] weather [(like)] (in|for|at) {location}",
            "[(what is|whats|what's)] [the] weather (today|right now|outside|tomorrow|this week)",
            "temperature",
            "temperature (in|for|at) {location}",
            "forecast",
            "forecast (in|for|at) {location}",
            "[(how is|hows|how's)] [the] weather (in|for|at) {location}",
            # The corpus asks about the sky, not about "the weather": 36 of the
            # misses start "do i need", 31 "is it going to", 21 "should i wear".
            "[(how is|hows|how's)] [the] weather [(like)] [(today|outside|now|right now)]",
            "(tell|show|give|get) me [the] (weather|forecast|temperature)",
            "(tell|show|give|get) me [the] (weather|forecast|temperature) [(in|for|at)] {location}",
            "(tell|show|give|get) me [the] (weather|forecast) (today|tomorrow|this week)",
            "is it (raining|snowing|sunny|cloudy|windy|hot|cold|warm|freezing)",
            "is it (raining|snowing|sunny|cloudy|windy|hot|cold|warm|freezing) (now|today|outside|right now)",
            "is it (raining|snowing|sunny|cloudy|windy|hot|cold|warm) (in|at) {location}",
            "is it going to (rain|snow|be sunny|be cold|be hot)",
            "is it going to (rain|snow) (today|tomorrow|tonight|this week)",
            "is it going to (rain|snow) in {location}",
            "will it (rain|snow|be sunny|be cold|be hot|be warm)",
            "will it (rain|snow) (today|tomorrow|tonight|this week)",
            "will it (rain|snow) in {location}",
            "do i need (an umbrella|a jacket|a coat|a sweater|sunscreen)",
            "do i need (an umbrella|a jacket|a coat|a sweater) (today|tomorrow)",
            "should i (wear|bring|take) (an umbrella|a jacket|a coat|a sweater)",
            "(weather|forecast) (today|tomorrow|tonight|this week)",
        ],
        handler=weather,
        tier=1,
        offline=False,
    ))

    # ── Crypto ───────────────────────────────────────────────────────────────
    def crypto_price(coin: str = "", **_: Any) -> Dict[str, Any]:
        ids = _COIN_IDS.get(coin.strip().lower(), "") if coin else ""
        return planner.public_api_agent.get_crypto_prices(ids or "bitcoin,ethereum")

    registry.register(Skill(
        name="crypto_price",
        read_only=True,
        description="Live cryptocurrency prices — Bitcoin, Ethereum and other coins only, never company shares",
        patterns=[
            "[(what is|whats|what's)] [the] {coin:coin} (price|rate|value)",
            "[(what is|whats|what's)] [the] price of [(a|one)] {coin:coin}",
            "{coin:coin} (price|rate|value)",
            "how much is [(a|one)] {coin:coin}",
            "crypto (price|prices|rates)",
            "[(what are|whats|what's)] [the] crypto (price|prices|rates)",
        ],
        handler=crypto_price,
        tier=1,
        offline=False,
    ))

    # ── News ─────────────────────────────────────────────────────────────────
    #
    # 707 of MASSIVE's utterances are `news_query` and MONDAY served none of
    # them: 32% "routed", almost all to `answer_question`, which looks the
    # headline up on Wikipedia. The patterns here are the shapes that corpus
    # actually contains — "tell me the latest technology news", "what's
    # happening in the world", "give me the headlines" — not a guess at them.
    def latest_news(topic: str = "", **_: Any) -> Dict[str, Any]:
        return planner.public_api_agent.get_latest_news(topic.strip().strip("\"'"))

    registry.register(Skill(
        name="latest_news",
        read_only=True,
        description="Live news headlines from the news feed, overall or on one topic — current events, not encyclopaedia facts",
        patterns=[
            "[(what is|whats|what's)] [the] [(latest|today's|todays|current)] news",
            "[(what are|whats|what's)] [the] [(latest|today's|todays|top)] (headlines|stories)",
            "(top|breaking|latest) (news|headlines|stories)",
            "news",
            "headlines",
            "(tell|show|give|get|read|fetch|find) me [(the|some|any)] [(latest|today's|todays)] news",
            "(tell|show|give|get|read|fetch|find) me [(the|some|any)] [(latest|today's|todays)] (headlines|stories)",
            "(tell|show|give|get|read|fetch|find) me [(the|some|any)] [(latest|today's|todays)] {topic} news",
            "(tell|show|give|get|read|fetch|find) me [(the|some|any)] news (about|on|in|from|regarding) {topic}",
            "[(the|some|any)] [(latest|today's|todays)] news (about|on|in|from|regarding) {topic}",
            "{topic} news",
            "news headlines (about|on|in|from) {topic}",
            "[(what is|whats|what's)] (happening|going on) in [the] {topic}",
            "[(what is|whats|what's)] [the] news (about|on|in|from) {topic}",
            "[(is|are)] there any [(new|latest)] news (about|on|regarding) {topic}",
            "update me on [the] news",
            "catch me up on [the] news",
        ],
        handler=latest_news,
        tier=1,
        offline=False,
    ))

    # ── Stock prices ─────────────────────────────────────────────────────────
    #
    # `qa_stock` is 200 real utterances and the app had only `crypto_price`, so
    # "tell me price of ifci stock" reached nothing at all. The symbol is
    # resolved from the name by Yahoo's search endpoint, because people type
    # "ifci", not "IFCI.NS".
    def stock_price(symbol: str = "", **_: Any) -> Dict[str, Any]:
        return planner.public_api_agent.get_stock_price(symbol.strip().strip("\"'"))

    registry.register(Skill(
        name="stock_price",
        read_only=True,
        description="Live share price of a listed company or ticker (NSE, BSE, NASDAQ) — shares, not cryptocurrency",
        patterns=[
            "[(what is|whats|what's)] [the] [current] (stock|share) price (of|for) {symbol}",
            "[(what is|whats|what's)] [the] [current] price of {symbol} (stock|stocks|share|shares)",
            "[(what is|whats|what's)] {symbol} (stock|share) price",
            "(stock|share) price (of|for) {symbol}",
            "{symbol} (stock|share) price",
            "(tell|show|give|get|find|fetch) me [the] [current] (stock|share) price (of|for) {symbol}",
            "(tell|show|give|get|find|fetch) me [the] [current] price of {symbol} (stock|stocks|share|shares)",
            "(tell|show|give|get|find|fetch) me [the] {symbol} (stock|share) price",
            "how (is|are) {symbol} (stock|stocks|share|shares) doing",
            "how much (is|are) {symbol} (stock|stocks|share|shares) [worth]",
            "{symbol} (stock|shares) [(price|quote|value)]",
            "quote for {symbol}",
        ],
        handler=stock_price,
        tier=1,
        offline=False,
    ))

    # ── The space station ────────────────────────────────────────────────────
    def iss_location(**_: Any) -> Dict[str, Any]:
        return planner.public_api_agent.get_iss_location()

    registry.register(Skill(
        name="iss_location",
        read_only=True,
        description="Where the ISS is right now",
        patterns=[
            "iss location",
            "iss coordinates",
            "where is [the] (iss|space station|international space station)",
            "[(what is|whats|what's)] [the] iss location",
        ],
        handler=iss_location,
        tier=1,
        offline=False,
    ))

    # ── Jokes ────────────────────────────────────────────────────────────────
    def joke(**_: Any) -> Dict[str, Any]:
        res = planner.public_api_agent.execute_dynamic_api(
            "https://v2.jokeapi.dev/joke/Any?safe-mode"
        )
        data = res.get("data") if res.get("success") else None
        if not data:
            # Failing to fetch a joke is not an occasion to invent one. Say what
            # happened and stop.
            return AgentResult.failed(
                "I couldn't reach the joke service just now.",
                error=res.get("error", "JOKE_API_UNAVAILABLE"),
            ).as_dict()
        text = (
            data.get("joke")
            if data.get("type") == "single"
            else f"{data.get('setup')} … {data.get('delivery')}"
        )
        res["message"] = f"✓ {text}"
        res["speech"] = str(text)
        res["intent"] = "joke"
        return res

    registry.register(Skill(
        name="tell_joke",
        read_only=True,
        description="Fetch a joke from a public API",
        patterns=[
            "joke",
            "tell me a joke",
            "[(say|tell me)] something funny",
            "make me laugh",
        ],
        handler=joke,
        tier=1,
        offline=False,
    ))

    # ── Arithmetic ───────────────────────────────────────────────────────────
    # `{expression:math}` and `{topic}` (below) carry the same literal text, so
    # the typed slot is what separates "what is 12 * 8" from "what is a tesseract".
    # See `core.intent_patterns.typed_slots`.
    def calculate(expression: str = "", **_: Any) -> Dict[str, Any]:
        raw = expression.strip()
        try:
            value = evaluate(raw)
        except ArithmeticRefused as exc:
            return AgentResult.failed(
                f"I can't work that out — {exc}.", error="BAD_EXPRESSION"
            ).as_dict()
        shown = format_result(value)
        return AgentResult.ok(
            f"✓ {raw} = {shown}",
            evidence=SystemQuery(source="arithmetic evaluator", detail=raw),
            data={"intent": "calculator", "expression": raw, "result": value,
                  "speech": f"That's {shown}."},
        ).as_dict()

    registry.register(Skill(
        name="calculate",
        read_only=True,
        description="Evaluate an arithmetic expression",
        patterns=[
            # Every one of these keeps a mandatory verb, for the reason
            # `is_anchored` enforces: making it optional expands to a bare
            # `{expression:math}`, and a pattern that is nothing but a slot
            # announces nothing about what it will capture.
            "(calculate|compute|evaluate|work out) {expression:math}",
            "(what is|whats|what's) {expression:math}",
            "(what is|whats|what's) {expression:math} equal to",
            "(what does|whats|what's) {expression:math} (equal|come to)",
        ],
        handler=calculate,
        tier=1,
        offline=True,
    ))

    # ── Questions ────────────────────────────────────────────────────────────
    # The last thing to leave the chain, and the broadest. It answers a question
    # from Wikipedia where there is an article, and from a web search where
    # there is not — which is what the legacy pair of branches did between them,
    # except that they disagreed about which one got to go first and the
    # Wikipedia branch gave up on any topic longer than five words.
    #
    # These patterns are deliberately the least specific in the registry. Every
    # skill that answers a question about the machine, the user, or their own
    # data carries more literal text ("what is the current volume", "what did i
    # say about {query}", "how many files are on my desktop") and therefore
    # outranks them. That ordering used to be a matter of which `elif` came
    # first; now it is a property of the patterns and is asserted per command in
    # `reports/routing_evidence.py`.
    _MAX_WIKI_WORDS = 6

    def answer_question(topic: str = "", _command: str = "", **_: Any) -> Dict[str, Any]:
        query = (topic or _command).strip().strip("\"'").rstrip("?").strip()
        if not query:
            return AgentResult.failed(
                "What would you like to know?", error="NO_QUESTION"
            ).as_dict()

        # Wikipedia first: it is a cited encyclopaedia answer rather than a
        # scraped snippet. Phrasal topics ("the capital of France") have no
        # article, so a miss falls through instead of being reported as one.
        if len(query.split()) <= _MAX_WIKI_WORDS:
            wiki = planner.public_api_agent.get_wikipedia_summary(query)
            if wiki.get("success"):
                return wiki

        search = planner.browser_agent.web_search(query, num_results=3)
        results = search.get("results", [])
        if not results:
            return AgentResult.failed(
                f"I couldn't find an answer for '{query}'.",
                error=search.get("error", "NO_WEB_RESULTS"),
                data={"query": query},
            ).as_dict()

        top = results[0]
        return {
            "success": True,
            "intent": "knowledge_question",
            "query": query,
            "sources_consulted": len(results),
            "results": results,
            "evidence": search.get("evidence"),
            "message": f"✓ {top['snippet']}\n\nSource: {top['title']} — {top['url']}",
        }

    registry.register(Skill(
        name="answer_question",
        read_only=True,
        description="Answer a general-knowledge or factual question from Wikipedia or the web — established facts, not today's headlines",
        patterns=[
            "(who is|who was|who are|who were) {topic}",
            "(what is|what are|what was|whats|what's) {topic}",
            "(when is|when was|when did|when does) {topic}",
            "(where is|where was|where are) {topic}",
            "(why is|why are|why does|why do|why did) {topic}",
            "(which is|which are) {topic}",
            "(how is|how are|how does|how do|how did|how much|how many) {topic}",
            "tell me [(something|more)] about {topic}",
            "explain {topic}",
            "wikipedia {topic}",
            "look up {topic} on wikipedia",
        ],
        handler=answer_question,
        tier=1,
        offline=False,
    ))
