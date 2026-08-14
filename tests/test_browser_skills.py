"""
Phase 3, tranche 3 — the browser surface.

Four commands typed into the app on 2026-08-13, and what came back:

    open Gmail                      ✓ Recipient set to 'recipient@example.com'!
                                      What is the subject of the email?
    open WhatsApp                   ✓ Opened WhatsApp. (correct)
    open youtube.com on my browser  I'm not sure how to do that yet.
    search web for YouTube          ✓ Found 5 web search results for
                                      'web for YouTube'.

Three separate defects, one shape: the substring chain decided routing before
anything could parse the command.

* `"gmail" in cmd_lower` sat ~70 lines above the launcher, so a request to open
  a website became a half-built email to a placeholder address.
* The launcher stripped the verb and gave up if more than three words were left,
  so "youtube.com on my browser" failed the count and fell through to
  `CoderAgent`, which honestly refuses what it cannot do.
* The search branch stripped `^(search for|search|...)` and searched for
  whatever remained, so the words saying *where* to search became part of *what*
  was searched for — and it reported five results, which is why nobody noticed.

Nothing here reaches the network: the agents are stubbed, because what is under
test is which handler a command reaches and with what.
"""

from __future__ import annotations

import pytest

from core.intent_patterns import MAX_APP_TOKENS
from core.planner import MasterPlanner


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture(autouse=True)
def stub_browser(planner, monkeypatch):
    """Never launch a browser or reach DuckDuckGo. Records the arguments."""
    planner.pending_clarification = None
    calls = {"opened": [], "searched": [], "researched": [], "launched": []}

    monkeypatch.setattr(
        planner.browser_agent, "open_app_or_website",
        lambda target: calls["opened"].append(target) or {
            "success": True, "message": f"✓ Opened {target}.", "target": target},
    )
    monkeypatch.setattr(
        planner.browser_agent, "web_search",
        lambda query, num_results=5: calls["searched"].append(query) or {
            "success": True, "query": query, "results": [],
            "message": f"✓ Found 0 web search results for '{query}'."},
    )
    monkeypatch.setattr(
        planner.browser_agent, "research_topic",
        lambda topic: calls["researched"].append(topic) or {
            "success": True, "topic": topic, "message": f"✓ Researched {topic}."},
    )
    # `_handle_whatsapp` opens the app through ComputerAgent, not BrowserAgent.
    monkeypatch.setattr(
        planner.computer_agent, "launch_application",
        lambda app: calls["launched"].append(app) or {
            "success": True, "app": app, "message": f"✓ Launched {app}."},
    )

    yield calls
    planner.pending_clarification = None


def _route(planner, command):
    """The skill a command reaches, without running it."""
    decision = planner.router.route(command)
    return (decision.skill.name if decision.skill else "(fallback)"), decision.slots


# ── open ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "command,target",
    [
        ("open gmail", "gmail"),
        ("open Gmail", "Gmail"),
        ("open notepad", "notepad"),
        ("open file explorer", "file explorer"),
        ("launch spotify", "spotify"),
        ("go to github.com", "github.com"),
        ("visit arxiv.org", "arxiv.org"),
        ("open the calculator", "calculator"),
        ("pull up my calendar", "calendar"),
        ("open the website example.com", "example.com"),
    ],
)
def test_launch_commands_reach_the_launcher(planner, stub_browser, command, target):
    planner._dispatch_to_agent(command, intent="browser", user_approved=False)
    assert stub_browser["opened"] == [target]


def test_open_gmail_is_not_an_email_command(planner, stub_browser):
    """
    The regression this tranche exists for. `"gmail" in cmd_lower` matched, and
    the email branch answered with "✓ Recipient set to 'recipient@example.com'!
    What is the subject of the email?" — a launch request turned into a message
    addressed to a placeholder, and it reported success while doing it.
    """
    res = planner._dispatch_to_agent("open gmail", intent="browser", user_approved=False)

    assert stub_browser["opened"] == ["gmail"]
    assert "recipient@example.com" not in res.get("message", "")
    assert res.get("pending_clarification") is not True
    assert planner.pending_clarification is None


def test_a_real_email_command_still_reaches_the_email_handler(planner):
    """
    Dropping bare "gmail" from the email keyword guard must not cost a real
    email command. Every phrasing that contained it also contains "mail to".
    """
    res = planner._dispatch_to_agent(
        "draft a gmail to bob@example.com", intent="communication", user_approved=False
    )
    assert res.get("pending_clarification") is True
    assert res.get("to") == "bob@example.com"


