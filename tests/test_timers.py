"""
ROADMAP Phase 11 — timers, alarms, and media keys.

These were dropped from the training corpus for not existing. `datagen/massive.py`
refuses an intent MONDAY cannot serve, with the reason attached, and three of its
entries read "no alarm or timer exists" — several hundred real utterances thrown
away because there was nowhere to send them. This tranche built the destination
and moved the mapping in the same commit.

What is asserted here, in order of how much it matters:

1. **A timer says what it actually is.** A thread in this process, which rings
   while MONDAY runs and not otherwise. The confirmation says so; a user should
   not discover it from a reminder that never came.
2. **A missed timer is reported as missed** — not fired four hours late, and not
   silently dropped.
3. **Media keys claim only that a key was sent.** `KeypressSent` says nothing
   about which app received it or whether anything was playing, because nothing
   here can see that.
4. **Parsing is summed, not first-match.** "1 hour 30 minutes" is 90 minutes.

Nothing here sleeps. `TimerService.tick(now)` takes the clock as an argument
precisely so the tests are a pure function of it — a thread that can only be
tested by waiting is a thread whose tests are slow and flaky.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

import pytest

from core.planner import MasterPlanner
from core.timers import (
    MISSED_AFTER,
    TimerService,
    format_delta,
    parse_clock_time,
    parse_duration,
)


# ── Parsing ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,seconds", [
    ("5 minutes", 300),
    ("30 seconds", 30),
    ("2 hours", 7200),
    ("an hour", 3600),
    ("a minute", 60),
    ("10 mins", 600),
    # Summed, not first-match. The old volume parser took the first number
    # anywhere in the command and got the wrong one.
    ("1 hour 30 minutes", 5400),
    ("2 hours 15 mins", 8100),
    # The article between count and unit. Without it "half" was skipped and the
    # bare "an hour" matched instead, so a 30-minute timer became 60.
    ("half an hour", 1800),
    ("a quarter hour", 900),
])
def test_a_duration_is_read_whole(text, seconds):
    assert parse_duration(text) == timedelta(seconds=seconds)


@pytest.mark.parametrize("text", ["", "no duration here", "set a timer", "hello"])
def test_no_duration_is_none_not_a_guess(text):
    assert parse_duration(text) is None


def test_a_duration_survives_the_words_around_it():
    assert parse_duration("set a timer for 20 minutes please") == timedelta(minutes=20)


@pytest.mark.parametrize("text,hour,minute", [
    ("7am", 7, 0),
    ("7:30 pm", 19, 30),
    ("18:45", 18, 45),
    ("12am", 0, 0),
    ("12pm", 12, 0),
])
def test_a_clock_time_is_read(text, hour, minute):
    when = parse_clock_time(text, now=datetime(2026, 8, 18, 6, 0))
    assert (when.hour, when.minute) == (hour, minute)


def test_a_time_that_has_passed_means_tomorrow():
    """"Wake me at 7am" said at 9am is not a request about the past."""
    now = datetime(2026, 8, 18, 9, 0)
    when = parse_clock_time("7am", now=now)
    assert when.date() == (now + timedelta(days=1)).date()
    assert when.hour == 7


def test_an_impossible_time_is_refused():
    assert parse_clock_time("at 99:99", now=datetime(2026, 8, 18, 9, 0)) is None


def test_format_delta_reads_like_a_countdown():
    assert format_delta(timedelta(seconds=45)) == "45 s"
    assert format_delta(timedelta(seconds=3725)) == "1 h 2 m"
    assert format_delta(timedelta(seconds=-5)) == "0 s"


# ── The service ──────────────────────────────────────────────────────────────
@pytest.fixture
def service(tmp_path):
    """A service with its own store, so a test never touches data/timers.json."""
    return TimerService(store_path=tmp_path / "timers.json")


def test_a_timer_fires_once_and_only_when_due(service):
    now = datetime(2026, 8, 18, 12, 0)
    fired: List[Any] = []
    service.on_fire = fired.append
    service.add("pasta", now + timedelta(minutes=10))

    assert service.tick(now) == []
    assert service.tick(now + timedelta(minutes=9)) == []
    assert [t.label for t in service.tick(now + timedelta(minutes=11))] == ["pasta"]
    assert len(fired) == 1
    # And it does not fire a second time on the next tick.
    assert service.tick(now + timedelta(minutes=12)) == []
    assert len(fired) == 1


def test_pending_is_ordered_by_when_it_rings(service):
    now = datetime(2026, 8, 18, 12, 0)
    service.add("later", now + timedelta(hours=2))
    service.add("sooner", now + timedelta(minutes=5))
    assert [t.label for t in service.pending()] == ["sooner", "later"]


def test_a_callback_that_raises_does_not_stop_the_others(service):
    """The tick thread holds every other pending timer. One bad notification
    must not take them all down with it."""
    now = datetime(2026, 8, 18, 12, 0)

    def _explode(timer):
        raise RuntimeError("the notification failed")

    service.on_fire = _explode
    service.add("one", now - timedelta(seconds=1))
    service.add("two", now - timedelta(seconds=1))
    assert len(service.tick(now)) == 2


def test_cancelling_reports_what_was_actually_cancelled(service):
    now = datetime(2026, 8, 18, 12, 0)
    service.add("pasta", now + timedelta(minutes=10))
    service.add("laundry", now + timedelta(minutes=30))

    assert [t.label for t in service.cancel("pasta")] == ["pasta"]
    assert [t.label for t in service.pending()] == ["laundry"]
    assert service.cancel("no such timer") == []
    assert len(service.cancel()) == 1


# ── Surviving a restart ──────────────────────────────────────────────────────
def test_a_pending_timer_survives_a_restart(tmp_path):
    store = tmp_path / "timers.json"
    now = datetime.now()

    first = TimerService(store_path=store)
    first.add("pasta", now + timedelta(hours=1))

    second = TimerService(store_path=store)
    assert second.load() == []                       # nothing missed
    assert [t.label for t in second.pending()] == ["pasta"]


def test_a_timer_that_came_due_while_closed_is_reported_as_missed(tmp_path):
    """Not fired late, and not silently dropped.

    Firing "your 10-minute pasta timer" the next morning is worse than saying it
    passed, and saying nothing is worse than both.
    """
    store = tmp_path / "timers.json"
    now = datetime.now()

    first = TimerService(store_path=store)
    first.add("pasta", now - MISSED_AFTER - timedelta(minutes=5))

    second = TimerService(store_path=store)
    missed = second.load()

    assert [t.label for t in missed] == ["pasta"]
    assert missed[0].missed is True
    assert second.pending() == [], "a missed timer must not stay pending"


def test_a_corrupt_store_is_not_a_crash(tmp_path):
    store = tmp_path / "timers.json"
    store.write_text("{not json at all", encoding="utf-8")
    assert TimerService(store_path=store).load() == []


# ── Through the planner ──────────────────────────────────────────────────────
@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    p.router.llm = None
    return p


@pytest.fixture(autouse=True)
def _no_leftover_timers(planner):
    """Each test starts with an empty list and leaves one behind."""
    planner.timer_service.cancel()
    yield
    planner.timer_service.cancel()


def _run(planner, command) -> Dict[str, Any]:
    return planner.process_command(command)["execution_result"]


@pytest.mark.parametrize("command", [
    "set a timer for 10 minutes",
    "set a 5 minute timer",
    "timer for 20 minutes",
    "remind me in 15 minutes",
    "wake me in an hour",
])
def test_setting_a_timer_reaches_the_timer(planner, command):
    result = _run(planner, command)
    assert result["success"] is True
    assert result["evidence"]["kind"] == "task_queued"


def test_the_confirmation_admits_it_only_rings_while_running(planner):
    """The one thing a user cannot find out any other way until it is too late."""
    message = _run(planner, "set a timer for 10 minutes")["message"]
    assert "while I'm running" in message


@pytest.mark.parametrize("command", [
    "set an alarm for 7am",
    "wake me up at 6:30am",
    "alarm at 9pm",
])
def test_setting_an_alarm_reaches_the_alarm(planner, command):
    assert _run(planner, command)["success"] is True


def test_a_timer_with_no_duration_asks_rather_than_guessing(planner):
    result = _run(planner, "set a timer")
    assert result["success"] is False
    assert result["error"] == "TIMER_NO_DURATION"


def test_a_timer_beyond_a_week_is_refused_with_the_reason(planner):
    """It would not survive that long, so promising it would be a lie."""
    result = _run(planner, "set a timer for 30 days")
    assert result["success"] is False
    assert result["error"] == "TIMER_TOO_LONG"


def test_listing_and_cancelling_round_trip(planner):
    _run(planner, "set a timer for 10 minutes")
    listed = _run(planner, "what timers do i have")
    assert listed["success"] is True
    assert "1 pending" in listed["message"]

    cancelled = _run(planner, "cancel my timers")
    assert cancelled["success"] is True
    assert planner.timer_service.pending() == []


def test_cancelling_nothing_is_a_failure_not_a_cheerful_success(planner):
    result = _run(planner, "cancel my timers")
    assert result["success"] is False
    assert result["error"] == "TIMER_NOT_FOUND"


def test_an_empty_list_says_so(planner):
    result = _run(planner, "timers")
    assert result["success"] is True
    assert "No timers" in result["message"]


# ── Media keys ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize("command,skill", [
    ("next song", "media_next"),
    ("skip this", "media_next"),
    ("previous track", "media_previous"),
    ("pause the music", "media_play_pause"),
    ("stop the music", "media_stop"),
])
def test_media_commands_reach_the_media_keys(planner, command, skill):
    from ml.intent_classifier import predict_intent

    intent, confidence, _ = predict_intent(planner.classifier, command)
    decision = planner.router.route(command, intent=intent, confidence=confidence)
    assert decision.routed, f"{command!r} routes nowhere"
    assert decision.skill.name == skill


def test_a_media_key_claims_only_that_a_key_was_sent(planner, monkeypatch):
    """It cannot see which app received it, or whether anything was playing.

    `KeypressSent` is the whole claim. Anything stronger — "now playing" — would
    be an assertion about an application MONDAY never spoke to.
    """
    import core.skills_timers as timers_module

    monkeypatch.setattr(timers_module, "send_media_key", lambda action: True)
    result = _run(planner, "next song")

    assert result["success"] is True
    assert result["evidence"]["kind"] == "keypress_sent"
    assert "playing" not in result["message"].lower()


def test_a_platform_without_media_keys_says_so(planner, monkeypatch):
    import core.skills_timers as timers_module

    monkeypatch.setattr(timers_module, "send_media_key", lambda action: False)
    result = _run(planner, "next song")

    assert result["success"] is False
    assert result["error"] == "MEDIA_KEY_UNAVAILABLE"


def test_choosing_what_to_play_is_still_refused(planner):
    """Media keys control what is already open. "Play some jazz" asks MONDAY to
    choose music, which nothing here can do — and `datagen/massive.py` keeps
    `play_music` refused for exactly this reason."""
    from ml.intent_classifier import predict_intent

    command = "play some jazz"
    intent, confidence, _ = predict_intent(planner.classifier, command)
    decision = planner.router.route(command, intent=intent, confidence=confidence)
    assert not decision.routed or decision.skill.name != "media_play_pause"
