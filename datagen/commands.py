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

# ── Fillers for the MONDAY-only surface ──────────────────────────────────────
# MASSIVE covers the phrasings people speak at an assistant; it has nothing for
# the things this app does to the machine it runs on, or to files on disk. Those
# capabilities are named in `/help`, and before this every one of them was
# absent from the corpus — which is why `battery` scored 0.26, `my ip` came back
# `memory_query`, and `summarise the file notes.txt` came back `browser` at 0.27.

# Real process names, because "kill {app}" is only useful if the corpus has seen
# what an app name looks like next to a kill verb.
_PROCESSES = ["notepad", "chrome", "spotify", "excel", "code", "python",
              "explorer", "teams", "zoom", "discord", "firefox", "outlook"]

# Local paths as a user actually types them — extension included, which is the
# token that separates a document command from a web one.
_FILES = ["README.md", "report.pdf", "notes.txt", "the invoice.pdf",
          "chapter3.pdf", "budget.xlsx", "minutes.docx", "syllabus.pdf",
          "data/sample.csv", "thesis.pdf", "requirements.txt", "resume.pdf"]

# Bare domains and URLs. `open {site}` used the plain-English site names above,
# so nothing in the corpus looked like "youtube.com".
_URLS = ["youtube.com", "github.com", "arxiv.org", "wikipedia.org", "gmail.com",
         "stackoverflow.com", "reddit.com", "linkedin.com", "example.com",
         "https://news.ycombinator.com", "docs.python.org", "kaggle.com"]

_BROWSERS = ["chrome", "edge", "firefox", "my browser", "the browser",
             "my default browser"]

# Indian mobile numbers in the shapes `normalise_phone` accepts. Synthetic and
# non-routable-looking on purpose: the 987654xxxx block is the one already used
# throughout /help and the tests.
_PHONES = ["9876543210", "+919876543210", "98765 43210", "+91 9876543210",
           "9123456780", "+919812345678"]

