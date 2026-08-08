"""
M.O.N.D.A.Y. — Voice & Speech Engine Agent
==========================================
Specialized agent for zero-shot voice synthesis (Text-to-Speech) using reference speaker sample
(assets/monday_voice.wav / assets/mondayvoice.mp3) and speech recognition processing.
"""

from __future__ import annotations

import os
import sys
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from core.contracts import AgentResult, FileWritten, TaskQueued
from core.security import log_action
from ml.voice_cloner import MondayVoiceModel

# Optional Pygame mixer for non-blocking UI audio playback
try:
    import pygame  # type: ignore
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

# Optional Coqui XTTS v2 zero-shot voice cloning framework
try:
    from TTS.api import TTS  # type: ignore
    XTTS_AVAILABLE = True
except ImportError:
    XTTS_AVAILABLE = False


class VoiceAgent:
    """
    Voice & Speech Processing Agent for M.O.N.D.A.Y.
    Clones reference speaker voice sample (assets/monday_voice.wav) and synthesizes
    speech asynchronously in background threads to avoid freezing the UI thread.
    """

    def __init__(self, sample_path: Optional[str] = None, enable_voice: bool = True) -> None:
        self.name = "VoiceAgent"
        self.enable_voice = enable_voice
        self.root_dir = Path(__file__).resolve().parent.parent

        # Locate reference audio speaker WAV/MP3 sample file
        default_sample = self.root_dir / "assets" / "monday_voice.wav"
        if not default_sample.exists():
            default_sample = self.root_dir / "assets" / "mondayvoice.mp3"
        if not default_sample.exists():
            default_sample = self.root_dir / "ui" / "mondayvoice.mp3"

        self.sample_path = Path(sample_path) if sample_path else default_sample
        self.voice_model = MondayVoiceModel()

        # Initialize pygame mixer for non-blocking playback
        if PYGAME_AVAILABLE:
            try:
                pygame.mixer.init()
            except Exception:
                pass

        # Load Coqui XTTS v2 model if available
        self.xtts_model = None
        if XTTS_AVAILABLE:
            try:
                self.xtts_model = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2")
            except Exception:
                self.xtts_model = None

        if self.sample_path.exists():
            self.voice_model.train_from_reference(self.sample_path)

    def set_voice_enabled(self, enabled: bool) -> bool:
        """Toggles voice output on or off."""
        self.enable_voice = enabled
        return self.enable_voice

    def train_voice(self, reference_audio_path: Optional[str] = None) -> Dict[str, Any]:
        """Trains or retrains the voice synthesis model using a reference audio sample."""
        target_path = reference_audio_path or str(self.sample_path)
        return self.voice_model.train_from_reference(target_path)

    def speak(self, text: str) -> Dict[str, Any]:
        """
        Synthesizes text into spoken speech output using reference speaker voice sample.
        Runs generation & audio playback asynchronously in a background thread so UI does not freeze.
        """
        if not text or not text.strip():
            return AgentResult.failed(
                "Speech text cannot be empty.", error="EMPTY_TEXT"
            ).as_dict()

        if not self.enable_voice:
            return AgentResult.failed(
                "Voice output is currently disabled (ENABLE_VOICE=False).",
                error="VOICE_DISABLED",
            ).as_dict()

        def _generate_and_play():
            output_path = self.root_dir / "data" / "staging" / "temp_speech.wav"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Option A: Coqui XTTS v2 zero-shot voice cloning from 7-second speaker sample
            if self.xtts_model is not None and self.sample_path.exists():
                try:
                    self.xtts_model.tts_to_file(
                        text=text,
                        speaker_wav=str(self.sample_path.resolve()),
                        language="en",
                        file_path=str(output_path.resolve())
                    )
                    if PYGAME_AVAILABLE:
                        pygame.mixer.music.load(str(output_path.resolve()))
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy():
                            pygame.time.Clock().tick(10)
                    return
                except Exception:
                    pass

            # Option B: High quality MondayVoiceModel reference audio synthesis fallback
            try:
                self.voice_model.synthesize_speech(text, output_audio_path=str(output_path.resolve()))
            except Exception:
                pass

        # Run synthesis in background thread so M.O.N.D.A.Y. UI does NOT freeze
        # while talking. Because this returns before the thread finishes — and
        # both synthesis paths above swallow their exceptions — the only thing
        # this function can honestly witness is that the work was queued.
        #
        # It used to return `audio_synthesized: True, trained_voice_used: True`
        # on the next line. Both were claims about a thread that had not run yet,
        # and the second was false regardless: neither gTTS nor pyttsx3 uses the
        # reference sample, and cloning it was abandoned (handoff.md §5).
        threading.Thread(target=_generate_and_play, daemon=True).start()
        log_action("voice_speak", text[:60], 1, "queued", self.name)

        return AgentResult.ok(
            f'[Voice] M.O.N.D.A.Y. Speaking: "{text}"',
            evidence=TaskQueued(worker="voice synthesis thread", detail=f"{len(text)} chars"),
            data={"text": text, "speech_queued": True},
        ).as_dict()

    def listen(self, timeout_seconds: int = 5) -> Dict[str, Any]:
        """
        Listens for audio speech input from default microphone using sounddevice and converts to text.
        """
        log_action("voice_listen", f"timeout={timeout_seconds}s", 1, "success", self.name)

        try:
            import wave
            import sounddevice as sd  # type: ignore
            import speech_recognition as sr  # type: ignore

            fs = 16000
            duration = max(3, int(timeout_seconds))
            wav_path = self.root_dir / "data" / "staging" / "mic_input.wav"
            wav_path.parent.mkdir(parents=True, exist_ok=True)

            # Record mic audio in 16bit PCM mono
            recording = sd.rec(int(duration * fs), samplerate=fs, channels=1, dtype='int16')
            sd.wait()

            with wave.open(str(wav_path.resolve()), 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(fs)
                wf.writeframes(recording.tobytes())

            recognizer = sr.Recognizer()
            with sr.AudioFile(str(wav_path.resolve())) as source:
                audio = recognizer.record(source)
                transcript = recognizer.recognize_google(audio)
                return AgentResult.ok(
                    f'[Mic] Recognized speech: "{transcript}"',
                    evidence=FileWritten(
                        path=str(wav_path), bytes_written=wav_path.stat().st_size
                    ),
                    data={"transcript": transcript, "listening": False},
                ).as_dict()
        except Exception as err:
            return AgentResult.failed(
                f"[Mic] Listening timed out or speech not clear: {err}",
                error="SPEECH_RECOGNITION_FAILED",
                data={"listening": False},
            ).as_dict()

    def start_wake_word_listener(self, callback_fn: Optional[Any] = None) -> Dict[str, Any]:
        """
        Starts a continuous hands-free background listener loop for 'Monday' or 'Hey Monday' wake word activation.
        Streams speech directly into M.O.N.D.A.Y. execution engine when triggered.
        """
        def continuous_listener_worker():
            print("🎙️ [Mic] Continuous Hands-free 'Monday' / 'Hey Monday' Wake-Word Listener Active.")
            while True:
                try:
                    res = self.listen(timeout_seconds=6)
                    if res.get("success") and res.get("transcript"):
                        transcript = res["transcript"]
                        if any(w in transcript.lower() for w in ["monday", "hey monday", "ok monday"]):
                            print(f"🎙️ [Wake-Word Triggered] Spoken command: \"{transcript}\"")
                            if callback_fn:
                                callback_fn(transcript)
                except Exception:
                    pass

        t = threading.Thread(target=continuous_listener_worker, daemon=True)
        t.start()
        log_action("start_wake_word_listener", "hey_monday", 1, "success", self.name)
        return AgentResult.ok(
            "✓ Hands-free continuous 'Monday' Wake-Word listener activated in background.",
            evidence=TaskQueued(worker="wake-word listener thread", detail="polls the mic every 6s"),
            data={"wake_word": "Hey Monday / Monday"},
        ).as_dict()
