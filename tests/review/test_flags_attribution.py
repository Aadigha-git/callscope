"""Auto-flag rules and attribution (T-M4-01): positive + negative timelines."""

from __future__ import annotations

from uuid import uuid4

import pytest

from callscope.events.models import Event, EventSource
from callscope.review.attribution import attribute_call, primary_attribution
from callscope.review.flags import (
    AgentTalkOverCallerRule,
    BargeRestartScratchRule,
    CallerRepetitionRule,
    DeadAirRule,
    EarlyHangupRule,
    EvalFailureRule,
    FlagThresholds,
    LowAsrConfidenceRule,
    PolicyDeniedRule,
    ToolArgNotInAsrRule,
    ToolErrorRule,
    UnsupportedClaimRule,
    evaluate_flags,
)
from callscope.review.timeline import build_timeline

pytestmark = pytest.mark.unit

CALL = uuid4()
TURN = uuid4()


def _ev(type_: str, t_ms: int, payload: dict | None = None, turn_id=TURN) -> Event:
    return Event(
        call_id=CALL,
        turn_id=turn_id,
        t_ms=t_ms,
        source=EventSource.WORKER,
        type=type_,
        payload=payload or {},
    )


def test_timeline_builds_vad_span() -> None:
    tl = build_timeline(
        CALL,
        [
            _ev("vad.speech_start", 0),
            _ev("vad.speech_end", 500),
            _ev("stt.final", 600, {"text": "hi"}),
        ],
    )
    assert any(s.kind == "caller_vad" and s.t_end_ms == 500 for s in tl.spans)
    assert any(s.kind == "stt.final" for s in tl.spans)


def test_low_asr_confidence_pos_neg() -> None:
    thr = FlagThresholds(asr_confidence_min=0.55)
    rule = LowAsrConfidenceRule()
    pos = build_timeline(CALL, [_ev("stt.final", 1, {"text": "x", "avg_conf": 0.2})])
    neg = build_timeline(CALL, [_ev("stt.final", 1, {"text": "x", "avg_conf": 0.9})])
    assert rule.evaluate(pos, thr)
    assert not rule.evaluate(neg, thr)


def test_tool_arg_not_in_asr_pos_neg() -> None:
    thr = FlagThresholds()
    rule = ToolArgNotInAsrRule()
    pos = build_timeline(
        CALL,
        [
            _ev("stt.final", 1, {"text": "book friday"}),
            _ev("tool.call", 2, {"name": "book", "args": {"phone": "5551234567"}}),
        ],
    )
    neg = build_timeline(
        CALL,
        [
            _ev("stt.final", 1, {"text": "my phone is 5551234567"}),
            _ev("tool.call", 2, {"name": "book", "args": {"phone": "5551234567"}}),
        ],
    )
    assert rule.evaluate(pos, thr)
    assert not rule.evaluate(neg, thr)


def test_caller_repetition_pos_neg() -> None:
    thr = FlagThresholds()
    rule = CallerRepetitionRule()
    pos = build_timeline(CALL, [_ev("stt.final", 1, {"text": "sorry what"})])
    neg = build_timeline(CALL, [_ev("stt.final", 1, {"text": "book plumbing friday"})])
    assert rule.evaluate(pos, thr)
    assert not rule.evaluate(neg, thr)


def test_dead_air_pos_neg() -> None:
    thr = FlagThresholds(dead_air_ms=2000)
    rule = DeadAirRule()
    pos = build_timeline(
        CALL,
        [
            _ev("endpoint.decided", 0),
            _ev("brain.first_token", 3000),
        ],
    )
    neg = build_timeline(
        CALL,
        [
            _ev("endpoint.decided", 0),
            _ev("filler.played", 500),
            _ev("brain.first_token", 3000),
        ],
    )
    assert rule.evaluate(pos, thr)
    assert not rule.evaluate(neg, thr)


def test_agent_talk_over_caller_pos_neg() -> None:
    thr = FlagThresholds()
    rule = AgentTalkOverCallerRule()
    pos = build_timeline(
        CALL,
        [
            _ev("vad.speech_start", 0),
            _ev("playback.start", 100),
            _ev("vad.speech_end", 400),
        ],
    )
    neg = build_timeline(
        CALL,
        [
            _ev("vad.speech_start", 0),
            _ev("vad.speech_end", 100),
            _ev("playback.start", 200),
        ],
    )
    assert rule.evaluate(pos, thr)
    assert not rule.evaluate(neg, thr)


