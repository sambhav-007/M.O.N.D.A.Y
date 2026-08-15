"""
The demo script is executed, not merely written.

`DEMO.md` is the rehearsed run for a live demonstration. A demo script that is
only prose rots the moment a skill is renamed or a pattern is narrowed, and the
first anyone finds out is in front of an audience — which is precisely the
situation the "offline demo path" item in `handoff.md` §6 was raised about.

So the commands in `DEMO.md` are parsed out of the file itself and run here,
with sockets blocked (`--block-network` is on by default, see `conftest.py`).
Three claims are checked, and they are the three the document makes:

1. **Every command in a ``demo-offline`` block reaches a skill declared
   `offline=True`.** A skill that needs the network cannot enter the offline
   script by accident, whatever the prose says.
2. **Every one of them succeeds with no network.** This is the claim that
   matters on the day.
3. **Every command in a ``demo-honest`` block fails, with an error code.** Act 6
   is about what MONDAY refuses to pretend, and a fabricated success there would
   be worse than any of the failures it demonstrates.

The ``demo-network`` block is parsed and checked for *routing* only. Running it
is the one thing this file will not do: those commands are in the script
precisely because they depend on third-party services with no SLA.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.planner import MasterPlanner

DEMO_PATH = Path(__file__).resolve().parent.parent / "DEMO.md"

_FENCE = re.compile(r"```(demo-[a-z]+)\n(.*?)```", re.DOTALL)


def _commands(tag: str) -> list[str]:
    text = DEMO_PATH.read_text(encoding="utf-8")
    out: list[str] = []
    for found_tag, body in _FENCE.findall(text):
        if found_tag == tag:
            out += [ln.strip() for ln in body.splitlines() if ln.strip()]
    return out


OFFLINE = _commands("demo-offline")
HONEST = _commands("demo-honest")
NETWORK = _commands("demo-network")

# Answers to a question MONDAY has just asked, not commands in their own right.
# They are in the script because a demo is a conversation, but they route
# through `pending_clarification` rather than through the router, so the
# per-command routing assertions do not apply to them.
REPLIES = {"no", "yes", "cancel", "send"}


@pytest.fixture(scope="module")
def planner():
    p = MasterPlanner()
    p.enable_voice = False
    return p


@pytest.fixture(autouse=True)
def _clear_state(planner):
    yield
    planner.pending_clarification = None


@pytest.fixture
def no_side_effects(planner, monkeypatch, fake_powershell):
    """Stops the demo commands reaching hardware, apps or the speakers.

    Three of them have real side effects that a test run should not have:
    `screenshot` writes a PNG, the volume commands drive the speakers (which is
    what `fake_powershell` is for), and a WhatsApp command opens the desktop
    app. Stubbing them keeps this a test of routing and reporting — which is
    what is being claimed — rather than a test of the operating system.
    """
    monkeypatch.setattr(
        planner.comms_agent, "open_whatsapp_chat",
        lambda phone, text="": {
            "success": True, "phone": phone, "text": text,
            "message": f"✓ Chat open for +{phone} with the message typed.",
        },
    )
    monkeypatch.setattr(
        planner.computer_agent, "launch_application",
        lambda app: {"success": True, "message": f"✓ Opened {app}"},
    )
    return planner


# ── The file itself ──────────────────────────────────────────────────────────
def test_the_demo_script_exists_and_has_all_three_blocks():
    """A missing block would make the assertions below vacuously true."""
    assert DEMO_PATH.exists(), "DEMO.md is the rehearsed script and must exist"
    assert len(OFFLINE) >= 15, f"only {len(OFFLINE)} offline demo commands parsed"
    assert len(HONEST) >= 4, f"only {len(HONEST)} honest-failure commands parsed"
    assert NETWORK, "the network block should still be listed, and labelled"


# ── Claim 1: nothing in the offline script needs the network ─────────────────
@pytest.mark.parametrize("command", [c for c in OFFLINE if c not in REPLIES])
def test_offline_demo_commands_route_to_offline_skills(planner, command):
    decision = planner.router.route(command)
    assert decision.routed, (
        f"{command!r} is in the offline demo script but no skill claims it"
    )
    assert decision.skill.offline, (
        f"{command!r} routes to {decision.skill.name}, which is declared "
        f"offline=False — it does not belong in the offline script"
    )


# ── Claim 2: and they all work with the network off ──────────────────────────
def test_the_whole_offline_script_runs_with_no_network(no_side_effects):
    """Runs the script end to end, in order, as it would be demonstrated.

    In order and in one test on purpose: the script is a conversation. `no`
    answers the Tier-2 prompt that `kill notepad` raises, and `cancel` answers
    the email confirmation — run out of order they answer nothing, which is a
    different thing to test (and is, in `test_help_command.py`).
    """
    planner = no_side_effects
    failures = []
    for command in OFFLINE:
        result = planner.process_command(command)["execution_result"]
        if not result.get("success"):
            failures.append(
                f"  {command!r} → {result.get('error', '?')}: "
                f"{str(result.get('message', ''))[:120]}"
            )
    planner.pending_clarification = None
    assert not failures, "offline demo commands failed:\n" + "\n".join(failures)


def test_the_tier2_gate_actually_arms_during_the_demo(no_side_effects):
    """Act 4 is the centrepiece, so it gets its own assertion.

    The script's value is that `kill notepad` *stops and asks*. A version of
    this that quietly killed the process would still pass the run-through above,
    because the gate reports success either way.
    """
    planner = no_side_effects
    gate = planner.process_command("kill notepad")["execution_result"]
    assert gate.get("awaiting_tier2_approval") is True
    assert gate.get("risk_tier") == 2
    assert planner.pending_clarification is not None

    cancelled = planner.process_command("no")["execution_result"]
    assert cancelled.get("cancelled") is True
    assert cancelled.get("executed") is not True


# ── Claim 3: the closing act fails honestly ──────────────────────────────────
@pytest.mark.parametrize("command", HONEST)
def test_honest_failures_stay_failures(no_side_effects, command):
    """Act 6 demonstrates refusals. A success here would undo the whole point.

    Each of these once returned a confident fabricated success — a smart light
    that switched nothing, a meeting recorder that captured nothing, an inbox
    reader that invented a subject line. The assertion is deliberately blunt:
    `success` must be False and there must be an error code to branch on.
    """
    result = no_side_effects.process_command(command)["execution_result"]
    assert result.get("success") is False, (
        f"{command!r} is in the honest-failure act but reported success: "
        f"{str(result.get('message', ''))[:160]}"
    )
    assert result.get("error"), f"{command!r} failed without an error code"


# ── The network block is labelled honestly ───────────────────────────────────
@pytest.mark.parametrize("command", NETWORK)
def test_network_demo_commands_are_declared_as_needing_the_network(planner, command):
    """Not run — checked. These are the ones that can stall in front of an
    audience, and the script's job is to say so before they do."""
    decision = planner.router.route(command)
    assert decision.routed, f"{command!r} is in the demo script but routes nowhere"
    assert decision.skill.offline is False, (
        f"{command!r} routes to {decision.skill.name}, which is declared "
        f"offline=True — if it needs no network it belongs in the offline script"
    )


# ── The two lists must not overlap ───────────────────────────────────────────
def test_no_command_is_in_two_acts():
    """A command that both must succeed offline and must fail honestly is a
    contradiction, and the kind that survives a long time in a document."""
    overlap = (set(OFFLINE) & set(HONEST)) | (set(OFFLINE) & set(NETWORK))
    assert not overlap, f"commands appear in conflicting demo blocks: {sorted(overlap)}"
