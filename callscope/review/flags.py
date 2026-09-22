"""Auto-flag rules over a call timeline (design §4.7)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from uuid import UUID

from callscope.review.timeline import CallTimeline

_REPEAT = re.compile(r"(?i)\b(what|sorry|pardon|no+|huh)\b")


@dataclass(frozen=True, slots=True)
class FlagThresholds:
    asr_confidence_min: float = 0.55
    dead_air_ms: int = 2_000
    hangup_after_agent_ms: int = 10_000
    entity_min_len: int = 3


@dataclass(frozen=True, slots=True)
class FlagHit:
    rule_id: str
    reason: str
    turn_id: UUID | None
    evidence_event_ids: tuple[UUID, ...]
    detail: dict[str, Any] = field(default_factory=dict)


class FlagRule(Protocol):
    rule_id: str

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]: ...


def _ids(*events: Any) -> tuple[UUID, ...]:
    return tuple(e.event_id for e in events if getattr(e, "event_id", None) is not None)


@dataclass(frozen=True, slots=True)
class LowAsrConfidenceRule:
    rule_id: str = "low_asr_confidence"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        hits: list[FlagHit] = []
        for ev in timeline.events_of("stt.final"):
            conf = ev.payload.get("avg_conf", ev.payload.get("confidence"))
            if conf is None:
                continue
            if float(conf) < thresholds.asr_confidence_min:
                hits.append(
                    FlagHit(
                        rule_id=self.rule_id,
                        reason=f"ASR avg_conf {conf} < {thresholds.asr_confidence_min}",
                        turn_id=ev.turn_id,
                        evidence_event_ids=_ids(ev),
                        detail={"avg_conf": float(conf)},
                    )
                )
        return hits


@dataclass(frozen=True, slots=True)
class ToolArgNotInAsrRule:
    rule_id: str = "tool_arg_not_in_asr"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        finals = {
            (e.turn_id, str(e.payload.get("text") or "").lower())
            for e in timeline.events_of("stt.final")
        }
        hits: list[FlagHit] = []
        for ev in timeline.events_of("tool.call"):
            args = ev.payload.get("args") or ev.payload.get("arguments") or {}
            if not isinstance(args, dict):
                continue
            asr_text = " ".join(t for tid, t in finals if tid == ev.turn_id)
            for key, val in args.items():
                s = str(val).strip()
                if len(s) < thresholds.entity_min_len:
                    continue
                if s.lower() not in asr_text:
                    hits.append(
                        FlagHit(
                            rule_id=self.rule_id,
                            reason=f"tool arg {key}={s!r} not in ASR text",
                            turn_id=ev.turn_id,
                            evidence_event_ids=_ids(ev),
                            detail={"arg": key, "value": s},
                        )
                    )
        return hits


@dataclass(frozen=True, slots=True)
class CallerRepetitionRule:
    rule_id: str = "caller_repetition"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        _ = thresholds
        hits: list[FlagHit] = []
        texts: list[tuple[Any, str]] = []
        for ev in timeline.events_of("stt.final"):
            text = str(ev.payload.get("text") or "").strip().lower()
            if not text:
                continue
            if _REPEAT.search(text) or (texts and text == texts[-1][1]):
                hits.append(
                    FlagHit(
                        rule_id=self.rule_id,
                        reason="caller repair/repetition cue",
                        turn_id=ev.turn_id,
                        evidence_event_ids=_ids(ev),
                        detail={"text": text},
                    )
                )
            texts.append((ev, text))
        return hits


@dataclass(frozen=True, slots=True)
class DeadAirRule:
    rule_id: str = "dead_air"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        hits: list[FlagHit] = []
        speech_ends = timeline.events_of("vad.speech_end", "endpoint.decided")
        fillers = {e.t_ms for e in timeline.events_of("filler.played")}
        brain_starts = timeline.events_of("brain.first_token", "tts.first_audio", "playback.start")
        for end in speech_ends:
            nxt = next((b for b in brain_starts if b.t_ms >= end.t_ms), None)
            if nxt is None:
                continue
            gap = nxt.t_ms - end.t_ms
            if gap > thresholds.dead_air_ms and not any(end.t_ms <= f <= nxt.t_ms for f in fillers):
                hits.append(
                    FlagHit(
                        rule_id=self.rule_id,
                        reason=f"dead air {gap} ms without filler",
                        turn_id=end.turn_id,
                        evidence_event_ids=_ids(end, nxt),
                        detail={"gap_ms": gap},
                    )
                )
        return hits


@dataclass(frozen=True, slots=True)
class AgentTalkOverCallerRule:
    rule_id: str = "agent_talk_over_caller"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        _ = thresholds
        hits: list[FlagHit] = []
        vad_active: list[tuple[int, int | None]] = []
        for sp in timeline.spans:
            if sp.kind == "caller_vad":
                vad_active.append((sp.t_start_ms, sp.t_end_ms))
        for ev in timeline.events_of("playback.start", "tts.first_audio"):
            for start, end in vad_active:
                if start <= ev.t_ms and (end is None or ev.t_ms <= end):
                    hits.append(
                        FlagHit(
                            rule_id=self.rule_id,
                            reason="agent audio while caller VAD active",
                            turn_id=ev.turn_id,
                            evidence_event_ids=_ids(ev),
                        )
                    )
                    break
        return hits


@dataclass(frozen=True, slots=True)
class BargeRestartScratchRule:
    rule_id: str = "barge_restart_scratch"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        _ = thresholds
        hits: list[FlagHit] = []
        for barge in timeline.events_of("barge_in.detected"):
            follow = [
                e
                for e in timeline.events_of("brain.request")
                if e.t_ms >= barge.t_ms and e.t_ms - barge.t_ms < 3000
            ]
            for br in follow[:1]:
                if br.payload.get("resume_from_prefix") is True:
                    continue
                hits.append(
                    FlagHit(
                        rule_id=self.rule_id,
                        reason="barge-in then brain.request without resume marker",
                        turn_id=barge.turn_id,
                        evidence_event_ids=_ids(barge, br),
                    )
                )
        return hits


@dataclass(frozen=True, slots=True)
class PolicyDeniedRule:
    rule_id: str = "policy_denied"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        _ = thresholds
        return [
            FlagHit(
                rule_id=self.rule_id,
                reason=str(e.payload.get("rule") or "policy denial"),
                turn_id=e.turn_id,
                evidence_event_ids=_ids(e),
                detail=dict(e.payload),
            )
            for e in timeline.events_of("policy.denied")
        ]


@dataclass(frozen=True, slots=True)
class ToolErrorRule:
    rule_id: str = "tool_error"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        _ = thresholds
        hits: list[FlagHit] = []
        for e in timeline.events_of("tool.result", "provider.error"):
            err = e.payload.get("error") or e.payload.get("status")
            if e.type == "provider.error" or err not in (None, "ok", "success"):
                if e.type == "tool.result" and not e.payload.get("error"):
                    continue
                hits.append(
                    FlagHit(
                        rule_id=self.rule_id,
                        reason=str(err or e.type),
                        turn_id=e.turn_id,
                        evidence_event_ids=_ids(e),
                    )
                )
        return hits


@dataclass(frozen=True, slots=True)
class UnsupportedClaimRule:
    rule_id: str = "unsupported_claim"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        _ = thresholds
        hits: list[FlagHit] = []
        for e in timeline.events:
            if e.payload.get("unsupported_claim") or e.payload.get("hallucination"):
                hits.append(
                    FlagHit(
                        rule_id=self.rule_id,
                        reason="agent claim flagged unsupported",
                        turn_id=e.turn_id,
                        evidence_event_ids=_ids(e),
                    )
                )
        return hits


@dataclass(frozen=True, slots=True)
class EarlyHangupRule:
    rule_id: str = "early_hangup"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        ends = timeline.events_of("call.end")
        if not ends:
            return []
        end = ends[-1]
        if str(end.payload.get("reason") or "") not in {"client_end", "caller_hangup", "hangup"}:
            # Still consider if within window of last agent audio
            pass
        agent = timeline.events_of("playback.start", "tts.first_audio", "brain.first_token")
        if not agent:
            return []
        last_agent = max(agent, key=lambda e: e.t_ms)
        if 0 <= end.t_ms - last_agent.t_ms <= thresholds.hangup_after_agent_ms:
            return [
                FlagHit(
                    rule_id=self.rule_id,
                    reason="caller ended within 10s of agent turn",
                    turn_id=last_agent.turn_id,
                    evidence_event_ids=_ids(last_agent, end),
                    detail={"delta_ms": end.t_ms - last_agent.t_ms},
                )
            ]
        return []


@dataclass(frozen=True, slots=True)
class EvalFailureRule:
    rule_id: str = "eval_failure"

    def evaluate(self, timeline: CallTimeline, thresholds: FlagThresholds) -> list[FlagHit]:
        _ = thresholds
        hits: list[FlagHit] = []
        for e in timeline.events:
            if e.payload.get("eval_failed") or e.payload.get("task_success") is False:
                hits.append(
                    FlagHit(
                        rule_id=self.rule_id,
                        reason="eval item failure",
                        turn_id=e.turn_id,
                        evidence_event_ids=_ids(e),
                    )
                )
        return hits


DEFAULT_RULES: tuple[FlagRule, ...] = cast(
    tuple[FlagRule, ...],
    (
        LowAsrConfidenceRule(),
        ToolArgNotInAsrRule(),
        CallerRepetitionRule(),
        DeadAirRule(),
        AgentTalkOverCallerRule(),
        BargeRestartScratchRule(),
        PolicyDeniedRule(),
        ToolErrorRule(),
        UnsupportedClaimRule(),
        EarlyHangupRule(),
        EvalFailureRule(),
    ),
)


def evaluate_flags(
    timeline: CallTimeline,
    *,
    thresholds: FlagThresholds | None = None,
    rules: tuple[FlagRule, ...] | None = None,
) -> list[FlagHit]:
    thr = thresholds or FlagThresholds()
    out: list[FlagHit] = []
    for rule in rules or DEFAULT_RULES:
        out.extend(rule.evaluate(timeline, thr))
    return out


__all__ = [
    "DEFAULT_RULES",
    "FlagHit",
    "FlagRule",
    "FlagThresholds",
    "evaluate_flags",
]
