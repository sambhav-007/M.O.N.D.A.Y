"""CODEC Skill: Music Control (Spotify + Apple Music, Cross-Platform Windows/Linux/macOS)"""
SKILL_NAME = "music"
SKILL_DESCRIPTION = "Control Spotify, Apple Music, or system media playback"
SKILL_MCP_EXPOSE = True
SKILL_TRIGGERS = ["play music", "pause music", "next song", "previous song", "skip song",
                   "play spotify", "pause spotify", "resume music", "stop music", "stop spotify",
                   "what song", "what is playing", "now playing", "play some music",
                   "play something", "play on spotify", "on spotify",
                   "stop the music", "pause the music", "play the music",
                   "next track", "skip track", "spotify play", "spotify pause", "spotify next"]

import sys
import os
import subprocess
import pyautogui

def _spotify_running():
    try:
        import psutil
        for proc in psutil.process_iter(['name']):
            if 'spotify' in (proc.info['name'] or '').lower():
                return True
    except Exception:
        pass
    if sys.platform == "darwin":
        r = subprocess.run(["pgrep", "-x", "Spotify"], capture_output=True, timeout=3)
        return r.returncode == 0
    return False

def _run_spotify_macos(cmd):
    return subprocess.run(["osascript", "-e", f'tell application "Spotify" to {cmd}'], capture_output=True, text=True, timeout=5)

def run(task, app="", ctx=""):
    low = task.lower()
    use_spotify = _spotify_running() or "spotify" in low

    if any(k in low for k in ["next", "skip"]):
        if sys.platform == "darwin" and use_spotify:
            _run_spotify_macos("next track")
            return "Skipped to next track."
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", 'tell application "Music" to next track'], timeout=5)
            return "Next track."
        else:
            pyautogui.press("nexttrack")
            return "Next track."

    if "previous" in low:
        if sys.platform == "darwin" and use_spotify:
            _run_spotify_macos("previous track")
            return "Previous track."
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", 'tell application "Music" to previous track'], timeout=5)
            return "Previous track."
        else:
            pyautogui.press("prevtrack")
            return "Previous track."

    if any(k in low for k in ["what song", "what is playing", "now playing"]):
        if sys.platform == "darwin" and use_spotify and _spotify_running():
            r = subprocess.run(["osascript", "-e",
                'tell application "Spotify" to return (name of current track) & " by " & (artist of current track)'],
                capture_output=True, text=True, timeout=5)
            if r.stdout.strip():
                return f"Now playing: {r.stdout.strip()}"
        return "Playing media."

    if any(k in low for k in ["pause", "stop"]):
        if sys.platform == "darwin" and use_spotify:
            _run_spotify_macos("pause")
            return "Spotify paused."
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", 'tell application "Music" to pause'], timeout=5)
            return "Music paused."
        else:
            pyautogui.press("playpause")
            return "Playback paused."

    if any(k in low for k in ["play", "resume"]):
        if sys.platform == "darwin" and use_spotify:
            if not _spotify_running():
                subprocess.run(["open", "-a", "Spotify"], timeout=5)
                import time; time.sleep(2)
            _run_spotify_macos("play")
            return "Spotify playing."
        elif sys.platform == "darwin":
            subprocess.run(["osascript", "-e", 'tell application "Music" to play'], timeout=5)
            return "Music playing."
        else:
            pyautogui.press("playpause")
            return "Playback started."

    return None
