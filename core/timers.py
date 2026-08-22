"""
M.O.N.D.A.Y. — ROADMAP Phase 11. Timers and alarms.

`datagen/massive.py` dropped MASSIVE's `alarm_set`, `alarm_query` and
`alarm_remove` with the reason "no alarm or timer exists" — 3 intents and
several hundred real utterances thrown away because the app had nowhere to send
them. That mapping file's governing rule is that an utterance is kept only if
MONDAY can serve it, so the way to recover those rows is to build the thing.

What is honest about this
-------------------------
A timer here is **a thread in this process**. It fires while MONDAY is running
and not otherwise, and that has to be said out loud when one is set rather than
discovered by a user whose reminder never came. It is not a Windows Scheduled
Task and it does not survive a reboot.

What it does survive is a restart *of the assistant*: timers are written to
`data/timers.json`, so `TimerService.start()` can report the ones that came due
while nothing was running. A missed timer is reported as missed. The alternative
— firing four hours late as though nothing happened, or silently dropping it —
are both worse than saying "this one passed while I was closed".

Why not `sched` or a per-timer thread
-------------------------------------
One thread ticking a sorted list. A thread per timer would be simpler to write
and would make "cancel the timer" a question about thread lifecycle rather than
about a list, which is the kind of thing that leaks threads in a long-running
desktop process. `AutonomyDaemon` next door already demonstrates the one-thread
pattern this follows.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

STORE_PATH = Path("data") / "timers.json"

#: How often the tick thread wakes. One second is well inside what a person
#: notices for a kitchen timer and costs nothing measurable.
TICK_SECONDS = 1.0

#: A timer this far past due when MONDAY starts is reported as missed rather
#: than fired. Firing "your 10-minute pasta timer" the next morning is worse
#: than saying it passed.
MISSED_AFTER = timedelta(minutes=1)

_UNITS = {
    "second": 1, "seconds": 1, "sec": 1, "secs": 1, "s": 1,
    "minute": 60, "minutes": 60, "min": 60, "mins": 60, "m": 60,
    "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600, "h": 3600,
    "day": 86400, "days": 86400,
}

_WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "forty five": 45, "fortyfive": 45, "forty-five": 45, "fifty": 50, "sixty": 60,
    "half": 0.5, "quarter": 0.25,
}

#: The `(?:an?\s+)?` between the count and the unit is load-bearing: without it
#: "half an hour" never matched `half` against `hour`, so `half` was skipped and
#: the bare `an hour` matched instead — a 30-minute timer silently became a
#: 60-minute one, which is the quiet kind of wrong this repository hunts.
_DURATION = re.compile(
    r"(?P<count>\d+(?:\.\d+)?|" + "|".join(sorted(_WORD_NUMBERS, key=len, reverse=True)) + r")"
    r"\s*(?:an?\s+)?(?P<unit>" + "|".join(sorted(_UNITS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

_CLOCK = re.compile(
    r"\b(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<meridiem>am|pm|a\.m\.|p\.m\.)?\b",
    re.IGNORECASE,
)


def parse_duration(text: str) -> Optional[timedelta]:
    """"5 minutes", "1 hour 30 mins", "half an hour" → a timedelta, or None.

    Every match in the string is summed, so "1 hour 30 minutes" is one duration
    rather than the first number found — which is the bug the old volume parser
    had when it took `re.search(r'(\\d+)')` from anywhere in the command.
    """
    total = 0.0
    for match in _DURATION.finditer(text or ""):
        raw = match.group("count").lower()
        count = float(raw) if raw.replace(".", "", 1).isdigit() else _WORD_NUMBERS.get(raw, 0)
        total += count * _UNITS[match.group("unit").lower()]
    return timedelta(seconds=total) if total > 0 else None


def parse_clock_time(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """"7am", "7:30 pm", "18:45" → the next datetime matching it, or None.

    Always in the future: "wake me at 7am" said at 9am means tomorrow. A time
    that has passed today is the single most likely thing to be asked for.
    """
    now = now or datetime.now()
    match = _CLOCK.search(text or "")
    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    meridiem = (match.group("meridiem") or "").replace(".", "").lower()

    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif not meridiem and hour <= 12 and match.group("minute") is None:
        # A bare "7" with no minutes and no am/pm. Ambiguous by nature; the
        # reading that is almost always meant is the next one to arrive.
        pass

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None

    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target


@dataclass
class Timer:
    """One pending timer. Plain data, so the store is a readable JSON file."""

    id: str
    label: str
    fires_at: str                       # ISO 8601, local time
    created_at: str
    kind: str = "timer"                 # "timer" (duration) or "alarm" (clock)
    fired: bool = False
    missed: bool = False

    @property
    def due(self) -> datetime:
        return datetime.fromisoformat(self.fires_at)

    def remaining(self, now: Optional[datetime] = None) -> timedelta:
        return self.due - (now or datetime.now())

    def describe(self, now: Optional[datetime] = None) -> str:
        left = self.remaining(now)
        if left.total_seconds() <= 0:
            return f"{self.label} — due now"
        return f"{self.label} — in {format_delta(left)} (at {self.due:%H:%M})"


def format_delta(delta: timedelta) -> str:
    """"1 h 5 m", "45 s". Rounded the way a person reads a countdown."""
    seconds = int(max(0, delta.total_seconds()))
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    parts = []
    if hours:
        parts.append(f"{hours} h")
    if minutes:
        parts.append(f"{minutes} m")
    if seconds and not hours:
        parts.append(f"{seconds} s")
    return " ".join(parts) or "0 s"


class TimerService:
    """Holds the pending timers and fires them. One thread, one sorted list."""

    def __init__(
        self,
        on_fire: Optional[Callable[[Timer], None]] = None,
        store_path: Optional[Path] = None,
    ) -> None:
        #: What to do when one comes due. Injected rather than imported so this
        #: module knows nothing about notifications, and so a test can watch it
        #: fire without a popup appearing on the developer's screen.
        self.on_fire = on_fire
        self.store_path = Path(store_path) if store_path else STORE_PATH
        self._timers: Dict[str, Timer] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ── Persistence ──────────────────────────────────────────────────────────
    def load(self) -> List[Timer]:
        """Reads the store and returns the timers that came due while closed."""
        if not self.store_path.exists():
            return []
        try:
            rows = json.loads(self.store_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt store is not a crash
            return []

        missed: List[Timer] = []
        now = datetime.now()
        with self._lock:
            for row in rows:
                try:
                    timer = Timer(**row)
                except TypeError:
                    continue
                if timer.fired:
                    continue
                if timer.due <= now - MISSED_AFTER:
                    timer.missed = True
                    missed.append(timer)
                    continue
                self._timers[timer.id] = timer
        if missed:
            self._save()
        return missed

    def _save(self) -> None:
        with self._lock:
            rows = [asdict(t) for t in self._timers.values()]
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            self.store_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
        except Exception:  # noqa: BLE001 — a timer still runs without its file
            pass

    # ── The list ─────────────────────────────────────────────────────────────
    def add(self, label: str, fires_at: datetime, kind: str = "timer") -> Timer:
        timer = Timer(
            id=uuid.uuid4().hex[:8],
            label=label.strip() or ("Alarm" if kind == "alarm" else "Timer"),
            fires_at=fires_at.isoformat(timespec="seconds"),
            created_at=datetime.now().isoformat(timespec="seconds"),
            kind=kind,
        )
        with self._lock:
            self._timers[timer.id] = timer
        self._save()
        return timer

    def pending(self) -> List[Timer]:
        with self._lock:
            return sorted(
                (t for t in self._timers.values() if not t.fired),
                key=lambda t: t.due,
            )

    def cancel(self, identifier: str = "") -> List[Timer]:
        """Cancels by id, by exact label, or — with no identifier — all of them.

        Returns what was cancelled, so the caller reports the real number rather
        than "cancelled" for an empty list.
        """
        identifier = (identifier or "").strip().lower()
        with self._lock:
            if not identifier:
                removed = list(self._timers.values())
                self._timers.clear()
            else:
                removed = [
                    t for t in self._timers.values()
                    if t.id == identifier or t.label.lower() == identifier
                ]
                for timer in removed:
                    self._timers.pop(timer.id, None)
        if removed:
            self._save()
        return removed

    # ── The thread ───────────────────────────────────────────────────────────
    def start(self) -> List[Timer]:
        """Loads the store, starts ticking, and returns anything missed."""
        missed = self.load()
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run, name="MondayTimers", daemon=True
            )
            self._thread.start()
        return missed

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=TICK_SECONDS * 3)
        self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(TICK_SECONDS):
            self.tick()

    def tick(self, now: Optional[datetime] = None) -> List[Timer]:
        """Fires anything due. Separate from the thread so tests drive it.

        A thread that can only be tested by sleeping is a thread whose tests are
        slow and flaky; this one is a pure function of the clock.
        """
        now = now or datetime.now()
        with self._lock:
            due = [t for t in self._timers.values() if not t.fired and t.due <= now]
            for timer in due:
                timer.fired = True
        for timer in due:
            if self.on_fire is not None:
                try:
                    self.on_fire(timer)
                except Exception:  # noqa: BLE001 — one bad callback is not fatal
                    pass
        if due:
            with self._lock:
                for timer in due:
                    self._timers.pop(timer.id, None)
            self._save()
        return due