_CONTACTS = ["papa", "mummy", "bhumi", "rahul", "the landlord", "my roommate",
             "priyanka", "ahmed", "sara", "my manager"]

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
        # Commands naming an actual file. `summarise the file notes.txt`
        # classified `browser` at 0.27 — a filename with an extension looked more
        # like a URL than a document, because no document template had ever
        # contained one. MASSIVE has nothing here: nobody dictates a file path to
        # a smart speaker, so this class stays wholly generated.
        "summarize {file}", "summarise {file}", "summarize the file {file}",
        "give me a summary of {file}", "summarise the document {file}",
        "read {file}", "what's in {file}", "tl;dr {file}",
        "open {file} and summarise it", "key points from {file}",
        "summarize the pdf {file}", "condense {file} for me",
    ],
    "communication": [
        "email {person} the schedule", "send {person} a message",
        "reply to {person} saying I'll be late", "draft a thank you note to {person}",
        "message {person} about {topic}", "tell {person} the meeting moved to 4pm",
        "write an email to {person}", "forward the invoice to {person}",
        "cc {person} on the update", "ping {person} about {topic}",
        "schedule a call with {person}", "send {person} the notes on {topic}",
        "ask {person} to review {topic}", "draft a reply to {person} about {topic}",
        # WhatsApp. MASSIVE's `social_post` is posting to a feed, which is a
        # different act, so none of its 414 utterances could be reused here.
        "message {phone} saying hi", "message {contact} saying good morning",
        "whatsapp {phone}", "send a whatsapp to {contact}",
        "whatsapp {contact} about {topic}", "text {contact} that I'm running late",
        "message {contact} saying {topic} is ready",
        "open whatsapp", "open whatsapp and message {contact}",
        # The literal email syntax /help documents, which no template contained —
        # so the one command the demo script leans on hardest was unrepresented.
        'send mail to {person}@example.com subject "Hi" body "Hello"',
        "send mail to {person}@example.com", "mail to {person}@example.com",
        "draft mail to {person}@example.com about {topic}",
        "read latest email", "read my latest email", "check my inbox",
        "notify me when the build finishes", "send me a notification about {topic}",
        "schedule meeting tomorrow 3pm", "add a calendar event for {topic}",
    ],
    "browser": [
        "search {site} for {topic}", "open {site}",
        "look up the weather in {topic}", "find flights to Delhi on {site}",
        "google how to fix {topic}", "fill out the form on {site}",
        "download the file from {site}", "check the latest on {site}",
        "book a ticket on {site}", "compare prices on {site}",
        "log in to {site}", "find reviews of {topic} on {site}",
        "browse {site} for {topic}", "get directions to {topic}",
        # Opening a URL, which is a different shape from opening a named site.
        # "open youtube.com on my browser" reached CoderAgent because nothing in
        # the corpus — or in the router — had ever seen a bare domain.
        "open {url}", "open {url} on {browser}", "go to {url}", "visit {url}",
        "open {url} in {browser}", "pull up {url}", "launch {url}",
        # The literal search phrasings /help advertises. `search web for X` was
        # searching for "web for X" until 2026-08-13; the corpus had no example
        # of a user naming *where* to search.
        "search the web for {topic}", "search web for {topic}",
        "search for {topic}", "search {topic}", "google {topic}",
        "search the internet for {topic}", "look up {topic} online",
        "find {topic} on the web", "web search for {topic}",
        # Research is its own agent method with its own output shape.
        "research {topic}", "deep research on {topic}", "research about {topic}",
        # Live-info commands. Every one is in /help; none were in the corpus.
        # `bitcoin price` classified `desktop_automation` at 0.26.
        "bitcoin price", "what is the price of bitcoin", "ethereum price",
        "crypto prices", "how much is btc worth right now",
        "iss location", "where is the space station", "iss coordinates",
        "where am i", "what is my location", "what city am i in",
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
        # Battery. `battery` — a bare /help example — scored 0.26, because the
        # word appeared nowhere in 9,996 rows.
        "battery", "battery status", "battery level", "battery percentage",
        "what is my battery percentage", "how much charge is left",
        "am i charging", "power status", "is the laptop plugged in",
        # Network. `my ip` came back `memory_query` at 0.33.
        "my ip", "what is my ip address", "show my network info",
        "what's my local ip", "network details", "am i online",
        # Terminating a process — the Tier-2 desktop action.
        "kill {process}", "terminate {process}", "force close {process}",
        "end the {process} process", "kill the {process} app",
        # Launching, including the aliases the computer agent maps.
        "open file explorer", "open this pc", "open my computer",
        "open the calculator", "launch {app}", "open {app} for me",
        # What is on the desktop. Classified `chitchat` at 0.25 in live use on
        # 2026-08-10 and answered with an SEO article (data/DATASET.md cites it
        # as the known live gap — this is the fix).
        "how many files are on my desktop", "what is on my desktop",
        "list my desktop", "count the files on my desktop",
        "how many folders are on my desktop",
        # System health, more phrasings.
        "health", "system health", "how is my pc doing", "computer stats",
        "check disk space", "how much ram is free",
        # The audit log, which /help offers on every surface.
        "history", "show me the action log", "audit log", "recent actions",
        "what have you done today",
    ],
    "memory_query": [
        "what did I save about {topic}", "remember that the wifi password is on the fridge",
        "recall my notes on {topic}", "save this: {topic} is due friday",
        "what do you have on {topic}", "note that {person} prefers morning meetings",
        "show me everything about {topic}", "store {topic} for later",
        "did I write anything about {topic}", "remind me what {person} said about {topic}",
        "keep a note that {topic} is important", "look up my saved info on {topic}",
        "what do I know about {topic}", "add {topic} to my memory",
        # The literal remember/recall syntax from /help. `recall prof` scored
        # 0.40 — under the router's stage-2 floor — because "recall X" as a bare
        # two-word command appeared in no template.
        "recall {topic}", "recall my {topic}", "remember my {topic}",
        "remember that {topic} is on friday", "remember {topic} is important",
        "what did i say about {topic}", "what do you remember about {topic}",
        "look up {topic} in my memory",
        # Contacts. These must read as memory writes, not as WhatsApp sends —
        # `_handle_save_contact_number` exists precisely because they collided.
        "{contact}'s number is {phone}", "remember {contact} number is {phone}",
        "save {contact} number as {phone}", "{contact} number is {phone}",
        "what is {contact}'s number", "what's {contact}'s whatsapp number",
        "do you have {contact}'s number", "what is the number for {contact}",
        # Proactive suggestions — components 2.3 + 2.4, offered by /help on every
        # surface, and scoring 0.26 as a bare word.
        "proactive", "proactive suggestions", "any suggestions for me",
        "show me my habits", "what patterns have you noticed",
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
        process=rng.choice(_PROCESSES),
        file=rng.choice(_FILES),
        url=rng.choice(_URLS),
        browser=rng.choice(_BROWSERS),
        phone=rng.choice(_PHONES),
        contact=rng.choice(_CONTACTS),
    )
    return (rng.choice(_PREFIX) + text + rng.choice(_SUFFIX)).strip()


