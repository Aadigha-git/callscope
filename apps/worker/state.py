"""Pure turn state machine (design §4.2). No LiveKit / provider imports."""

from __future__ import annotations

from enum import StrEnum


class TurnState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ENDED = "ended"


class TurnEvent(StrEnum):
    CALL_CONNECTED = "call_connected"
    GREETING_DONE = "greeting_done"
    ENDPOINT_FINAL = "endpoint_final"
    EMPTY_TRANSCRIPT = "empty_transcript"
    FIRST_AUDIO = "first_audio"
    REPLY_COMPLETE = "reply_complete"
    BARGE_IN = "barge_in"
    CALL_END = "call_end"
    TIMEOUT = "timeout"
    ERROR = "error"


class InvalidTransition(Exception):
    """Raised when an event is not legal in the current state."""

    def __init__(self, state: TurnState, event: TurnEvent) -> None:
        self.state = state
        self.event = event
        super().__init__(f"invalid transition: {state.value} + {event.value}")


# (state, event) -> new_state
_TRANSITIONS: dict[tuple[TurnState, TurnEvent], TurnState] = {
    (TurnState.IDLE, TurnEvent.CALL_CONNECTED): TurnState.LISTENING,
    (TurnState.IDLE, TurnEvent.GREETING_DONE): TurnState.LISTENING,
    (TurnState.IDLE, TurnEvent.CALL_END): TurnState.ENDED,
    (TurnState.IDLE, TurnEvent.TIMEOUT): TurnState.ENDED,
    (TurnState.IDLE, TurnEvent.ERROR): TurnState.ENDED,
    (TurnState.LISTENING, TurnEvent.ENDPOINT_FINAL): TurnState.THINKING,
    (TurnState.LISTENING, TurnEvent.EMPTY_TRANSCRIPT): TurnState.LISTENING,
    (TurnState.LISTENING, TurnEvent.CALL_END): TurnState.ENDED,
    (TurnState.LISTENING, TurnEvent.TIMEOUT): TurnState.ENDED,
    (TurnState.LISTENING, TurnEvent.ERROR): TurnState.ENDED,
    (TurnState.THINKING, TurnEvent.FIRST_AUDIO): TurnState.SPEAKING,
    (TurnState.THINKING, TurnEvent.BARGE_IN): TurnState.LISTENING,
    (TurnState.THINKING, TurnEvent.REPLY_COMPLETE): TurnState.LISTENING,
    (TurnState.THINKING, TurnEvent.CALL_END): TurnState.ENDED,
    (TurnState.THINKING, TurnEvent.TIMEOUT): TurnState.ENDED,
    (TurnState.THINKING, TurnEvent.ERROR): TurnState.ENDED,
    (TurnState.SPEAKING, TurnEvent.BARGE_IN): TurnState.LISTENING,
    (TurnState.SPEAKING, TurnEvent.REPLY_COMPLETE): TurnState.LISTENING,
    (TurnState.SPEAKING, TurnEvent.CALL_END): TurnState.ENDED,
    (TurnState.SPEAKING, TurnEvent.TIMEOUT): TurnState.ENDED,
    (TurnState.SPEAKING, TurnEvent.ERROR): TurnState.ENDED,
}


class TurnStateMachine:
    """Explicit turn FSM. ``ENDED`` is terminal."""

    def __init__(self, *, initial: TurnState = TurnState.IDLE) -> None:
        self._state = initial
        self.history: list[tuple[TurnState, TurnEvent, TurnState]] = []

    @property
    def state(self) -> TurnState:
        return self._state

    @property
    def ended(self) -> bool:
        return self._state is TurnState.ENDED

    def handle(self, event: TurnEvent) -> TurnState:
        if self._state is TurnState.ENDED:
            raise InvalidTransition(self._state, event)
        key = (self._state, event)
        if key not in _TRANSITIONS:
            raise InvalidTransition(self._state, event)
        nxt = _TRANSITIONS[key]
        self.history.append((self._state, event, nxt))
        self._state = nxt
        return nxt

    def can(self, event: TurnEvent) -> bool:
        if self._state is TurnState.ENDED:
            return False
        return (self._state, event) in _TRANSITIONS
