"""Synthetic labeled-command generator for the Intent Classifier (2.1).

Produces 2k-5k rows of ``(text, intent)`` by combining hand-written templates
per intent with slot fillers and light paraphrasing. This is the documented
"synthesize from test usage + augment with paraphrasing" strategy from the
proposal — the assumptions live here in the open so the dataset is defensible.

The ``llm_fallback`` class is intentionally noisy/ambiguous: it represents the
commands a rule/keyword system *cannot* confidently route, which is exactly the
low-confidence bucket the RL router (2.5) later learns to handle.
"""

from __future__ import annotations

import random

import pandas as pd

from .config import RANDOM_SEED

# Slot fillers reused across templates. Kept broad so the template x filler
# space is large enough to yield a few thousand *unique* commands after dedup.
_DOCS = ["the PDF", "this report", "the invoice", "chapter 3", "the DBMS notes",
         "my resume", "the contract", "the lecture slides", "the syllabus",
         "the research paper", "the meeting minutes", "the spreadsheet",
         "the onboarding doc", "the whitepaper", "the assignment brief",
         "the release notes", "the user manual", "the financial statement"]
_PEOPLE = ["Priyanka", "the team", "my group", "Ahmed", "the professor", "mom",
           "Sara", "the client", "my manager", "the TA", "Rahul", "the vendor",
           "the recruiter", "my roommate", "the committee"]
_APPS = ["VS Code", "Chrome", "Spotify", "Excel", "the terminal", "Notion",
         "Slack", "Docker", "Postman", "Figma", "the file explorer", "Zoom",
         "OBS", "the database client", "the email app"]
_SITES = ["wikipedia", "the course portal", "arxiv", "github", "gmail",
          "stack overflow", "linkedin", "the library site", "youtube",
          "the docs page", "reddit", "the ticketing system"]
_TOPICS = ["the DBMS project", "last week's meeting", "my thesis", "the API keys",
           "the budget", "the reading list", "the travel plan", "the exam schedule",
           "the client call", "the grocery list", "the sprint goals",
           "the interview prep", "the wifi setup", "the conference deadline"]

# Per-intent templates. {slot} placeholders are filled from the lists above.
TEMPLATES = {
    "document_intel": [
        "summarize {doc}", "give me a summary of {doc}", "extract the tables from {doc}",
        "what does {doc} say about {topic}", "pull the key points from {doc}",
        "read {doc} and tell me the deadline", "find the total amount in {doc}",
        "tl;dr {doc}", "highlight the action items in {doc}",
        "compare {doc} against the requirements", "list every date mentioned in {doc}",
        "what's the conclusion of {doc}", "translate {doc} to plain english",
        "count how many times {topic} appears in {doc}",
    ],
    "communication": [
        "email {person} the schedule", "send {person} a message",
        "reply to {person} saying I'll be late", "draft a thank you note to {person}",
        "message {person} about {topic}", "tell {person} the meeting moved to 4pm",
        "write an email to {person}", "forward the invoice to {person}",
        "cc {person} on the update", "ping {person} about {topic}",
        "schedule a call with {person}", "send {person} the notes on {topic}",
        "ask {person} to review {topic}", "draft a reply to {person} about {topic}",
    ],
    "browser": [
        "search {site} for {topic}", "open {site}",
        "look up the weather in {topic}", "find flights to Delhi on {site}",
        "google how to fix {topic}", "fill out the form on {site}",
        "download the file from {site}", "check the latest on {site}",
        "book a ticket on {site}", "compare prices on {site}",
        "log in to {site}", "find reviews of {topic} on {site}",
        "browse {site} for {topic}", "get directions to {topic}",
    ],
    "desktop_automation": [
        "open {app}", "launch {app}", "close {app}", "run the project in {app}",
        "run my build script", "commit my changes and push", "open {app} and start the server",
        "restart {app}", "kill the process on port 3000", "clear the cache in {app}",
        "update {app} to the latest version", "back up the folder to my drive",
        "rename the files in the downloads folder", "open {app} and load {topic}",
        # System-settings control. The assistant ships these as headline
        # features, so leaving them out of the corpus made "change the volume
        # to 100%" classify as communication.
        "change the volume to 100%", "set the volume to 40", "turn the volume up",
        "turn the volume down", "mute the volume", "unmute the sound",
        "take a screenshot", "capture the current window",
        "turn up the brightness", "lower the screen brightness",
        "enable dark mode", "turn on wifi", "turn off bluetooth",
        "show me the system health", "check cpu and ram usage",
        "organize my downloads folder", "empty the recycle bin",
    ],
    "memory_query": [
        "what did I save about {topic}", "remember that the wifi password is on the fridge",
        "recall my notes on {topic}", "save this: {topic} is due friday",
        "what do you have on {topic}", "note that {person} prefers morning meetings",
        "show me everything about {topic}", "store {topic} for later",
        "did I write anything about {topic}", "remind me what {person} said about {topic}",
        "keep a note that {topic} is important", "look up my saved info on {topic}",
        "what do I know about {topic}", "add {topic} to my memory",
    ],
    "chitchat": [
        "hello", "hi {person}", "hey monday", "good morning", "good evening",
        "how are you today", "who are you", "what is your name",
        "thanks for the help", "thank you monday", "are you an AI",
        "tell me a joke", "how is the weather", "nice to meet you",
    ],
    # Ambiguous / underspecified — should be hard to route confidently.
    "llm_fallback": [
        "help me with this", "do the thing", "make it better",
        "can you handle {topic} for me", "sort everything out",
        "you know what I mean", "figure it out", "same as yesterday but faster",
        "plan my week around {topic}", "just deal with {topic}",
        "do whatever makes sense for {topic}", "fix {topic} somehow",
        "take care of {topic}", "handle the {topic} situation",
        "make {topic} work", "surprise me with {topic}",
    ],
}


