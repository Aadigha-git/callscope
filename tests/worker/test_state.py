"""TurnStateMachine transition coverage (design §4.2)."""

from __future__ import annotations

import pytest

from apps.worker.state import InvalidTransition, TurnEvent, TurnState, TurnStateMachine


def test_happy_path_two_turns() -> None:
    sm = TurnStateMachine()
    assert sm.state is TurnState.IDLE
    sm.handle(TurnEvent.GREETING_DONE)
    assert sm.state is TurnState.LISTENING
    sm.handle(TurnEvent.ENDPOINT_FINAL)
    assert sm.state is TurnState.THINKING
    sm.handle(TurnEvent.FIRST_AUDIO)
    assert sm.state is TurnState.SPEAKING
    sm.handle(TurnEvent.REPLY_COMPLETE)
    assert sm.state is TurnState.LISTENING
    sm.handle(TurnEvent.ENDPOINT_FINAL)
    sm.handle(TurnEvent.REPLY_COMPLETE)  # empty brain → listening without audio
    assert sm.state is TurnState.LISTENING
    sm.handle(TurnEvent.CALL_END)
    assert sm.ended


def test_empty_transcript_stays_listening() -> None:
    sm = TurnStateMachine()
    sm.handle(TurnEvent.CALL_CONNECTED)
    sm.handle(TurnEvent.EMPTY_TRANSCRIPT)
    assert sm.state is TurnState.LISTENING
    assert sm.history[-1] == (TurnState.LISTENING, TurnEvent.EMPTY_TRANSCRIPT, TurnState.LISTENING)


def test_barge_in_from_thinking_and_speaking() -> None:
    sm = TurnStateMachine()
    sm.handle(TurnEvent.CALL_CONNECTED)
    sm.handle(TurnEvent.ENDPOINT_FINAL)
    sm.handle(TurnEvent.BARGE_IN)
    assert sm.state is TurnState.LISTENING
    sm.handle(TurnEvent.ENDPOINT_FINAL)
    sm.handle(TurnEvent.FIRST_AUDIO)
    sm.handle(TurnEvent.BARGE_IN)
    assert sm.state is TurnState.LISTENING


def test_silence_and_max_timeout() -> None:
    sm = TurnStateMachine()
    sm.handle(TurnEvent.CALL_CONNECTED)
    sm.handle(TurnEvent.TIMEOUT)
    assert sm.ended

    sm2 = TurnStateMachine()
    sm2.handle(TurnEvent.CALL_CONNECTED)
    sm2.handle(TurnEvent.ENDPOINT_FINAL)
    sm2.handle(TurnEvent.TIMEOUT)
    assert sm2.ended


def test_error_paths() -> None:
    sm = TurnStateMachine()
    sm.handle(TurnEvent.CALL_CONNECTED)
    sm.handle(TurnEvent.ENDPOINT_FINAL)
    sm.handle(TurnEvent.ERROR)
    assert sm.ended


def test_invalid_transition() -> None:
    sm = TurnStateMachine()
    with pytest.raises(InvalidTransition):
        sm.handle(TurnEvent.FIRST_AUDIO)
    sm.handle(TurnEvent.CALL_END)
    with pytest.raises(InvalidTransition):
        sm.handle(TurnEvent.CALL_CONNECTED)


def test_can() -> None:
    sm = TurnStateMachine()
    assert sm.can(TurnEvent.GREETING_DONE)
    assert not sm.can(TurnEvent.FIRST_AUDIO)