def test_barge_restart_pos_neg() -> None:
    thr = FlagThresholds()
    rule = BargeRestartScratchRule()
    pos = build_timeline(
        CALL,
        [
            _ev("barge_in.detected", 100),
            _ev("brain.request", 200, {}),
        ],
    )
    neg = build_timeline(
        CALL,
        [
            _ev("barge_in.detected", 100),
            _ev("brain.request", 200, {"resume_from_prefix": True}),
        ],
    )
    assert rule.evaluate(pos, thr)
    assert not rule.evaluate(neg, thr)


def test_policy_and_tool_error_pos_neg() -> None:
    thr = FlagThresholds()
    assert PolicyDeniedRule().evaluate(
        build_timeline(CALL, [_ev("policy.denied", 1, {"rule": "confirm"})]), thr
    )
    assert not PolicyDeniedRule().evaluate(build_timeline(CALL, [_ev("stt.final", 1, {})]), thr)
    assert ToolErrorRule().evaluate(
        build_timeline(CALL, [_ev("tool.result", 1, {"error": "timeout"})]), thr
    )
    assert not ToolErrorRule().evaluate(
        build_timeline(CALL, [_ev("tool.result", 1, {"status": "ok"})]), thr
    )


def test_unsupported_claim_and_eval_failure() -> None:
    thr = FlagThresholds()
    assert UnsupportedClaimRule().evaluate(
        build_timeline(CALL, [_ev("brain.done", 1, {"unsupported_claim": True})]), thr
    )
    assert EvalFailureRule().evaluate(
        build_timeline(CALL, [_ev("call.end", 1, {"task_success": False})]), thr
    )


def test_early_hangup_pos_neg() -> None:
    thr = FlagThresholds(hangup_after_agent_ms=10_000)
    rule = EarlyHangupRule()
    pos = build_timeline(
        CALL,
        [
            _ev("playback.start", 1000),
            _ev("call.end", 2000, {"reason": "client_end"}),
        ],
    )
    neg = build_timeline(
        CALL,
        [
            _ev("playback.start", 1000),
            _ev("call.end", 20_000, {"reason": "client_end"}),
        ],
    )
    assert rule.evaluate(pos, thr)
    assert not rule.evaluate(neg, thr)


def test_evaluate_flags_aggregates() -> None:
    tl = build_timeline(
        CALL,
        [
            _ev("stt.final", 1, {"text": "hi", "avg_conf": 0.1}),
            _ev("policy.denied", 2, {"rule": "x"}),
        ],
    )
    hits = evaluate_flags(tl)
    assert {h.rule_id for h in hits} >= {"low_asr_confidence", "policy_denied"}


def test_attribution_asr_ent_and_slot() -> None:
    tl = build_timeline(CALL, [_ev("stt.final", 1, {"text": "555"})])
    attrs = attribute_call(
        tl,
        ref_transcript="call 555-123-4567 please",
        hyp_transcript="call please",
        wer=0.5,
    )
    assert primary_attribution(attrs)
    assert primary_attribution(attrs).code in {"RC-ASR-ENT", "RC-ASR-NOISE"}

    attrs2 = attribute_call(
        tl,
        ref_transcript="book friday",
        hyp_transcript="book friday",
        wer=0.0,
        slots_ref={"day": "friday"},
        slots_hyp={"day": "monday"},
    )
    assert any(a.code == "RC-LLM-SLOT" for a in attrs2)


def test_attribution_turn_early_and_barge_miss() -> None:
    tl = build_timeline(
        CALL,
        [
            _ev("endpoint.decided", 100, {"vad_active": True}),
            _ev("barge_in.detected", 200),
        ],
    )
    attrs = attribute_call(tl)
    codes = {a.code for a in attrs}
    assert "RC-TURN-EARLY" in codes
    assert "RC-TURN-BARGE-MISS" in codes


def test_attribution_tool_err_and_false_barge() -> None:
    tl = build_timeline(
        CALL,
        [
            _ev("tool.result", 1, {"error": "boom"}),
            _ev("barge_in.detected", 2, {"caller_speech": False}),
            _ev("playback.stop", 3),
        ],
    )
    attrs = attribute_call(tl)
    codes = {a.code for a in attrs}
    assert "RC-TOOL-ERR" in codes
    assert "RC-TURN-BARGE-FALSE" in codes
