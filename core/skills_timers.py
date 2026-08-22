"""
M.O.N.D.A.Y. — tranche 6: timers, alarms and media keys (ROADMAP Phase 11).

Both categories were **dropped from the training corpus for not existing**.
`datagen/massive.py` refuses an intent MONDAY cannot serve, with the reason
attached, and two of its entries read:

    "alarm_set": "no alarm or timer exists",
    "play_music": "no playback control",

That is the right rule and the wrong side of it to be on: several hundred real
utterances were discarded because the app had nowhere to send them. This tranche
builds the destinations, and `datagen/massive.py` maps those intents in the same
commit — a capability and its corpus entry move together, or the classifier is
trained on a promise.

What is honest here
-------------------
**A timer is a thread in this process.** It fires while MONDAY is running and
not otherwise, and the confirmation says so rather than leaving a user to find
out when the reminder never comes. `core/timers.py` carries the rest of that
reasoning.

**Media keys are keystrokes, not a music player.** `play`, `pause` and `next`
send the same virtual keys a keyboard's media buttons send, so they control
whatever app currently claims them — Spotify, YouTube in a browser, VLC. MONDAY
cannot tell which app that is, cannot tell whether anything was listening, and
does not claim to: the evidence is `KeypressSent`, which says a key was sent and
nothing about what received it. "Play some jazz" is therefore *not* served here
and still refuses, because choosing music is a thing this cannot do.
"""

from __future__ import annotations

import sys
from datetime import datetime
from typing import Any, Dict

from core.contracts import AgentResult, KeypressSent, SystemQuery, TaskQueued
from core.skills import Skill, SkillRegistry
from core.timers import (
    TimerService,
    format_delta,
    parse_clock_time,
    parse_duration,
)

#: Windows virtual-key codes for the media keys, from the Microsoft docs. Sent
#: with `keybd_event` through ctypes rather than `pyautogui` — pyautogui is
#: installed here, but it pulls a screenshot stack and a mouse-position poll to
#: press one key, and this needs neither.
_MEDIA_KEYS = {
    "play_pause": 0xB3,
    "next": 0xB0,
    "previous": 0xB1,
    "stop": 0xB2,
}

_KEYEVENTF_KEYUP = 0x0002


def send_media_key(action: str) -> bool:
    """Presses one media key. False when the platform has no such thing."""
    code = _MEDIA_KEYS.get(action)
    if code is None or sys.platform != "win32":
        return False
    try:
        import ctypes

        user32 = ctypes.windll.user32
        user32.keybd_event(code, 0, 0, 0)
        user32.keybd_event(code, 0, _KEYEVENTF_KEYUP, 0)
        return True
    except Exception:  # noqa: BLE001 — an unavailable key is not a crash
        return False


