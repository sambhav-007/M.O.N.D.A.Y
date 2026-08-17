"""
Phase 7 — the backend can speak, and hear, without the network.

Two seams, `voice/tts.py` and `voice/stt.py`, each with the same obligation:
**say which engine did it.** "MONDAY has a voice" is not a useful claim when
there are three possible sources and two are usually absent, and neither is
"MONDAY heard you" when one recogniser is on this machine and the other is a
Google endpoint.

The tests here run with synthesis faked (see `no_audio_output` in `conftest.py`)
because a suite that drives a sound card is slow and audible — that fixture
exists because this change made the run go from 68 seconds to 482 before it was
added. The engines are exercised for real in the round-trip test at the bottom,
which is skipped unless both are actually installed.
"""

from __future__ import annotations

import wave
from pathlib import Path

import pytest

from agents.voice_agent import VoiceAgent
from voice import stt, tts


# ── Which engine, and never a claim without one ──────────────────────────────
@pytest.mark.real_audio
def test_no_engine_is_reported_as_unavailable_not_as_silence(monkeypatch, tmp_path):
    """The failure `MondayVoiceModel.synthesize_speech` used to get wrong.

    It returned `success: True` when gTTS had raised *and* pyttsx3 was absent,
    so it reported speech when no audio existed anywhere.
    """
    monkeypatch.setattr(tts, "available_engine", lambda: "")
    result = tts.synthesize("hello", tmp_path / "out.wav")
    assert result.ok is False
    assert result.error == "TTS_UNAVAILABLE"
    assert "install" in result.detail.lower()


@pytest.mark.real_audio
def test_empty_text_is_refused_before_any_engine_is_started(tmp_path):
    assert tts.synthesize("   ", tmp_path / "out.wav").error == "EMPTY_TEXT"


def test_synthesis_can_be_switched_off_entirely(monkeypatch):
    """`MONDAY_TTS=off` exists because the desktop UI speaks in the browser."""
    monkeypatch.setenv("MONDAY_TTS", "off")
    assert tts.available_engine() == ""


@pytest.mark.real_audio
def test_a_file_that_was_not_written_is_not_reported_as_speech(monkeypatch, tmp_path):
    """`pyttsx3.save_to_file` reports nothing, so the file is the evidence.

    Without checking it, a failed write would be announced as speech — which is
    precisely the bug this module was written to end.
    """
    class _Engine:
        def save_to_file(self, text: str, path: str) -> None:
            pass  # writes nothing at all

        def runAndWait(self) -> None:
            pass

    pyttsx3 = pytest.importorskip("pyttsx3")
    monkeypatch.setattr(pyttsx3, "init", lambda *a, **k: _Engine())
    result = tts._sapi5("hello", tmp_path / "missing.wav")
    assert result.ok is False
    assert result.error == "TTS_WROTE_NOTHING"


@pytest.mark.real_audio
def test_playing_a_file_that_does_not_exist_is_false(tmp_path):
    assert tts.play(tmp_path / "nope.wav") is False


# ── The agent reports what actually happened ─────────────────────────────────
def test_speaking_witnesses_a_file_not_a_thread(no_audio_output):
    """`speak` waited on a thread and returned `TaskQueued` — "a thread exists",
    which is true and nearly useless. It writes a file now, so there is
    something real to witness."""
    agent = VoiceAgent()
    result = agent.speak("testing one two")

    assert result["success"] is True
    assert result["evidence"]["kind"] == "file_written"
    assert result["engine"] == "fake"
    assert no_audio_output == ["testing one two"]


def test_speech_and_playback_are_separate_claims(no_audio_output):
    """Whether audio was synthesised and whether it reached the speakers are
    different facts, and `play` only reports that playback *started*."""
    result = VoiceAgent().speak("hello")
    assert "playback_started" in result
    assert result["audio_path"]


