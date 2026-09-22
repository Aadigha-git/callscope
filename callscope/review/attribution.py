"""First-pass root-cause attribution heuristics (design §4.7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from callscope.review.flags import FlagHit, FlagThresholds, evaluate_flags
from callscope.review.timeline import CallTimeline


@dataclass(frozen=True, slots=True)
class Attribution:
    code: str
    confidence: float
    evidence_event_ids: tuple[UUID, ...]
    rationale: str
    detail: dict[str, Any] = field(default_factory=dict)


def _ids_from_flags(*hits: FlagHit) -> tuple[UUID, ...]:
    out: list[UUID] = []
    for h in hits:
        out.extend(h.evidence_event_ids)
    return tuple(out)


def attribute_call(
    timeline: CallTimeline,
    *,
    thresholds: FlagThresholds | None = None,
    ref_transcript: str | None = None,
    hyp_transcript: str | None = None,
    intent_ref: str | None = None,
    intent_hyp: str | None = None,
    slots_ref: dict[str, Any] | None = None,
    slots_hyp: dict[str, Any] | None = None,
    wer: float | None = None,
    unsupported_claim: bool = False,
) -> list[Attribution]:
    """Return ordered RC attributions with confidence and evidence event IDs."""
    thr = thresholds or FlagThresholds()
    flags = evaluate_flags(timeline, thresholds=thr)
    by_rule = {f.rule_id: f for f in flags}
    out: list[Attribution] = []

    # Scenario-aware branch
    if ref_transcript is not None and hyp_transcript is not None:
        if wer is not None and wer >= 0.3:
            # High WER → entity/noise ASR
            code = "RC-ASR-ENT" if _looks_entity_heavy(ref_transcript) else "RC-ASR-NOISE"
            out.append(
                Attribution(
                    code=code,
                    confidence=0.7,
                    evidence_event_ids=tuple(e.event_id for e in timeline.events_of("stt.final")),
                    rationale=f"high WER={wer:.2f} vs reference",
                )
            )
        elif wer is not None and wer < 0.1:
            if slots_ref is not None and slots_hyp is not None and slots_ref != slots_hyp:
                out.append(
                    Attribution(
                        code="RC-LLM-SLOT",
                        confidence=0.75,
                        evidence_event_ids=tuple(
                            e.event_id for e in timeline.events_of("tool.call", "brain.done")
                        ),
                        rationale="transcript OK but slots mismatch",
                    )
                )
            elif (
                intent_ref
                and intent_hyp
                and intent_ref.strip().lower() != intent_hyp.strip().lower()
            ):
                out.append(
                    Attribution(
                        code="RC-LLM-INTENT",
                        confidence=0.75,
                        evidence_event_ids=tuple(
                            e.event_id for e in timeline.events_of("brain.done")
                        ),
                        rationale="transcript OK but intent mismatch",
                    )
                )
            elif unsupported_claim or "unsupported_claim" in by_rule:
                hit = by_rule.get("unsupported_claim")
                out.append(
                    Attribution(
                        code="RC-LLM-HALLU",
                        confidence=0.8,
                        evidence_event_ids=_ids_from_flags(hit) if hit else (),
                        rationale="unsupported claim with good transcript",
                    )
                )

    # Turn-taking
    for ev in timeline.events_of("endpoint.decided"):
        if ev.payload.get("vad_active") is True:
            out.append(
                Attribution(
                    code="RC-TURN-EARLY",
                    confidence=0.85,
                    evidence_event_ids=(ev.event_id,),
                    rationale="endpoint while VAD still active",
                )
            )
    if "dead_air" in by_rule:
        hit = by_rule["dead_air"]
        # Prefer SYS-LAT if brain_ttft large
        code = "RC-TURN-LATE"
        for e in timeline.events_of("brain.first_token"):
            if float(e.payload.get("ttft_ms") or 0) > 1500:
                code = "RC-SYS-LAT"
                break
        out.append(
            Attribution(
                code=code,
                confidence=0.7,
                evidence_event_ids=hit.evidence_event_ids,
                rationale=hit.reason,
            )
        )

    for barge in timeline.events_of("barge_in.detected"):
        applied = [
            e
            for e in timeline.events_of("barge_in.applied", "playback.stop")
            if e.t_ms >= barge.t_ms
        ]
        if not applied:
            out.append(
                Attribution(
                    code="RC-TURN-BARGE-MISS",
                    confidence=0.8,
                    evidence_event_ids=(barge.event_id,),
                    rationale="barge_in.detected without playback stop",
                )
            )
        elif barge.payload.get("caller_speech") is False:
            out.append(
                Attribution(
                    code="RC-TURN-BARGE-FALSE",
                    confidence=0.75,
                    evidence_event_ids=(barge.event_id,),
                    rationale="barge-in without caller speech on track",
                )
            )

    if "tool_error" in by_rule:
        hit = by_rule["tool_error"]
        out.append(
            Attribution(
                code="RC-TOOL-ERR",
                confidence=0.9,
                evidence_event_ids=hit.evidence_event_ids,
                rationale=hit.reason,
            )
        )
    if "policy_denied" in by_rule:
        hit = by_rule["policy_denied"]
        out.append(
            Attribution(
                code="RC-LLM-POLICY",
                confidence=0.85,
                evidence_event_ids=hit.evidence_event_ids,
                rationale=hit.reason,
            )
        )
    if "tool_arg_not_in_asr" in by_rule and not any(a.code == "RC-ASR-ENT" for a in out):
        hit = by_rule["tool_arg_not_in_asr"]
        out.append(
            Attribution(
                code="RC-TOOL-ARGS",
                confidence=0.65,
                evidence_event_ids=hit.evidence_event_ids,
                rationale=hit.reason,
            )
        )

    # Deduplicate by code keeping highest confidence
    best: dict[str, Attribution] = {}
    for a in out:
        prev = best.get(a.code)
        if prev is None or a.confidence > prev.confidence:
            best[a.code] = a
    return sorted(best.values(), key=lambda a: (-a.confidence, a.code))


def primary_attribution(attrs: list[Attribution]) -> Attribution | None:
    return attrs[0] if attrs else None


def _looks_entity_heavy(text: str) -> bool:
    import re

    return bool(re.search(r"\d{3,}|\b[A-Z][a-z]+\s+[A-Z][a-z]+\b|street|avenue|road", text, re.I))


__all__ = [
    "Attribution",
    "attribute_call",
    "primary_attribution",
]
