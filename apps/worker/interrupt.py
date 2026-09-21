"""Barge-in gate: min speech duration + post-playback grace (design §4.2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BargeInSample:
    """Result of observing one speech-activity sample while the agent may be active."""

    should_interrupt: bool
    speech_ms: int
    reason: str  # sustained | grace | below_min | idle | not_agent


class InterruptionGate:
    """Track caller speech against barge-in thresholds.

    Exact LiveKit VAD frames are not required — callers feed ``speaking`` samples with a
    monotonic ``t_ms`` (worker clock). False triggers below ``min_duration_ms`` are ignored.
    """

    def __init__(self, *, min_duration_ms: int = 250, grace_ms: int = 400) -> None:
        self.min_duration_ms = min_duration_ms
        self.grace_ms = grace_ms
        self._playback_started_at_ms: int | None = None
        self._speech_started_at_ms: int | None = None

    def mark_playback_start(self, t_ms: int) -> None:
        self._playback_started_at_ms = t_ms
        self._speech_started_at_ms = None

    def clear_playback(self) -> None:
        self._playback_started_at_ms = None
        self._speech_started_at_ms = None

    def observe(
        self,
        *,
        t_ms: int,
        speaking: bool,
        agent_active: bool,
    ) -> BargeInSample:
        """Return whether barge-in should fire for this sample.

        ``agent_active`` is True in THINKING or SPEAKING (cancel LLM and/or TTS).
        """
        if not agent_active:
            self._speech_started_at_ms = None
            return BargeInSample(False, 0, "idle")

        if not speaking:
            self._speech_started_at_ms = None
            return BargeInSample(False, 0, "idle")

        if self._speech_started_at_ms is None:
            self._speech_started_at_ms = t_ms
        speech_ms = max(0, t_ms - self._speech_started_at_ms)

        if self._playback_started_at_ms is not None:
            since_start = t_ms - self._playback_started_at_ms
            if since_start < self.grace_ms:
                return BargeInSample(False, speech_ms, "grace")

        if speech_ms < self.min_duration_ms:
            return BargeInSample(False, speech_ms, "below_min")

        return BargeInSample(True, speech_ms, "sustained")
