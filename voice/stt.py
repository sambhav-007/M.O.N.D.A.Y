"""
M.O.N.D.A.Y. — speech to text, offline where possible.

`VoiceAgent.listen` recorded microphone audio and sent it to
`recognizer.recognize_google` — a round trip to a Google endpoint. That made
"voice works offline" an overstatement in the one place it mattered most: with
no network, MONDAY could speak (in the browser) but could not hear.

Vosk fixes that. It is ~50 MB, CPU-only, two packages, and takes **raw PCM** —
so it needs no FFmpeg, which is what killed XTTS on this machine (`handoff.md`
§5). `faster-whisper` is more accurate and was rejected on memory: CTranslate2
plus a model, against ~4 GB free with a 2 GB language model already resident
(ROADMAP §4.2).

The fallback order is deliberately the opposite of the TTS module's. There,
quality is worth a dependency. Here, **offline is the feature** — a transcriber
that needs the network is the thing being replaced, so it goes last and says so.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Where the Vosk model lives. Vosk ships no model with the package; it is a
#: separate ~50 MB download, so an unset path means "not configured" rather than
#: a guess that fails somewhere less obvious.
#:
#:     https://alphacephei.com/vosk/models  →  vosk-model-small-en-us-0.15
VOSK_MODEL = os.environ.get(
    "MONDAY_VOSK_MODEL", str(Path("models") / "vosk-model-small-en-us")
)

#: 16 kHz mono is what the small model expects and what `sounddevice` records.
SAMPLE_RATE = 16000


@dataclass(frozen=True)
class Heard:
    """What was transcribed, and by what."""

    ok: bool
    transcript: str = ""
    engine: str = ""
    offline: bool = False
    error: str = ""
    detail: str = ""


def vosk_available() -> bool:
    """Whether offline transcription is actually possible right now."""
    if not Path(VOSK_MODEL).exists():
        return False
    try:
        import vosk  # noqa: F401

        return True
    except ImportError:
        return False


def transcribe_pcm(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> Heard:
    """Transcribes 16-bit mono PCM offline. Never raises.

    Takes bytes rather than a path on purpose: the recording already exists in
    memory as a numpy array, and writing a WAV only to read it back is how a
    decoder — and therefore FFmpeg — creeps into the dependency list.
    """
    if not pcm:
        return Heard(ok=False, error="NO_AUDIO", detail="nothing was recorded")
    if not vosk_available():
        return Heard(
            ok=False,
            error="VOSK_UNAVAILABLE",
            detail=(
                f"No offline model at '{VOSK_MODEL}'. Download "
                f"vosk-model-small-en-us-0.15 and set MONDAY_VOSK_MODEL, or "
                f"MONDAY will fall back to the online recogniser."
            ),
        )

    try:
        import vosk

        vosk.SetLogLevel(-1)  # the C library is chatty on stderr by default
        model = vosk.Model(VOSK_MODEL)
        recognizer = vosk.KaldiRecognizer(model, sample_rate)
        recognizer.AcceptWaveform(pcm)
        result = json.loads(recognizer.FinalResult() or "{}")
    except Exception as exc:  # noqa: BLE001
        return Heard(ok=False, error="VOSK_FAILED", detail=f"{type(exc).__name__}: {exc}")

    text = str(result.get("text", "")).strip()
    if not text:
        # Silence is not a failure of the recogniser, and saying "recognition
        # failed" when the user simply did not speak sends them debugging the
        # wrong thing.
        return Heard(ok=False, engine="vosk", offline=True, error="NO_SPEECH",
                     detail="the recording contained no recognisable speech")
    return Heard(ok=True, transcript=text, engine="vosk", offline=True)
