"""Per-call timeline built from event envelopes (design §4.7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from callscope.events.models import Event


@dataclass(slots=True)
class TimelineSpan:
    kind: str
    t_start_ms: int
    t_end_ms: int | None = None
    turn_id: UUID | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_ids: list[UUID] = field(default_factory=list)


@dataclass(slots=True)
class CallTimeline:
    call_id: UUID
    events: list[Event]
    spans: list[TimelineSpan] = field(default_factory=list)

    def events_of(self, *types: str) -> list[Event]:
        wanted = set(types)
        return [e for e in self.events if e.type in wanted]

    def sorted_events(self) -> list[Event]:
        return sorted(self.events, key=lambda e: (e.t_ms, str(e.event_id)))


def build_timeline(call_id: UUID, events: list[Event]) -> CallTimeline:
    """Pure function: project events into lane spans for review UI / rules."""
    ordered = sorted(
        (e for e in events if e.call_id == call_id),
        key=lambda e: (e.t_ms, str(e.event_id)),
    )
    spans: list[TimelineSpan] = []
    open_vad: TimelineSpan | None = None

    for ev in ordered:
        if ev.type == "vad.speech_start":
            open_vad = TimelineSpan(
                kind="caller_vad",
                t_start_ms=ev.t_ms,
                turn_id=ev.turn_id,
                payload=dict(ev.payload),
                event_ids=[ev.event_id],
            )
        elif ev.type == "vad.speech_end" and open_vad is not None:
            open_vad.t_end_ms = ev.t_ms
            open_vad.event_ids.append(ev.event_id)
            spans.append(open_vad)
            open_vad = None
        elif ev.type in {
            "stt.partial",
            "stt.final",
            "endpoint.decided",
            "brain.first_token",
            "brain.done",
            "tts.first_audio",
            "playback.start",
            "playback.stop",
            "tool.call",
            "tool.result",
            "barge_in.detected",
            "barge_in.applied",
            "filler.played",
            "policy.denied",
            "provider.error",
        }:
            spans.append(
                TimelineSpan(
                    kind=ev.type,
                    t_start_ms=ev.t_ms,
                    t_end_ms=ev.t_ms,
                    turn_id=ev.turn_id,
                    payload=dict(ev.payload),
                    event_ids=[ev.event_id],
                )
            )

    if open_vad is not None:
        spans.append(open_vad)

    return CallTimeline(call_id=call_id, events=ordered, spans=spans)


__all__ = ["CallTimeline", "TimelineSpan", "build_timeline"]
