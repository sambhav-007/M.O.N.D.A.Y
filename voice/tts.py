"""
M.O.N.D.A.Y. — text to speech, and which engine actually said it.

One decision point for backend synthesis, with the engines tried in order and
the answer reporting **which one spoke**. That last part is the whole design:
"MONDAY has a voice" is not a useful claim when there are three possible sources
and two of them may be absent.

The order, and the reasoning behind it (ROADMAP §4.1, measured on this machine):

1. **Piper** — offline neural, ~5 packages, embedded espeak-ng. `onnxruntime`
   was probed here and loads, so Smart App Control does not block it. It sounds
   markedly better than anything else available. It is **GPL-3.0**, which is a
   licence decision rather than a `pip install`, so it is used only if the user
   has installed it deliberately.
2. **pyttsx3** — Windows SAPI5 over COM. No ML runtime, no model file, always
   there once installed. Measured on this machine it offers only *David* and
   *Zira*, the legacy voices — so it is the dependable floor, not the good
   answer. The ROADMAP originally had this first and the probe corrected it.
3. **Nothing** — reported as `TTS_UNAVAILABLE`, which is the current state of
   this machine and must stay honest. `MondayVoiceModel.synthesize_speech` used
   to return `success: True` when gTTS had raised *and* pyttsx3 was absent, so
   no audio existed anywhere.

**Not Kokoro**, despite the better licence: 22 transitive packages including
`regex`, which Smart App Control blocked here during the XTTS attempt.

**Not XTTS.** `voice/tts_bridge.py` is the record of that attempt and stays as
one — it needs FFmpeg, which SAC blocks outright, and it is not importable from
this environment. It is a standalone script for a separate venv, not a seam.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

#: Set to a Piper voice `.onnx` to use Piper. Without it Piper is skipped even
#: when installed — a voice model is a separate ~60 MB download and guessing at
#: a path would produce a failure that looks like a bug.
PIPER_VOICE = os.environ.get("MONDAY_PIPER_VOICE", "")

#: `MONDAY_TTS=off` silences backend synthesis entirely. Exists because the
#: desktop UI speaks in the browser, and two voices saying the same sentence is
#: worse than one — see `core/speech.py` and the double-speak note in
#: `handoff.md` §3.
_DISABLED = {"off", "0", "false", "no", "none"}


@dataclass(frozen=True)
class Spoken:
    """What happened when synthesis was attempted."""

    ok: bool
    engine: str = ""
    path: str = ""
    error: str = ""
    detail: str = ""


def available_engine() -> str:
    """The engine that would be used, or "" if none. Cheap and side-effect free."""
    if os.environ.get("MONDAY_TTS", "").strip().lower() in _DISABLED:
        return ""
    if PIPER_VOICE and Path(PIPER_VOICE).exists():
        try:
            import piper  # noqa: F401

            return "piper"
        except ImportError:
            pass
    try:
        import pyttsx3  # noqa: F401

        return "pyttsx3"
    except ImportError:
        return ""


def synthesize(text: str, out_path: str | Path) -> Spoken:
    """Writes `text` to `out_path` as audio. Never raises.

    Returns which engine produced the file, so a caller can report the truth
    rather than "spoke". A caller that cannot say which engine spoke should not
    claim that anything did.
    """
    words = (text or "").strip()
    if not words:
        return Spoken(ok=False, error="EMPTY_TEXT")

    engine = available_engine()
    if not engine:
        return Spoken(
            ok=False,
            error="TTS_UNAVAILABLE",
            detail=(
                "No speech engine is installed. `pip install pyttsx3` for the "
                "Windows voices, or set MONDAY_PIPER_VOICE to a Piper .onnx for "
                "the neural one."
            ),
        )

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    if engine == "piper":
        try:
            import wave

            from piper import PiperVoice

            voice = PiperVoice.load(PIPER_VOICE)
            with wave.open(str(out), "wb") as wav:
                voice.synthesize_wav(words, wav)
            if out.exists() and out.stat().st_size > 0:
                return Spoken(ok=True, engine="piper", path=str(out))
            return Spoken(ok=False, error="TTS_WROTE_NOTHING", detail="piper produced an empty file")
        except Exception as exc:  # noqa: BLE001
            # Fall through to SAPI5 rather than failing: a missing voice file or
            # a broken model should degrade, not silence the assistant.
            return _sapi5(words, out, note=f"piper failed ({type(exc).__name__})")

    return _sapi5(words, out)


def _sapi5(text: str, out: Path, note: str = "") -> Spoken:
    """Windows' own voices. The floor, and always the same two here."""
    try:
        import pyttsx3

        engine = pyttsx3.init()
        engine.save_to_file(text, str(out))
        engine.runAndWait()
        # `save_to_file` reports nothing, so the file is the evidence. Without
        # this check a failed write would be reported as speech — which is the
        # exact bug `MondayVoiceModel.synthesize_speech` had.
        if out.exists() and out.stat().st_size > 0:
            return Spoken(ok=True, engine="pyttsx3", path=str(out), detail=note)
        return Spoken(ok=False, error="TTS_WROTE_NOTHING",
                      detail=(note + "; " if note else "") + "pyttsx3 wrote no audio")
    except Exception as exc:  # noqa: BLE001
        return Spoken(ok=False, error="TTS_FAILED",
                      detail=(note + "; " if note else "") + f"{type(exc).__name__}: {exc}")


def play(path: str | Path) -> bool:
    """Plays a synthesised file. True only if playback actually started."""
    target = Path(path)
    if not target.exists():
        return False
    try:
        import pygame

        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(str(target))
        pygame.mixer.music.play()
        return True
    except Exception:  # noqa: BLE001
        return False
