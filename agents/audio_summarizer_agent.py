"""
M.O.N.D.A.Y. — Live Meeting & System Audio Summarizer Agent
===========================================================
Captures active microphone / speaker audio streams during meetings (Google Meet, Zoom, Teams)
and generates real-time structured bullet-point meeting minutes.
"""

from __future__ import annotations

import os
import sys
import time
import json
import threading
from typing import Any, Dict, List, Optional
from pathlib import Path

from core.contracts import AgentResult, FileRead, SystemQuery
from core.security import log_action


class AudioSummarizerAgent:
    """Captures desktop audio streams and synthesizes meeting minutes."""

    def __init__(self) -> None:
        self.name = "AudioSummarizerAgent"
        self.is_recording = False
        self.recorded_transcripts: List[str] = []

    # ── Meeting capture: declared, never implemented ─────────────────────────
    # `start_meeting_recording` used to set `self.is_recording = True` and reply
    # "🎙️ Live Meeting Audio Recording Started. M.O.N.D.A.Y. is capturing meeting
    # audio streams..." — while capturing nothing. There is no audio capture code
    # anywhere in this repo: `recorded_transcripts` is only ever assigned `[]`,
    # by this file, and no caller appends to it. `stop_…_and_summarize` then
    # reported "No speech transcripts were captured during this recording
    # period", which reads as an empty meeting rather than an absent feature.
    #
    # This is the most consequential fabrication found so far, because a user can
    # act on it: leave it running through a meeting, take no notes, and discover
    # afterwards that nothing existed to summarise. Both entry points now say so
    # up front.
    #
    # Making it real needs a loopback/WASAPI capture path (`sounddevice` is
    # already a dependency and `VoiceAgent` uses it for the microphone) plus
    # transcription. Until then this refuses rather than pretends.

    _NOT_IMPLEMENTED_DETAIL = (
        "No audio capture is implemented — nothing would be recorded. "
        "I can summarise a transcript or notes you already have."
    )

    def start_meeting_recording(self) -> Dict[str, Any]:
        """Refuses: meeting audio capture is not implemented."""
        log_action("start_meeting_recording", "meeting_audio", 1, "unsupported", self.name)
        return AgentResult.unsupported(
            "record meeting audio", detail=self._NOT_IMPLEMENTED_DETAIL
        ).as_dict()

    def stop_meeting_recording_and_summarize(self) -> Dict[str, Any]:
        """Refuses: there was never a recording to stop."""
        self.is_recording = False
        log_action("stop_meeting_recording", "meeting_audio", 1, "unsupported", self.name)
        return AgentResult.unsupported(
            "summarise a recorded meeting", detail=self._NOT_IMPLEMENTED_DETAIL
        ).as_dict()

    def summarize_audio_file(self, file_path_or_notes: str) -> Dict[str, Any]:
        """Summarises a transcript file, or notes passed directly as text.

        The empty case used to substitute two invented bullets — "Captured audio
        transcript processed." and "Main points extracted cleanly." — which
        described work that had not happened, over content that did not exist.
        Nothing to summarise is now reported as nothing to summarise.
        """
        path_obj = Path(file_path_or_notes)
        from_file = path_obj.exists() and path_obj.is_file()
        if from_file:
            text_content = path_obj.read_text(encoding="utf-8", errors="ignore")
        else:
            text_content = file_path_or_notes

        bullets = [
            line.strip()
            for line in text_content.splitlines()
            if line.strip() and len(line.strip()) > 10
        ]
        if not bullets:
            return AgentResult.failed(
                "There was nothing summarisable in that — I look for lines of "
                "more than ten characters.",
                error="NO_CONTENT_TO_SUMMARIZE",
            ).as_dict()

        summary_msg = "🎙️ Audio Summary & Meeting Minutes:\n" + "\n".join(
            f"  • {b}" for b in bullets[:5]
        )
        evidence = (
            FileRead(path=str(path_obj), bytes_read=len(text_content))
            if from_file
            else SystemQuery(source="inline text", detail=f"{len(bullets)} lines")
        )
        return AgentResult.ok(
            summary_msg, evidence=evidence, data={"summary": summary_msg}
        ).as_dict()

    def inspect_audio_metadata(self, file_path: str) -> Dict[str, Any]:
        """Inspects WAV or MP3 audio file metadata including file size, duration, and sampling rate."""
        path = Path(file_path).resolve()
        if not path.exists():
            return AgentResult.failed(
                f"Audio file '{file_path}' not found.", error="FILE_NOT_FOUND"
            ).as_dict()

        file_size = path.stat().st_size

        # Only a WAV header is actually read. For anything else the numbers below
        # are arithmetic on the file size and a fixed 16 kHz assumption, so they
        # are labelled as an estimate rather than reported as metadata — an MP3's
        # real sample rate is not 16000 just because that is what the variable was
        # initialised to.
        import wave

        measured = False
        channels, sample_rate = 1, 16000
        duration = max(1.0, round(file_size / 32000.0, 2))
        if path.suffix.lower() == ".wav":
            try:
                with wave.open(str(path), "rb") as wf:
                    channels = wf.getnchannels()
                    sample_rate = wf.getframerate()
                    duration = round(wf.getnframes() / float(sample_rate), 2)
                    measured = True
            except Exception:
                pass

        log_action("inspect_audio_metadata", path.name, 1, "success", self.name)
        if measured:
            message = (
                f"✓ Audio Metadata for '{path.name}': {duration}s duration | "
                f"{sample_rate}Hz | {channels} ch."
            )
        else:
            message = (
                f"✓ '{path.name}' is {file_size:,} bytes. I can only read headers "
                f"from WAV files, so for this format I can estimate roughly "
                f"{duration}s of audio and nothing more — the sample rate and "
                f"channel count are unknown."
            )

        return AgentResult.ok(
            message,
            evidence=FileRead(path=str(path), bytes_read=file_size),
            data={
                "filename": path.name,
                "file_size_bytes": file_size,
                "header_parsed": measured,
                "estimated_duration_sec": duration,
                **({"sample_rate_hz": sample_rate, "channels": channels} if measured else {}),
            },
        ).as_dict()