def generate_commands(
    n: int = 3000,
    seed: int = RANDOM_SEED,
    label_noise: float = 0.06,
    per_class: int | dict[str, int] | None = None,
) -> pd.DataFrame:
    """Return a shuffled DataFrame of unique ``(text, intent)`` rows.

    Balanced by class: each of the 7 intents targets ``n // 7`` *unique*
    commands. For each class we sample template+filler+noise combinations until
    the target is met (or the combinatorial space is exhausted), so the final
    dataset is both class-balanced and free of exact duplicates.

    ``per_class`` overrides ``n``, and may be a **dict** giving a different
    target for each intent. `build_corpus` uses that form to ask for exactly the
    shortfall MASSIVE could not cover, which differs per class — 0 extra rows for
    a class with 2,500 real ones, all 2,500 for `document_intel`, which MASSIVE
    has nothing for.

    ``label_noise`` is the fraction of rows whose label is flipped to a random
    *other* intent. This simulates real annotation ambiguity (many commands
    genuinely straddle two intents) and, together with the shared filler
    vocabulary, keeps the task learnable-but-not-trivial so the model comparison
    is informative. The flipped rows are documented, not hidden.
    """
    rng = random.Random(seed)
    if per_class is None:
        targets = {intent: n // len(TEMPLATES) for intent in TEMPLATES}
    elif isinstance(per_class, int):
        targets = {intent: per_class for intent in TEMPLATES}
    else:
        targets = {intent: max(0, per_class.get(intent, 0)) for intent in TEMPLATES}

    intents = list(TEMPLATES.keys())
    rows = []
    for intent, templates in TEMPLATES.items():
        target = targets[intent]
        seen: set[str] = set()
        attempts = 0
        max_attempts = target * 60  # generous guard against exhaustion
        while len(seen) < target and attempts < max_attempts:
            text = _inject_noise(_fill(rng.choice(templates), rng), rng)
            attempts += 1
            if text not in seen:
                seen.add(text)
                rows.append({"text": text, "intent": intent})

    if not rows:
        return pd.DataFrame(columns=["text", "intent"])

    # Inject label noise on a random subset.
    if label_noise > 0:
        k = int(len(rows) * label_noise)
        for i in rng.sample(range(len(rows)), k):
            true = rows[i]["intent"]
            rows[i]["intent"] = rng.choice([c for c in intents if c != true])

    df = pd.DataFrame(rows)
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


#: Generated rows guaranteed per class, whatever MASSIVE supplies.
#:
#: The first version of `build_corpus` topped up with generation only where
#: MASSIVE fell short. That looked principled and was wrong: MASSIVE filled
#: `browser` and `communication` outright, so those two classes got 88 and 98
#: generated rows — noise flips, nothing else — and **every MONDAY-specific
#: template for them was absent from the corpus**. Measured: `search web for
#: youtube` 0.29, `visit arxiv.org` 0.37, `iss location` 0.44, `whatsapp
#: +919876543210` misclassified at 0.26. The classes with the most real data
#: were the ones that had never seen the app's own commands.
#:
#: MASSIVE is a *voice assistant* corpus. It has no bare URLs, no `subject "…"
#: body "…"`, no WhatsApp, no `iss location`. Those phrasings only exist because
#: this generator writes them, so a floor of generated rows is not padding — it
#: is the only coverage the app's own surface will ever get.
MIN_GENERATED_PER_CLASS = 800


def build_corpus(
    per_class: int = 2500,
    seed: int = RANDOM_SEED,
    label_noise: float = 0.06,
    min_generated: int = MIN_GENERATED_PER_CLASS,
) -> pd.DataFrame:
    """The corpus 2.1 actually trains on: real utterances plus generated coverage.

    Each class targets `per_class` rows, of which at least `min_generated` are
    generated and the rest are real (Amazon MASSIVE, mapped by
    `datagen/massive.py`). A class MASSIVE covers well is mostly real; a class it
    has nothing for — `document_intel` — is entirely generated, with no pretence
    otherwise.

    **Label noise is applied to the generated rows only.** The 6% flip exists to
    stop a templated corpus being trivially separable (`data/DATASET.md`);
    corrupting real human labels to make a benchmark harder would be vandalism,
    and MASSIVE's ambiguity is already the genuine article.

    Returns `(text, intent, source)` — `source` is `massive` or `generated`, so
    every downstream metric can be split by provenance instead of taking the mix
    on trust.
    """
    from datagen.massive import load_massive

    real = load_massive()
    frames = []
    real_counts: dict[str, int] = {}
    real_budget = max(0, per_class - min_generated)

    if real is not None:
        real = real[["text", "intent"]].copy()
        real["source"] = "massive"
        # Deterministic subsample when a class has more than the budget, so the
        # corpus stays balanced and `seed` still reproduces it byte-for-byte.
        for intent, group in real.groupby("intent"):
            take = (
                group.sample(n=real_budget, random_state=seed)
                if len(group) > real_budget
                else group
            )
            real_counts[intent] = len(take)
            frames.append(take)

    shortfall = {
        intent: max(min_generated, per_class - real_counts.get(intent, 0))
        for intent in TEMPLATES
    }
    gen = generate_commands(
        per_class=shortfall, seed=seed, label_noise=label_noise
    )
    gen["source"] = "generated"
    frames.append(gen)

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=["text"]).reset_index(drop=True)
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