# Domain-neutral filler that real users sprinkle across EVERY intent. Shared
# tokens like these deliberately blur the class boundaries so TF-IDF can't split
# the intents on trivially disjoint vocabulary — that's what makes the 5-model
# comparison meaningful instead of everyone scoring ~100%.
_PREFIX = ["", "", "", "please ", "can you ", "hey monday ", "i need to ",
           "could you ", "quick ", "i want to "]
_SUFFIX = ["", "", "", " please", " for me", " asap", " when you get a sec",
           " thanks", " now"]


def _fill(template: str, rng: random.Random) -> str:
    text = template.format(
        doc=rng.choice(_DOCS),
        person=rng.choice(_PEOPLE),
        app=rng.choice(_APPS),
        site=rng.choice(_SITES),
        topic=rng.choice(_TOPICS),
    )
    return (rng.choice(_PREFIX) + text + rng.choice(_SUFFIX)).strip()


def generate_commands(
    n: int = 3000, seed: int = RANDOM_SEED, label_noise: float = 0.06
) -> pd.DataFrame:
    """Return a shuffled DataFrame of unique ``(text, intent)`` rows.

    Balanced by class: each of the 7 intents targets ``n // 7`` *unique*
    commands. For each class we sample template+filler+noise combinations until
    the target is met (or the combinatorial space is exhausted), so the final
    dataset is both class-balanced and free of exact duplicates.

    ``label_noise`` is the fraction of rows whose label is flipped to a random
    *other* intent. This simulates real annotation ambiguity (many commands
    genuinely straddle two intents) and, together with the shared filler
    vocabulary, keeps the task learnable-but-not-trivial so the model comparison
    is informative. The flipped rows are documented, not hidden.
    """
    rng = random.Random(seed)
    per_class = n // len(TEMPLATES)
    intents = list(TEMPLATES.keys())
    rows = []
    for intent, templates in TEMPLATES.items():
        seen: set[str] = set()
        attempts = 0
        max_attempts = per_class * 60  # generous guard against exhaustion
        while len(seen) < per_class and attempts < max_attempts:
            text = _inject_noise(_fill(rng.choice(templates), rng), rng)
            attempts += 1
            if text not in seen:
                seen.add(text)
                rows.append({"text": text, "intent": intent})

    # Inject label noise on a random subset.
    if label_noise > 0:
        k = int(len(rows) * label_noise)
        for i in rng.sample(range(len(rows)), k):
            true = rows[i]["intent"]
            rows[i]["intent"] = rng.choice([c for c in intents if c != true])

    df = pd.DataFrame(rows)
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


def _inject_noise(text: str, rng: random.Random) -> str:
    roll = rng.random()
    if roll < 0.15:                       # random capitalization
        return text.capitalize()
    if roll < 0.22 and len(text) > 6:     # drop a character (typo)
        i = rng.randrange(len(text))
        return text[:i] + text[i + 1:]
    if roll < 0.30:                       # trailing punctuation
        return text + rng.choice([".", "!", " please", " pls", "?"])
    return text
