"""
Isolated XTTS v2 synthesis bridge.
Run with the dedicated TTS venv's python (C:\\Users\\sambh\\monday-tts) so the
heavy PyTorch/Coqui deps stay out of the main app environment.

    python voice/tts_bridge.py --text "hello" --speaker ui/mondayvoice.mp3 --out out.wav

Clones the reference speaker voice and writes spoken audio to --out.
"""

from __future__ import annotations

import argparse
import os
import sys

# Accept the Coqui model license non-interactively (avoids a hanging prompt).
os.environ.setdefault("COQUI_TOS_AGREED", "1")


def _ensure_wav_reference(speaker_path: str) -> str:
    """XTTS needs a loadable audio file. The bundled 'mondayvoice.mp3' is really
    an MP3; if torchaudio can't read it directly, transcode to a temp WAV."""
    try:
        import torchaudio  # noqa: F401
        import torchaudio as ta
        ta.load(speaker_path)  # will raise if unreadable
        return speaker_path
    except Exception:
        pass
    # Fallback: transcode via soundfile+librosa if available
    try:
        import librosa
        import soundfile as sf
        wav, sr = librosa.load(speaker_path, sr=22050, mono=True)
        out = os.path.join(os.path.dirname(speaker_path), "_monday_ref_22k.wav")
        sf.write(out, wav, sr)
        return out
    except Exception as e:
        print(f"WARN: could not transcode reference audio: {e}", file=sys.stderr)
        return speaker_path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--speaker", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    from TTS.api import TTS

    speaker = _ensure_wav_reference(args.speaker)
    tts = TTS(model_name="tts_models/multilingual/multi-dataset/xtts_v2", progress_bar=False)
    tts.tts_to_file(text=args.text, speaker_wav=speaker, language="en", file_path=args.out)
    print(f"OK: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