def test_a_failed_synthesis_is_a_failure(monkeypatch):
    monkeypatch.setattr(
        tts, "synthesize",
        lambda text, out: tts.Spoken(ok=False, error="TTS_UNAVAILABLE", detail="none installed"),
    )
    result = VoiceAgent().speak("hello")
    assert result["success"] is False
    assert result["error"] == "TTS_UNAVAILABLE"


def test_disabled_voice_says_so(monkeypatch):
    agent = VoiceAgent()
    agent.set_voice_enabled(False)
    assert agent.speak("hello")["error"] == "VOICE_DISABLED"


# ── Hearing, offline ─────────────────────────────────────────────────────────
def test_no_model_is_reported_as_not_configured(monkeypatch):
    """A missing 50 MB download is a setup state, not a recognition failure."""
    monkeypatch.setattr(stt, "vosk_available", lambda: False)
    heard = stt.transcribe_pcm(b"\x00\x00" * 100)
    assert heard.ok is False
    assert heard.error == "VOSK_UNAVAILABLE"
    assert "MONDAY_VOSK_MODEL" in heard.detail


def test_no_audio_is_distinguished_from_no_speech(monkeypatch):
    assert stt.transcribe_pcm(b"").error == "NO_AUDIO"


def test_silence_is_not_a_recogniser_failure():
    """Reporting "recognition failed" when the user simply did not speak sends
    them to debug a microphone that is fine."""
    if not stt.vosk_available():
        pytest.skip("no Vosk model installed")
    heard = stt.transcribe_pcm(b"\x00\x00" * 16000)  # one second of digital silence
    assert heard.ok is False
    assert heard.error == "NO_SPEECH"
    assert heard.engine == "vosk"


# ── Who speaks — the double-speak rule ───────────────────────────────────────
def test_the_backend_is_silent_by_default(no_audio_output):
    """The desktop UI speaks in the browser, with barge-in. If the backend also
    spoke, every reply would be said twice — the defect that took three attempts
    to kill, and was only "fixed" last time by the accident of no engine being
    installed. Phase 7 ends that accident, so the rule is now explicit."""
    from core.planner import MasterPlanner

    planner = MasterPlanner()
    assert planner.enable_voice is False, (
        "MasterPlanner speaks by default again — the UI will double every reply"
    )
    planner.process_command("what time is it")
    assert no_audio_output == [], f"the backend spoke unasked: {no_audio_output}"


def test_the_cli_turns_it_on_because_a_terminal_has_no_browser():
    """Asserted against the source: the CLI is the one surface that must speak,
    and a refactor that quietly dropped the line would leave it mute with no
    test failing anywhere else."""
    source = (Path(__file__).resolve().parent.parent / "cli.py").read_text(encoding="utf-8")
    assert "enable_voice = True" in source


# ── End to end, for real ─────────────────────────────────────────────────────
@pytest.mark.real_audio
@pytest.mark.parametrize("phrase", ["what is the battery level"])
def test_speak_then_hear_it_back_with_no_network(tmp_path, phrase, monkeypatch):
    """The Phase 7 claim, end to end: MONDAY says something and understands it
    back, with nothing leaving the machine.

    Unfaked on purpose — this is the one test that exercises the real engines,
    and it is skipped where they are not installed rather than asserting a
    capability the machine does not have.
    """
    monkeypatch.delenv("MONDAY_TTS", raising=False)
    # Undo the suite-wide interception for this test only.
    import importlib

    real_tts = importlib.reload(tts)
    if not real_tts.available_engine():
        pytest.skip("no TTS engine installed")
    if not stt.vosk_available():
        pytest.skip("no Vosk model installed")

    wav = tmp_path / "roundtrip.wav"
    spoken = real_tts.synthesize(phrase, wav)
    assert spoken.ok, f"synthesis failed: {spoken.error} {spoken.detail}"

    with wave.open(str(wav), "rb") as handle:
        pcm = handle.readframes(handle.getnframes())
        rate = handle.getframerate()

    heard = stt.transcribe_pcm(pcm, rate)
    assert heard.ok, f"transcription failed: {heard.error} {heard.detail}"
    assert heard.offline is True
    assert heard.transcript == phrase
