"""CODEC Skill: Speak text aloud via Kokoro TTS or native system voice (Cross-Platform)"""
SKILL_NAME = "tts_say"
SKILL_DESCRIPTION = "Speak a message out loud via Kokoro TTS or native system voice"
SKILL_TRIGGERS = [
    "speak", "say out loud", "say aloud", "read aloud",
    "tts", "voice say", "announce", "speak this",
    "tell me out loud", "say it",
]
SKILL_MCP_EXPOSE = True

import sys
import os
import re
import json
import tempfile
import subprocess
import requests

_CFG_PATH = os.path.expanduser("~/.codec/config.json")
try:
    _cfg = json.load(open(_CFG_PATH))
except Exception:
    _cfg = {}

KOKORO_URL   = _cfg.get("tts_url", "http://localhost:8085/v1/audio/speech")
KOKORO_MODEL = _cfg.get("tts_model", _cfg.get("kokoro_model", "mlx-community/Kokoro-82M-bf16"))
TTS_VOICE    = _cfg.get("tts_voice", "af_bella")

_WRITE_VERBS = (
    "speak", "say out loud", "say aloud", "read aloud",
    "tts", "voice say", "announce", "speak this",
    "tell me out loud", "say it", "say",
)

def _extract_text(task: str) -> str:
    t = task.strip()
    low = t.lower()
    for v in sorted(_WRITE_VERBS, key=len, reverse=True):
        m = re.match(r'^\s*' + re.escape(v) + r'\b', low)
        if m:
            t = t[m.end():].strip()
            break
    t = re.sub(r'^\s*[:,\-]+\s*', '', t).strip()
    return t.strip('"\'').strip()

def play_audio_cross_platform(wav_path):
    try:
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound(wav_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            for player in ["paplay", "aplay", "ffplay"]:
                try:
                    subprocess.Popen([player, wav_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except FileNotFoundError:
                    continue
    except Exception:
        pass

def speak_fallback_cross_platform(text):
    try:
        if sys.platform == "win32":
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            except Exception:
                # SAPI COM fallback
                cmd = f"Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{text}')"
                subprocess.Popen(["powershell", "-Command", cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return f"🔊 (Windows TTS) {text}"
        elif sys.platform == "darwin":
            subprocess.Popen(["say", text])
            return f"🔊 (macOS say) {text}"
        else:
            try:
                subprocess.Popen(["espeak", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                pass
            return f"🔊 (Linux espeak) {text}"
    except Exception as e:
        return f"TTS Fallback Error: {e}"

def run(task, app="", ctx=""):
    text = _extract_text(task)
    if not text or len(text) < 1:
        return "What should I say? (e.g. 'say All done captain')"

    clean = text[:500]
    clean = re.sub(r'\*+', '', clean)
    clean = re.sub(r'#+\s*', '', clean)
    clean = clean.replace('"', '').strip()

    try:
        resp = requests.post(
            KOKORO_URL,
            json={
                "model": KOKORO_MODEL,
                "input": clean,
                "voice": TTS_VOICE,
                "response_format": "wav",
            },
            stream=True,
            timeout=5,
        )
        if resp.status_code != 200:
            return speak_fallback_cross_platform(clean)

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        for chunk in resp.iter_content(chunk_size=4096):
            tmp.write(chunk)
        tmp.close()
        play_audio_cross_platform(tmp.name)
        return f"🔊 Speaking: {clean}"
    except Exception:
        return speak_fallback_cross_platform(clean)
