"""Graceful degradation matrix (design §4.11)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class FailureKind(StrEnum):
    ASR = "asr"
    BRAIN = "brain"
    TOOL = "tool"
    BIZ = "biz"
    TTS = "tts"
    EVENTS = "events"


class DegradeAction(StrEnum):
    CONTINUE = "continue"
    ANNOUNCE = "announce"
    OFFER_CALLBACK = "offer_callback"
    HANDOFF = "handoff"
    TEXT_ONLY = "text_only"
    BUFFER_EVENTS = "buffer_events"
    END_CALL = "end_call"


@dataclass(frozen=True, slots=True)
class DegradeDecision:
    action: DegradeAction
    kind: FailureKind
    failure_count: int
    spoken_notice: str
    end_reason: str | None = None
    data_code: str | None = None


@dataclass
class DegradeController:
    """Per-call failure counters → matrix actions."""

    max_asr_failures: int = 2
    max_brain_failures: int = 2
    max_tool_failures: int = 2
    _counts: dict[FailureKind, int] = field(default_factory=dict)

    def count(self, kind: FailureKind) -> int:
        return self._counts.get(kind, 0)

    def record(self, kind: FailureKind) -> DegradeDecision:
        n = self._counts.get(kind, 0) + 1
        self._counts[kind] = n

        if kind is FailureKind.ASR:
            if n >= self.max_asr_failures:
                return DegradeDecision(
                    DegradeAction.END_CALL,
                    kind,
                    n,
                    "I'm still having trouble hearing you. Please try again later.",
                    end_reason="asr_error",
                    data_code="asr_error",
                )
            return DegradeDecision(
                DegradeAction.ANNOUNCE,
                kind,
                n,
                "I'm having trouble hearing you. You can also leave a callback request.",
                data_code="asr_trouble",
            )

        if kind is FailureKind.BRAIN:
            if n >= self.max_brain_failures:
                return DegradeDecision(
                    DegradeAction.HANDOFF,
                    kind,
                    n,
                    "I'm having trouble reaching our assistant. I can take a callback or "
                    "transfer you to a human.",
                    end_reason="brain_error",
                    data_code="brain_handoff",
                )
            return DegradeDecision(
                DegradeAction.ANNOUNCE,
                kind,
                n,
                "Sorry, I hit a snag. One more try.",
                data_code="brain_retry",
            )

        if kind is FailureKind.TOOL:
            if n >= self.max_tool_failures:
                return DegradeDecision(
                    DegradeAction.OFFER_CALLBACK,
                    kind,
                    n,
                    "I couldn't finish that action. Can I take a callback instead?",
                    end_reason="tool_error",
                    data_code="tool_callback",
                )
            return DegradeDecision(
                DegradeAction.CONTINUE,
                kind,
                n,
                "",
                data_code="tool_retry",
            )

        if kind is FailureKind.BIZ:
            return DegradeDecision(
                DegradeAction.OFFER_CALLBACK,
                kind,
                n,
                "Our booking system is unavailable. I can take a callback and we'll follow up.",
                data_code="biz_down",
            )

        if kind is FailureKind.TTS:
            return DegradeDecision(
                DegradeAction.TEXT_ONLY,
                kind,
                n,
                "Audio playback is unavailable; continuing in text-only mode.",
                data_code="tts_text_only",
            )

        # EVENTS
        return DegradeDecision(
            DegradeAction.BUFFER_EVENTS,
            kind,
            n,
            "",
            data_code="events_buffered",
        )
