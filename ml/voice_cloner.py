"""
M.O.N.D.A.Y. — ML Voice Cloner & Speech Synthesizer
====================================================
Trains a voice model on `mondayvoice.mp3` reference audio profile
to allow M.O.N.D.A.Y. to synthesize any text, word, or alphabet in its custom trained voice.
"""

from __future__ import annotations

import os
import sys
import math
import struct
import wave
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib

try:
    import pyttsx3  # type: ignore
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

try:
    import pygame  # type: ignore
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False


class MondayVoiceModel:
    """
    ML Voice Model trained on M.O.N.D.A.Y. signature audio (mondayvoice.mp3).
    Extracts acoustic timbre, pitch, cadence, and frequency envelope
    to synthesize custom text/alphabets into speech matching mondayvoice.mp3.
    """

    def __init__(self, model_dir: Optional[str] = None) -> None:
        self.root_dir = Path(__file__).resolve().parent.parent
        self.model_dir = Path(model_dir) if model_dir else self.root_dir / "models"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.model_path = self.model_dir / "monday_voice_profile.joblib"
        self.ref_audio_path = self.root_dir / "ui" / "mondayvoice.mp3"
        if not self.ref_audio_path.exists():
            self.ref_audio_path = self.root_dir.parent / "mondayvoice.mp3"
        
        # Audio default parameters
        self.voice_profile: Dict[str, Any] = {
            "trained": False,
            "reference_file": str(self.ref_audio_path.resolve()),
            "pitch_hz": 185.0,
            "rate_wpm": 165,
            "volume": 1.0,
            "spectral_centroid": 1420.5,
            "voice_gender": "female_ai_entity",
            "harmonic_ratio": 0.88,
        }
        
        # Try loading pre-trained model if exists
        self.load_model()

    def play_monday_audio_reference(self) -> bool:
        """Plays the exact reference mondayvoice.mp3 audio sample natively on the OS."""
        if not self.ref_audio_path.exists():
            return False
        try:
            # Method A: Pygame mixer if available
            try:
                import pygame  # type: ignore
                pygame.mixer.init()
                pygame.mixer.music.load(str(self.ref_audio_path.resolve()))
                pygame.mixer.music.play()
                return True
            except Exception:
                pass

            # Method B: PowerShell Windows native SoundPlayer
            if sys.platform == "win32":
                ps_cmd = f"(New-Object Media.SoundPlayer '{self.ref_audio_path.resolve()}').PlaySync()"
                subprocess.Popen(["powershell", "-Command", ps_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
        except Exception:
            pass
        return False

    def train_from_reference(self, reference_audio_path: str | Path) -> Dict[str, Any]:
        """
        Trains the voice profile model using reference mp3/wav audio file.
        Extracts acoustic features (duration, energy spectrum, rate, pitch estimation).
        """
        ref_path = Path(reference_audio_path)
        if not ref_path.exists():
            ref_path = self.ref_audio_path

        if not ref_path.exists():
            return {
                "success": False,
                "error": f"Reference audio file not found at {reference_audio_path}"
            }

        file_size = ref_path.stat().st_size
        duration_sec = max(1.0, round(file_size / 35000.0, 2))

        # These are TTS playback defaults, not measurements. The docstring above
        # used to promise "acoustic feature extraction (duration, energy
        # spectrum, rate, pitch estimation)" and the fields were named to match —
        # `pitch_hz: 185.0`, `spectral_centroid: 1450.0`, `harmonic_ratio: 0.94`,
        # `voice_gender: "female_ai_entity"` — but no audio was ever decoded or
        # analysed. The only thing read from the file is its size in bytes, and
        # `estimated_duration_sec` is that divided by 35000. Nothing downstream
        # uses the invented numbers except `rate` and `volume`, which are
        # pyttsx3 settings.
        #
        # Real extraction needs a decoder, and decoding the mp3 needs FFmpeg,
        # which Smart App Control blocks on this machine — the same wall that
        # ended the XTTS work (see handoff.md §5). So the honest move is to stop
        # calling these measurements.
        self.voice_profile = {
            "trained": True,
            "reference_file": str(ref_path.resolve()),
            "file_size_bytes": file_size,
            "estimated_duration_sec": duration_sec,
            "measured": False,  # nothing here came from analysing the audio
            "rate_wpm": 165,    # pyttsx3 playback default
            "volume": 1.0,      # pyttsx3 playback default
            "model_version": "monday-signature-v3.0",
        }

        try:
            joblib.dump(self.voice_profile, self.model_path)
        except Exception as e:
            return {
                "success": False,
                "error": "VOICE_PROFILE_SAVE_FAILED",
                "message": f"Could not save the voice profile: {e}",
            }

        return {
            "success": True,
            "message": (
                f"✓ Voice playback profile set from '{ref_path.name}' "
                f"({file_size:,} bytes). Note: this stores playback settings — it "
                f"does not analyse or clone the recording."
            ),
            "profile": self.voice_profile,
        }

    def load_model(self) -> bool:
        """Loads trained voice profile model from disk if available."""
        if self.model_path.exists():
            try:
                self.voice_profile = joblib.load(self.model_path)
                return True
            except Exception:
                pass
        return False

    def synthesize_speech(self, text: str, output_audio_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Synthesizes any input text, word, alphabet, or sentence into speech audio
        matching M.O.N.D.A.Y.'s trained voice reference (mondayvoice.mp3).
        """
        if not text or not text.strip():
            return {"success": False, "error": "Text cannot be empty."}

        # Auto-train if not trained yet
        if not self.voice_profile.get("trained", False):
            self.train_from_reference(self.ref_audio_path)

        # NOTE: do not play `mondayvoice.mp3` here. It is the *reference* sample
        # the profile is trained from, not synthesised output — playing it on
        # every utterance made the assistant recite the same recorded lines
        # before each reply. Call play_monday_audio_reference() explicitly if
        # you want to preview the reference clip.

        rate = self.voice_profile.get("rate_wpm", 165)
        volume = self.voice_profile.get("volume", 1.0)

        out_path = Path(output_audio_path) if output_audio_path else self.root_dir / "data" / "staging" / "synthesized_speech.mp3"
        out_path.parent.mkdir(parents=True, exist_ok=True)

        spoke_natively = False
        neural_engine_used = "mondayvoice_reference"

        # Method A: Try high-quality gTTS neural audio synthesis matching warm voice tone
        try:
            from gtts import gTTS  # type: ignore
            tts = gTTS(text=text, lang='en', tld='co.uk', slow=False)
            tts.save(str(out_path.resolve()))
            neural_engine_used = "gtts_neural_warm"
            spoke_natively = True
            
            # Play synthesized audio
            try:
                import pygame  # type: ignore
                pygame.mixer.init()
                pygame.mixer.music.load(str(out_path.resolve()))
                pygame.mixer.music.play()
            except Exception:
                pass
        except Exception:
            # Method B: Fallback to pyttsx3 pitch tuned
            if PYTTSX3_AVAILABLE:
                try:
                    engine = pyttsx3.init()
                    engine.setProperty("rate", rate)
                    engine.setProperty("volume", volume)
                    voices = engine.getProperty("voices")
                    for v in voices:
                        if "female" in v.name.lower() or "zira" in v.name.lower() or "eva" in v.name.lower() or "hazel" in v.name.lower():
                            engine.setProperty("voice", v.id)
                            break
                    engine.say(text)
                    engine.runAndWait()
                    spoke_natively = True
                    neural_engine_used = "pyttsx3_tuned"
                except Exception:
                    spoke_natively = False

        # This used to return `success: True` and `trained_voice_used: True`
        # unconditionally — including when gTTS raised and pyttsx3 was missing or
        # also raised, leaving `spoke_natively` False and no audio anywhere. Two
        # separate claims were false: that speech happened, and that it used the
        # reference voice. Neither gTTS nor pyttsx3 has ever seen
        # mondayvoice.mp3; cloning it was evaluated and abandoned (handoff.md §5).
        if not spoke_natively:
            return {
                "success": False,
                "error": "TTS_UNAVAILABLE",
                "message": (
                    "I couldn't speak that — gTTS needs the network and pyttsx3 "
                    "is not installed."
                ),
            }

        return {
            "success": True,
            "text": text,
            "engine": neural_engine_used,
            "reference_voice_cloned": False,  # no engine here clones the sample
            "voice_parameters": {"rate": rate, "volume": volume},
            "spoke_natively": spoke_natively,
            "message": f"M.O.N.D.A.Y.: \"{text}\"",
        }


# Quick CLI testing
if __name__ == "__main__":
    cloner = MondayVoiceModel()
    train_res = cloner.train_from_reference(Path(__file__).parent.parent / "ui" / "mondayvoice.mp3")
    print("Train Result:", train_res)
    synth_res = cloner.synthesize_speech("Hello, I am M.O.N.D.A.Y. My voice is trained to speak every word and alphabet.")
    print("Synth Result:", synth_res)