def register_timer_skills(registry: SkillRegistry, planner: Any) -> None:
    """Registers timers, alarms and media control against a planner."""

    service: TimerService = planner.timer_service

    # ── Setting one ──────────────────────────────────────────────────────────
    def _confirm(timer, kind: str) -> Dict[str, Any]:
        when = timer.due
        left = format_delta(timer.remaining())
        return AgentResult.ok(
            f"⏰ {kind} set: {timer.label} — {left} from now, at {when:%H:%M}.\n"
            f"  It rings only while I'm running; I'll say so if one passes while "
            f"I'm closed.",
            # `TaskQueued` is the honest strength here: the tick thread exists and
            # holds this timer. Whether it rings depends on MONDAY still running
            # then, which the message says out loud.
            evidence=TaskQueued(
                worker="MondayTimers",
                detail=f"{kind.lower()} '{timer.label}' due {when:%Y-%m-%d %H:%M}",
            ),
            data={
                "timer_id": timer.id,
                "label": timer.label,
                "fires_at": timer.fires_at,
                "speech": f"{kind} set for {left} from now.",
            },
        ).as_dict()

    def set_timer(duration: str = "", label: str = "", _command: str = "", **_: Any) -> Dict[str, Any]:
        span = parse_duration(duration or _command)
        if span is None:
            return AgentResult.failed(
                "How long? Try 'set a timer for 10 minutes'.",
                error="TIMER_NO_DURATION",
            ).as_dict()
        if span.total_seconds() > 86400 * 7:
            return AgentResult.failed(
                "That is more than a week away — I only hold timers while I'm "
                "running, so use a calendar event instead.",
                error="TIMER_TOO_LONG",
            ).as_dict()
        timer = service.add(label.strip() or "Timer", datetime.now() + span, kind="timer")
        return _confirm(timer, "Timer")

    registry.register(Skill(
        name="set_timer",
        read_only=False,
        description="Set a countdown timer for a duration, which rings while MONDAY runs",
        patterns=[
            "set [(a|an)] timer for {duration}",
            "set [(a|an)] {duration} timer",
            "timer for {duration}",
            "start [(a|an)] timer for {duration}",
            "remind me in {duration}",
            "wake me in {duration}",
            "let me know in {duration}",
            "ping me in {duration}",
            "countdown {duration}",
        ],
        handler=set_timer,
        tier=1,
        offline=True,
    ))

    def set_alarm(when: str = "", label: str = "", _command: str = "", **_: Any) -> Dict[str, Any]:
        moment = parse_clock_time(when or _command)
        if moment is None:
            return AgentResult.failed(
                "What time? Try 'set an alarm for 7am'.",
                error="ALARM_NO_TIME",
            ).as_dict()
        timer = service.add(label.strip() or "Alarm", moment, kind="alarm")
        return _confirm(timer, "Alarm")

    registry.register(Skill(
        name="set_alarm",
        read_only=False,
        description="Set an alarm for a clock time, which rings while MONDAY runs",
        patterns=[
            "set [(an|a)] alarm for {when}",
            "set [(an|a)] alarm at {when}",
            "alarm for {when}",
            "alarm at {when}",
            "wake me [(up)] at {when}",
            "wake me [(up)] {when}",
            "remind me at {when}",
        ],
        handler=set_alarm,
        tier=1,
        offline=True,
    ))

    # ── Reading them ─────────────────────────────────────────────────────────
    def list_timers(**_: Any) -> Dict[str, Any]:
        pending = service.pending()
        if not pending:
            return AgentResult.ok(
                "No timers or alarms set.",
                evidence=SystemQuery(source="timers.json", detail="0 pending"),
                data={"timers": [], "speech": "Nothing set."},
            ).as_dict()
        lines = [f"  • {t.describe()}" for t in pending]
        return AgentResult.ok(
            f"⏰ {len(pending)} pending:\n" + "\n".join(lines),
            evidence=SystemQuery(source="timers.json", detail=f"{len(pending)} pending"),
            data={
                "timers": [t.id for t in pending],
                "speech": f"{len(pending)} pending. " + ". ".join(t.label for t in pending[:3]),
            },
        ).as_dict()

    registry.register(Skill(
        name="list_timers",
        read_only=True,
        description="What timers and alarms are set — not calendar events",
        # Written from the corpus rather than guessed at: `alarm_query` routed
        # 17% before these, and almost every miss was being taken by
        # `answer_question`'s "(what is|what are) {topic}" — so "what alarms do
        # i have set" became a Wikipedia lookup of "alarms do i have set".
        patterns=[
            "[(what|which)] (timers|alarms) [(do i have|are set|are there)]",
            "[(what|which)] (timers|alarms) (do|did) i (have|set) [set]",
            "[(what|which)] (timers|alarms) i (have|set) [set]",
            "[(what|which)] (timers|alarms) [(do i have|are set)] (set|active|pending|on)",
            "list [(my|the)] [(active|pending|current)] (timers|alarms)",
            "(show|read|tell|give) [me] [(my|the)] [(active|pending|current)] (timers|alarms)",
            "(show|read|tell|give) me [(my|the)] (timers|alarms) [(i have|i set|that are set)]",
            "(timers|alarms)",
            "[(do)] i have any (timers|alarms)",
            "(are|is) there any (timers|alarms)",
            "[(do)] i have (a|an) (timer|alarm) set",
            "(did|have) i set (a|an|any) (timer|alarm) [rest]",
            "[(what|which)] time (is|are) [(my|the)] (timer|alarm|timers|alarms) set for",
            "[(what|which)] time (will|does) [(my|the)] (timer|alarm) (go off|ring|sound)",
            "when (is|does) [(my|the)] [next] (timer|alarm) [(go off|ring|due)]",
            "how long [(is)] left on [(the|my)] timer",
            "how much time [(is)] left on [(the|my)] timer",
            "check [(my|the)] (timers|alarms)",
            "confirm [(the|my)] (alarm|timer) [time]",
        ],
        handler=list_timers,
        tier=1,
        offline=True,
    ))

    # ── Cancelling ───────────────────────────────────────────────────────────
    def cancel_timer(which: str = "", **_: Any) -> Dict[str, Any]:
        removed = service.cancel(which)
        if not removed:
            return AgentResult.failed(
                f"No timer called '{which}'." if which else "There are no timers to cancel.",
                error="TIMER_NOT_FOUND",
            ).as_dict()
        names = ", ".join(t.label for t in removed)
        return AgentResult.ok(
            f"✓ Cancelled {len(removed)}: {names}.",
            evidence=SystemQuery(source="timers.json", detail=f"cancelled {len(removed)}"),
            data={"cancelled": [t.id for t in removed], "speech": f"Cancelled {len(removed)}."},
        ).as_dict()

    registry.register(Skill(
        name="cancel_timer",
        read_only=False,
        description="Cancel a pending timer or alarm, by name or all of them",
        patterns=[
            "cancel [(the|my)] (timer|alarm)",
            "cancel [(the|my)] (timers|alarms)",
            "cancel [(the|my)] (timer|alarm) {which}",
            "(stop|clear|delete|remove) [(the|my)] (timer|alarm)",
            "(stop|clear|delete|remove) [(the|my)] (timers|alarms)",
            "(stop|clear|delete|remove) [(the|my)] (timer|alarm) {which}",
            "turn off [(the|my)] (alarm|timer)",
        ],
        handler=cancel_timer,
        tier=1,
        offline=True,
    ))

    # ── Media keys ───────────────────────────────────────────────────────────
    def _media(action: str, said: str) -> Dict[str, Any]:
        if send_media_key(action):
            return AgentResult.ok(
                f"✓ Sent {said}.",
                # A key was sent. Whether anything was playing, and which app
                # received it, are things this cannot see and does not claim.
                evidence=KeypressSent(key=said, target_hint="whatever app holds the media keys"),
                data={"action": action, "speech": said},
            ).as_dict()
        return AgentResult.failed(
            f"I couldn't send the {said} key on this platform.",
            error="MEDIA_KEY_UNAVAILABLE",
            data={"action": action, "platform": sys.platform},
        ).as_dict()

    registry.register(Skill(
        name="media_play_pause",
        read_only=False,
        description="Play or pause whatever is playing, via the media key — it cannot choose what plays",
        patterns=[
            "(play|pause|resume)",
            "(play|pause|resume) [(the)] (music|song|track|video|it)",
            "(pause|resume) playback",
            "play pause",
            "hit (play|pause)",
        ],
        handler=lambda **_: _media("play_pause", "play/pause"),
        tier=1,
        offline=True,
    ))

    registry.register(Skill(
        name="media_next",
        read_only=False,
        description="Skip to the next track via the media key",
        patterns=[
            "(next|skip) [(the)] (track|song)",
            "(next|skip) song",
            "skip [(this|it)]",
            "play the next (song|track)",
        ],
        handler=lambda **_: _media("next", "next track"),
        tier=1,
        offline=True,
    ))

    registry.register(Skill(
        name="media_previous",
        read_only=False,
        description="Go back to the previous track via the media key",
        patterns=[
            "(previous|last) (track|song)",
            "go back [(a|one)] (track|song)",
            "play the (previous|last) (song|track)",
            "replay [(the|this)] (song|track)",
        ],
        handler=lambda **_: _media("previous", "previous track"),
        tier=1,
        offline=True,
    ))

    registry.register(Skill(
        name="media_stop",
        read_only=False,
        description="Stop playback via the media key",
        patterns=[
            "stop [(the)] (music|song|track|playback|video)",
            "stop playing",
        ],
        handler=lambda **_: _media("stop", "stop"),
        tier=1,
        offline=True,
    ))
