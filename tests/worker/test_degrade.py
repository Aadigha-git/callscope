"""Degradation matrix unit tests (design §4.11)."""

from __future__ import annotations

from apps.worker.degrade import DegradeAction, DegradeController, FailureKind


def test_asr_ends_after_two_failures() -> None:
    d = DegradeController()
    first = d.record(FailureKind.ASR)
    assert first.action is DegradeAction.ANNOUNCE
    assert first.end_reason is None
    second = d.record(FailureKind.ASR)
    assert second.action is DegradeAction.END_CALL
    assert second.end_reason == "asr_error"


def test_brain_handoff_after_two() -> None:
    d = DegradeController()
    assert d.record(FailureKind.BRAIN).action is DegradeAction.ANNOUNCE
    assert d.record(FailureKind.BRAIN).action is DegradeAction.HANDOFF


def test_tool_callback_after_two() -> None:
    d = DegradeController()
    assert d.record(FailureKind.TOOL).action is DegradeAction.CONTINUE
    assert d.record(FailureKind.TOOL).action is DegradeAction.OFFER_CALLBACK


def test_biz_offers_callback() -> None:
    d = DegradeController()
    dec = d.record(FailureKind.BIZ)
    assert dec.action is DegradeAction.OFFER_CALLBACK
    assert "callback" in dec.spoken_notice.lower()


def test_tts_text_only() -> None:
    d = DegradeController()
    dec = d.record(FailureKind.TTS)
    assert dec.action is DegradeAction.TEXT_ONLY


def test_events_buffer() -> None:
    d = DegradeController()
    dec = d.record(FailureKind.EVENTS)
    assert dec.action is DegradeAction.BUFFER_EVENTS