@pytest.mark.parametrize(
    "command",
    [
        "open youtube.com on my browser",
        "open youtube.com in my browser",
        "open youtube.com in chrome",
        "launch youtube.com on edge",
        "go to youtube.com in firefox",
    ],
)
def test_saying_which_browser_does_not_break_the_command(planner, stub_browser, command):
    """
    Four words after the verb, so the old word-count guard rejected it and the
    command fell all the way through to `CoderAgent`: "I'm not sure how to do
    that yet". Naming the browser is now matched by the pattern rather than
    counted against the target.
    """
    planner._dispatch_to_agent(command, intent="browser", user_approved=False)
    assert stub_browser["opened"] == ["youtube.com"]


def test_politeness_is_not_part_of_the_app_name(planner, stub_browser):
    planner._dispatch_to_agent("launch spotify please", intent="browser", user_approved=False)
    assert stub_browser["opened"] == ["spotify"]


def test_whatsapp_keeps_its_own_handler(planner, stub_browser):
    """
    `open whatsapp` could be served by the launcher, but the WhatsApp handler
    opens the app *and* says how to dictate a message from there. Routing it to
    the generic launcher would work and would silently drop that.
    """
    res = planner._dispatch_to_agent("open whatsapp", intent="browser", user_approved=False)

    assert stub_browser["launched"] == ["whatsapp"]
    assert stub_browser["opened"] == []
    assert "message" in res.get("message", "").lower()


# ── The word count that was load-bearing ─────────────────────────────────────
def test_a_sentence_is_not_an_app_name(planner):
    """
    The old guard's one good instinct: without a length bound, "open whatsapp
    and message papa saying hi" is an application called "whatsapp and message
    papa saying hi". The bound survives as the `:app` slot type, so this still
    falls through to the handler that can parse it.
    """
    assert _route(planner, "open whatsapp and message papa saying hi")[0] == "(fallback)"


def test_the_app_slot_bound_is_where_it_says_it_is(planner):
    assert MAX_APP_TOKENS == 3
    within = " ".join(["a"] * MAX_APP_TOKENS)
    beyond = " ".join(["a"] * (MAX_APP_TOKENS + 1))

    assert _route(planner, f"open {within}") == ("open_app_or_website", {"target": within})
    assert _route(planner, f"open {beyond}")[0] == "(fallback)"


def test_start_is_not_a_launch_verb(planner):
    """
    `start {target:app}` would match "start meeting recording", which belongs to
    the audio agent. The legacy chain still serves "start <app>", and it runs
    after that intercept — which is the only reason the verb can be left out.
    """
    assert _route(planner, "start meeting recording")[0] == "(fallback)"


# ── search ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "command,query",
    [
        # The screenshot case: it searched for "web for YouTube" and reported
        # five results, so the failure was invisible in the status.
        ("search web for YouTube", "YouTube"),
        ("search the web for YouTube", "YouTube"),
        ("search the internet for rust tutorials", "rust tutorials"),
        ("search online for cheap flights", "cheap flights"),
        ("search for python tutorials", "python tutorials"),
        ("search python tutorials", "python tutorials"),
        ("web search for python tutorials", "python tutorials"),
        ("google weather in delhi", "weather in delhi"),
        ("find rust tutorials online", "rust tutorials"),
        # Trailing punctuation belongs to the sentence, not to the query.
        ("search for what is a monad?", "what is a monad"),
    ],
)
def test_the_query_is_what_was_asked_for(planner, stub_browser, command, query):
    planner._dispatch_to_agent(command, intent="browser", user_approved=False)
    assert stub_browser["searched"] == [query]


def test_a_weak_classification_no_longer_reaches_generated_code(planner, stub_browser):
    """
    "search current AI news" classified `desktop_automation` at 0.33 and was
    dispatched to `CoderAgent`, which wrote a `web_scraper` script and ran it
    under `subprocess` — a live fetch `--block-network` cannot see, which is why
    that test took 40s and had to be marked `network`. Stage 1 now places it
    before any classification is consulted.
    """
    planner._dispatch_to_agent("search current AI news", intent="desktop_automation",
                               user_approved=False, confidence=0.33)
    assert stub_browser["searched"] == ["current AI news"]


def test_research_does_not_research_the_word_research(planner, stub_browser):
    """
    The verb-stripping regex listed every search verb except this one, so
    `research quantum computing` looked up "research quantum computing".
    """
    planner._dispatch_to_agent("research quantum computing", intent="browser",
                               user_approved=False)
    assert stub_browser["researched"] == ["quantum computing"]
    assert stub_browser["searched"] == []


def test_recall_still_beats_the_web_for_a_memory_lookup(planner):
    """
    `look up {query} in my memory` carries more literal text than any search
    pattern, so specificity — not registration order — keeps it.
    """
    assert _route(planner, "look up my exam in my memory")[0] == "recall_memory"
