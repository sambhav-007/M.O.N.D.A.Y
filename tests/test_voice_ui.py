"""The browser-side voice logic — wake word, echo suppression, barge-in.

`ui/index.html` carries the only speech path in the app. There is no backend
TTS on this machine (gTTS and pyttsx3 are both absent), so `speechSynthesis` is
what the user actually hears, and `webkitSpeechRecognition` is what hears them.
That makes the JavaScript in `Voice` load-bearing, and untested JavaScript in a
643-line HTML file is exactly where a regression hides.

Rather than duplicate the logic in Python — which would test a copy and let the
shipped code drift away from it — this extracts the `Voice` object *from
index.html* and runs it under node. If it does not match what ships, the test
is not testing anything.

Skipped when node is unavailable. The app does not need node; only this test
does.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX = PROJECT_ROOT / "ui" / "index.html"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None, reason="node is not installed"
)

# Minimal stand-ins for the three browser globals `Voice` touches. Anything more
# would be re-implementing a browser; anything less and it will not load.
#
# `speak()` is deliberately a no-op that never fires `onstart`. That models the
# real browser: `onstart` is asynchronous and arrives well after `speak()`
# returns, which is the gap `isTalking()` exists to cover.
PRELUDE = """
global.SpeechSynthesisUtterance = class { constructor(text) { this.text = text; } };
global.window = {
  SpeechSynthesisUtterance: global.SpeechSynthesisUtterance,
  speechSynthesis: {
    speaking: false,
    pending: false,
    speak(){},
    cancel(){ this.speaking = false; this.pending = false; },
  },
};
global.document = { getElementById: () => null };
global.setEntityMode = () => {};
global.sendCommand = () => {};
"""


def _voice_source() -> str:
    """Lifts the `Voice` object verbatim out of the shipped HTML."""
    html = INDEX.read_text(encoding="utf-8")
    start = html.index("const Voice = {")
    end = html.index("const IDLE_CAPTION")
    return html[start:end].rstrip().rstrip(";")


def _run_js(script: str):
    source = f"{PRELUDE}\n{_voice_source()};\n{script}"
    # `encoding="utf-8"` is not optional: the extracted source carries the em
    # dashes and emoji from index.html's comments and captions, and Windows
    # would otherwise pipe it as cp1252 and fail before node sees it.
    proc = subprocess.run(
        ["node", "-"],
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _wake(*phrases):
    calls = ", ".join(f"Voice.afterWakeWord({json.dumps(p)})" for p in phrases)
    return _run_js(f"console.log(JSON.stringify([{calls}]))")


# ── Wake word ────────────────────────────────────────────────────────────────
def test_the_wake_phrase_is_consumed_and_the_command_is_not():
    assert _wake(
        "hey monday",
        "hey monday open gmail",
        "hello monday battery",
        "ok monday set volume to 40",
    ) == ["", "open gmail", "battery", "set volume to 40"]


def test_the_wake_phrase_allows_to_between_greeting_and_name():
    assert _wake(
        "hi to monday",
        "hello to monday battery",
        "hey to monday what time is it",
    ) == ["", "battery", "what time is it"]


def test_apostrophes_survive_the_wake_word():
    """
    The regression this exists for. The first version flattened punctuation to
    spaces before searching *and returned the flattened string*, so "hey monday
    what's the time" became "what s the time" — which matches no skill pattern,
    because those are written with the apostrophe ("what's my name",
    "papa's number"). The command is now sliced out of the original text.
    """
    assert _wake(
        "Hey Monday, what's the time",
        "okay monday what's my name",
        "hey monday what's papa's number",
    ) == ["what's the time", "what's my name", "what's papa's number"]


def test_case_survives_the_wake_word():
    """Proper nouns reach the handler as typed — "message Shivansh", not "shivansh"."""
    assert _wake("hey monday message Shivansh hello") == ["message Shivansh hello"]


def test_mishearings_still_wake_it():
    """
    Speech recognition mangles the greeting constantly, and a wake word that
    misses is a feature that does not work. These are real transcriptions.
    """
    assert _wake(
        "Heyy Monday open gmail",
        "hay munday battery",
        "hey mondey proactive",
        "helloo monday health",
        "monday what's my name",          # greeting clipped off entirely
    ) == ["open gmail", "battery", "proactive", "health", "what's my name"]


def test_interim_wake_arms_immediately_without_running_the_final_wake_as_a_command():
        assert _run_js(r'''
            global.setTimeout = () => 1;
            global.clearTimeout = () => {};
            const input = { value: '' };
            const commands = [];
            global.document = { getElementById: id => id === 'cmd-input' ? input : null };
            global.sendCommand = () => commands.push(input.value);
            const result = (transcript, isFinal) => Object.assign([{ transcript }], { isFinal });

            Voice.live = true;
            Voice.onResult({ resultIndex: 0, results: [result('Hey Monday', false)] });
            const armedOnInterim = Voice.awake;
            Voice.onResult({ resultIndex: 0, results: [result('Hey Monday', true)] });
            const ignoredDuplicateWake = commands.length === 0 && Voice.awake;
            Voice.onResult({ resultIndex: 0, results: [result('what time is it', true)] });

            console.log(JSON.stringify([armedOnInterim, ignoredDuplicateWake, commands, Voice.awake]));
        ''') == [True, True, ['what time is it'], False]


def test_interim_wake_and_command_in_one_final_transcript_runs_only_the_command():
        assert _run_js(r'''
            global.setTimeout = () => 1;
            global.clearTimeout = () => {};
            const input = { value: '' };
            const commands = [];
            global.document = { getElementById: id => id === 'cmd-input' ? input : null };
            global.sendCommand = () => commands.push(input.value);
            const result = (transcript, isFinal) => Object.assign([{ transcript }], { isFinal });

            Voice.live = true;
            Voice.onResult({ resultIndex: 0, results: [result('Hello Monday', false)] });
            Voice.onResult({ resultIndex: 0, results: [result('Hello, Monday, battery', true)] });
            console.log(JSON.stringify([commands, Voice.awake]));
        ''') == [['battery'], False]


def test_speech_not_addressed_to_monday_is_ignored():
    """
    The point of a wake word. Always-on listening that acts on everything is
    unusable in a room with other people in it.
    """
    assert _wake(
        "what time is it",
        "I'll see you on Tuesday then",
        "no I told him the deadline was friday",
    ) == [None, None, None]


# ── Echo suppression ─────────────────────────────────────────────────────────
def test_monday_does_not_interrupt_itself():
    """
    The microphone hears the speakers. Without this the assistant barges in on
    its own voice and cuts every reply off after three words.
    """
    assert _run_js("""
      Voice.lastSpoken = "Your name is Sambhav Sehgal.";
      console.log(JSON.stringify([
        Voice.isEcho("your name is sambhav"),
        Voice.isEcho("name is sambhav sehgal"),
        Voice.isEcho("stop, open gmail instead")
      ]));
    """) == [True, True, False]


def test_nothing_is_an_echo_when_nothing_is_being_said():
    assert _run_js("""
      Voice.lastSpoken = "";
      console.log(JSON.stringify(Voice.isEcho("anything at all")));
    """) is False


# ── Barge-in ─────────────────────────────────────────────────────────────────
def test_speaking_over_monday_stops_it():
    """
    Barge-in runs on *interim* results — text that arrives while the user is
    still mid-word. Waiting for a final result would be far too late to feel
    like an interruption.
    """
    assert _run_js("""
      Voice.speaking = true;
      Voice.lastSpoken = "Found five web search results for YouTube.";
      const stopped = Voice.maybeBargeIn("actually stop");
      console.log(JSON.stringify([stopped, Voice.speaking]));
    """) == [True, False]


def test_barge_in_works_before_the_voice_has_actually_started():
    """
    `speaking` used to be set in the utterance's `onstart`, which is
    asynchronous — a hundred milliseconds or more after `speak()` returns.
    Interrupting inside that gap did nothing, so barging in the instant a reply
    arrived, which is the most natural moment to do it, was precisely when it
    failed. Verified against a real `speechSynthesis` in a browser; here the
    stub reproduces the ordering.
    """
    assert _run_js("""
      Voice.speak("A long sentence we intend to interrupt part way through.");
      const talkingRightAway = Voice.isTalking();   // before onstart fires
      const cancelled = Voice.maybeBargeIn("stop talking please");
      console.log(JSON.stringify([talkingRightAway, cancelled, Voice.speaking]));
    """) == [True, True, False]


def test_its_own_voice_does_not_trigger_barge_in():
    assert _run_js("""
      Voice.speaking = true;
      Voice.lastSpoken = "Found five web search results for YouTube.";
      console.log(JSON.stringify(Voice.maybeBargeIn("found five web search")));
    """) is False


def test_a_cough_does_not_trigger_barge_in():
    assert _run_js("""
      Voice.speaking = true; Voice.lastSpoken = "x";
      console.log(JSON.stringify(Voice.maybeBargeIn("uh")));
    """) is False


def test_nothing_to_stop_when_silent():
    assert _run_js("""
      Voice.speaking = false;
      console.log(JSON.stringify(Voice.maybeBargeIn("hello there")));
    """) is False


# ── Wiring ───────────────────────────────────────────────────────────────────
def test_the_ui_speaks_the_short_form_not_the_message():
    """
    `execution_result.speech` is what `core/speech.py` decided to say;
    `.message` is what belongs on screen. Passing `.message` to the synthesiser
    is what had it reading a whole scraped search result aloud, and reciting a
    Tier-2 prompt including "can't be undone · est. 1s".
    """
    html = INDEX.read_text(encoding="utf-8")
    assert "exec.speech || msg" in html
    assert "speakText(msg)" not in html, "the UI is speaking the on-screen text again"


def test_the_ui_prefers_a_natural_voice_and_human_pacing():
    html = INDEX.read_text(encoding="utf-8")
    assert "Microsoft Aria Online (Natural)" in html
    assert "Microsoft Jenny Online (Natural)" in html
    assert "u.rate = 0.98" in html
    assert "u.pitch = 1.02" in html


def test_multiline_results_preserve_help_menu_formatting():
    html = INDEX.read_text(encoding="utf-8")
    assert 'class="whitespace-pre-wrap break-words"' in html


def test_recognition_is_continuous_with_interim_results():
    """
    Both are required. `continuous` keeps the session alive between utterances;
    `interimResults` is what makes barge-in possible at all.
    """
    html = INDEX.read_text(encoding="utf-8")
    assert "rec.continuous = true" in html
    assert "rec.interimResults = true" in html
