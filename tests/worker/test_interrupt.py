"""InterruptionGate unit tests."""

from __future__ import annotations

from apps.worker.interrupt import InterruptionGate


def test_below_min_duration_ignored() -> None:
    gate = InterruptionGate(min_duration_ms=250, grace_ms=400)
    gate.mark_playback_start(0)
    # After grace, short burst
    s = gate.observe(t_ms=500, speaking=True, agent_active=True)
    assert s.reason == "below_min"
    assert not s.should_interrupt
    s2 = gate.observe(t_ms=600, speaking=True, agent_active=True)
    assert s2.speech_ms == 100
    assert not s2.should_interrupt


def test_sustained_speech_triggers() -> None:
    gate = InterruptionGate(min_duration_ms=250, grace_ms=400)
    gate.mark_playback_start(0)
    gate.observe(t_ms=500, speaking=True, agent_active=True)
    s = gate.observe(t_ms=760, speaking=True, agent_active=True)
    assert s.should_interrupt
    assert s.reason == "sustained"
    assert s.speech_ms >= 250


def test_grace_period_blocks() -> None:
    gate = InterruptionGate(min_duration_ms=250, grace_ms=400)
    gate.mark_playback_start(1000)
    s = gate.observe(t_ms=1200, speaking=True, agent_active=True)
    assert s.reason == "grace"
    assert not s.should_interrupt


def test_idle_when_agent_not_active() -> None:
    gate = InterruptionGate()
    s = gate.observe(t_ms=100, speaking=True, agent_active=False)
    assert s.reason == "idle"
    assert not s.should_interrupt
