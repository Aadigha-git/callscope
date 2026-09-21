"""Per-call orchestration (design §4.2). No LiveKit imports."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import UUID

from apps.worker.config import WorkerConfig
from apps.worker.state import TurnEvent, TurnState, TurnStateMachine
from callscope.events.clock import CallClock
from callscope.events.models import Event, EventSource
from callscope.events.writer import EventWriter
from callscope.norm.chunker import SentenceChunker
from callscope.norm.tts_norm import tts_norm
from callscope.observability import metrics
from callscope.providers.base import (
    BrainBackend,
    BrainDelta,
    Msg,
    ProviderError,
    ProviderTimeout,
    STTEvent,
    STTProvider,
    TTSProvider,
)

logger = logging.getLogger(__name__)

DataPublisher = Callable[[dict[str, Any]], Awaitable[None]]
PcmPublisher = Callable[[bytes], Awaitable[None]]


class MediaBridge(Protocol):
    """Outbound media/data toward the caller (LiveKit or test double)."""

    async def publish_pcm(self, pcm: bytes) -> None: ...

    async def publish_data(self, message: dict[str, Any]) -> None: ...


@dataclass
class NullMedia:
    frames: list[bytes] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)

    async def publish_pcm(self, pcm: bytes) -> None:
        self.frames.append(pcm)

    async def publish_data(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


class CallSession:
    """One live call: STT → brain → chunker → TTS → events + data channel."""

    def __init__(
        self,
        *,
        call_id: UUID,
        stt: STTProvider,
        tts: TTSProvider,
        brain: BrainBackend,
        writer: EventWriter,
        clock: CallClock,
        config: WorkerConfig | None = None,
        media: MediaBridge | None = None,
        stack_version_id: str | None = None,
        system_prompt: str = "You are a helpful receptionist. Keep replies short.",
    ) -> None:
        self.call_id = call_id
        self._stt = stt
        self._tts = tts
        self._brain = brain
        self._writer = writer
        self._clock = clock
        self._config = config or WorkerConfig()
        self._media: MediaBridge = media or NullMedia()
        self._stack_version_id = stack_version_id
        self._system_prompt = system_prompt
        self.sm = TurnStateMachine()
        self.history: list[Msg] = [Msg(role="system", content=system_prompt)]
        self.end_reason: str | None = None
        self._active_turn_id: UUID | None = None
        self._spoken_prefix = ""
        self._interruption_note: str | None = None
        self._speech_end_t_ms: int | None = None
        self._first_audio_observed = False
        self._metrics_active = False

    @property
    def state(self) -> TurnState:
        return self.sm.state

    def _emit(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        *,
        turn_id: UUID | None = None,
    ) -> None:
        self._writer.emit(
            Event(
                call_id=self.call_id,
                turn_id=turn_id if turn_id is not None else self._active_turn_id,
                t_ms=self._clock.t_ms(),
                source=EventSource.WORKER,
                type=event_type,
                payload=payload or {},
            )
        )

    async def _data(self, message: dict[str, Any]) -> None:
        await self._media.publish_data(message)

    async def _set_agent_state(self, state: TurnState) -> None:
        await self._data({"type": "agent.state", "state": state.value})

    async def start(self) -> None:
        if not self._clock.started:
            self._clock.start()
        metrics.ACTIVE_CALLS.inc()
        self._metrics_active = True
        self._emit(
            "call.start",
            {
                "channel": "web",
                "stack_version_id": self._stack_version_id,
            },
        )
        await self._data({"type": "notice", "code": "recording_on", "text": "Recording on"})

    async def run_greeting(self) -> None:
        """Speak the greeting while IDLE, then enter LISTENING."""
        text = self._config.greeting_text.strip()
        if not text:
            self.sm.handle(TurnEvent.GREETING_DONE)
            await self._set_agent_state(TurnState.LISTENING)
            return
        await self._speak_text(text, turn_id=None, mark_speaking=False)
        self.history.append(Msg(role="assistant", content=text))
        self.sm.handle(TurnEvent.GREETING_DONE)
        await self._set_agent_state(TurnState.LISTENING)

    async def connect(self) -> None:
        """Mark call connected without a separate greeting (tests / headless)."""
        self.sm.handle(TurnEvent.CALL_CONNECTED)
        await self._set_agent_state(TurnState.LISTENING)

    async def process_pcm(self, pcm: AsyncIterator[bytes]) -> None:
        """Stream mic PCM through STT until finals are handled or session ends."""
        try:
            async for ev in self._stt.stream(
                pcm,
                sample_rate=self._config.sample_rate,
                hotwords=self._config.hotwords or None,
            ):
                if self.sm.ended:
                    break
                if self._timed_out():
                    reason = "silence_timeout" if self._silence_timed_out() else "max_duration"
                    await self.end(reason)
                    break
                await self._on_stt_event(ev)
        except ProviderError as exc:
            metrics.PROVIDER_ERRORS.labels(stage="asr").inc()
            self._emit(
                "provider.error",
                {"stage": "asr", "code": type(exc).__name__, "retryable": False},
            )
            await self._data({"type": "error", "code": "asr_error"})
            await self.end("asr_error")

    async def _on_stt_event(self, ev: STTEvent) -> None:
        if ev.kind == "partial":
            self._emit("stt.partial", {"text": ev.text})
            await self._data({"type": "transcript.partial", "text": ev.text})
            return
        # final
        self._speech_end_t_ms = self._clock.t_ms()
        self._emit(
            "endpoint.decided",
            {"silence_ms": int(self._config.endpoint_min_delay_s * 1000), "reason": "silence"},
        )
        self._emit(
            "stt.final",
            {
                "text": ev.text,
                "avg_conf": ev.avg_conf,
                "words": [
                    {"w": w.word, "start_ms": w.start_ms, "end_ms": w.end_ms, "conf": w.conf}
                    for w in ev.words
                ],
                "audio_ms": ev.t_end_ms,
            },
        )
        await self._data({"type": "transcript.final", "text": ev.text})
        if ev.avg_conf is not None:
            metrics.ASR_CONFIDENCE.observe(float(ev.avg_conf))
        await self.handle_final_transcript(ev.text)

    async def handle_final_transcript(self, text: str) -> None:
        if self.sm.ended:
            return
        if not text.strip():
            self.sm.handle(TurnEvent.EMPTY_TRANSCRIPT)
            return
        if self.sm.state is TurnState.IDLE:
            self.sm.handle(TurnEvent.CALL_CONNECTED)
        turn_id = uuid.uuid4()
        self._active_turn_id = turn_id
        self._spoken_prefix = ""
        self._first_audio_observed = False
        self.sm.handle(TurnEvent.ENDPOINT_FINAL)
        await self._set_agent_state(TurnState.THINKING)
        self.history.append(Msg(role="user", content=text.strip()))
        await self._run_brain_turn(turn_id)

    async def _run_brain_turn(self, turn_id: UUID) -> None:
        chunker = SentenceChunker(min_chars=self._config.chunker_min_chars)
        spoken_parts: list[str] = []
        got_token = False
        t_brain0 = self._clock.t_ms()
        self._emit("brain.request", {"messages": len(self.history)}, turn_id=turn_id)
        try:
            stream = self._brain_stream(self.history, turn_id=turn_id)
            async for delta in stream:
                if self.sm.ended or self.sm.state is TurnState.LISTENING:
                    # barge-in moved us back
                    break
                if delta.kind == "text" and delta.text:
                    if not got_token:
                        got_token = True
                        metrics.observe_stage(
                            "brain_ttft", (self._clock.t_ms() - t_brain0) / 1000.0
                        )
                        self._emit(
                            "brain.first_token",
                            {"ttft_ms": self._clock.t_ms() - t_brain0},
                            turn_id=turn_id,
                        )
                    chunker.push(delta.text)
                    for sentence in chunker.ready():
                        await self._speak_sentence(sentence, turn_id=turn_id)
                        spoken_parts.append(sentence)
                elif delta.kind == "done":
                    break
            for sentence in chunker.flush():
                await self._speak_sentence(sentence, turn_id=turn_id)
                spoken_parts.append(sentence)
            self._emit("brain.done", {}, turn_id=turn_id)
        except ProviderTimeout as exc:
            metrics.PROVIDER_ERRORS.labels(stage="brain").inc()
            self._emit(
                "provider.error",
                {"stage": "brain", "code": "timeout", "retryable": True, "detail": str(exc)},
                turn_id=turn_id,
            )
            await self._data({"type": "error", "code": "brain_timeout"})
            await self.end("brain_timeout")
            return
        except ProviderError as exc:
            metrics.PROVIDER_ERRORS.labels(stage="brain").inc()
            self._emit(
                "provider.error",
                {"stage": "brain", "code": type(exc).__name__, "retryable": False},
                turn_id=turn_id,
            )
            await self._data({"type": "error", "code": "brain_error"})
            await self.end("brain_error")
            return

        spoken = " ".join(spoken_parts).strip()
        if spoken:
            self.history.append(Msg(role="assistant", content=spoken))
            await self._data({"type": "agent.text", "text": spoken})
        if self.sm.state in {TurnState.THINKING, TurnState.SPEAKING}:
            self.sm.handle(TurnEvent.REPLY_COMPLETE)
            self._emit("playback.stop", {"reason": "complete"}, turn_id=turn_id)
            await self._set_agent_state(TurnState.LISTENING)
        self._active_turn_id = None
        self._interruption_note = None

    def _brain_stream(self, messages: Sequence[Msg], *, turn_id: UUID) -> AsyncIterator[BrainDelta]:
        # Prefer interruption_note when the backend supports it (HermesBackend).
        stream_reply = self._brain.stream_reply
        try:
            return stream_reply(
                list(messages),
                call_id=str(self.call_id),
                turn_id=str(turn_id),
                interruption_note=self._interruption_note,  # type: ignore[call-arg]
            )
        except TypeError:
            return stream_reply(
                list(messages),
                call_id=str(self.call_id),
                turn_id=str(turn_id),
            )

    async def _speak_sentence(self, sentence: str, *, turn_id: UUID) -> None:
        await self._speak_text(sentence, turn_id=turn_id, mark_speaking=True)

    async def _speak_text(
        self,
        text: str,
        *,
        turn_id: UUID | None,
        mark_speaking: bool,
    ) -> None:
        spoken = tts_norm(text)
        if not spoken.strip():
            return
        self._emit(
            "tts.request",
            {"chars": len(spoken), "voice": self._config.tts_voice},
            turn_id=turn_id,
        )
        t0 = self._clock.t_ms()
        first = True
        try:
            async for pcm in self._tts.stream(
                spoken, voice=self._config.tts_voice, speed=self._config.tts_speed
            ):
                if first:
                    first = False
                    ttfb = (self._clock.t_ms() - t0) / 1000.0
                    metrics.observe_stage("tts_ttfb", ttfb)
                    self._emit(
                        "tts.first_audio",
                        {"ttfb_ms": self._clock.t_ms() - t0},
                        turn_id=turn_id,
                    )
                    if mark_speaking and self.sm.state is TurnState.THINKING:
                        self.sm.handle(TurnEvent.FIRST_AUDIO)
                        self._emit("playback.start", {"reason": "reply"}, turn_id=turn_id)
                        await self._set_agent_state(TurnState.SPEAKING)
                    if (
                        mark_speaking
                        and not self._first_audio_observed
                        and self._speech_end_t_ms is not None
                    ):
                        self._first_audio_observed = True
                        latency_s = (self._clock.t_ms() - self._speech_end_t_ms) / 1000.0
                        metrics.RESPONSE_LATENCY.observe(latency_s)
                await self._media.publish_pcm(pcm)
            self._spoken_prefix = (self._spoken_prefix + " " + spoken).strip()
        except ProviderError as exc:
            metrics.PROVIDER_ERRORS.labels(stage="tts").inc()
            self._emit(
                "provider.error",
                {"stage": "tts", "code": type(exc).__name__, "retryable": False},
                turn_id=turn_id,
            )
            await self._data({"type": "error", "code": "tts_error"})
            await self.end("tts_error")
            return

    async def interrupt(self) -> None:
        """Barge-in hook (full VAD path is T-M2-05): cancel brain/TTS and return to LISTENING."""
        if not self.sm.can(TurnEvent.BARGE_IN):
            return
        turn_id = self._active_turn_id
        if turn_id is not None:
            await self._brain.cancel(str(turn_id))
        cancel = getattr(self._tts, "request_cancel", None)
        if callable(cancel):
            cancel()
        prefix = self._spoken_prefix
        self._interruption_note = (
            f"The caller interrupted; you had said: {prefix}. The rest was not heard."
            if prefix
            else "The caller interrupted before you spoke."
        )
        self.sm.handle(TurnEvent.BARGE_IN)
        self._emit(
            "barge_in.applied",
            {"spoken_prefix_chars": len(prefix)},
            turn_id=turn_id,
        )
        self._emit("playback.stop", {"reason": "barge_in"}, turn_id=turn_id)
        if prefix:
            self.history.append(Msg(role="assistant", content=prefix))
        await self._set_agent_state(TurnState.LISTENING)

    def _timed_out(self) -> bool:
        if not self._clock.started:
            return False
        t_s = self._clock.t_ms() / 1000.0
        return t_s >= self._config.call_max_duration_s or self._silence_timed_out()

    def _silence_timed_out(self) -> bool:
        # Simplified: if listening and call age exceeds silence timeout from last speech.
        if self.sm.state is not TurnState.LISTENING:
            return False
        t_ms = self._clock.t_ms()
        anchor = self._speech_end_t_ms if self._speech_end_t_ms is not None else 0
        return (t_ms - anchor) >= int(self._config.call_silence_timeout_s * 1000)

    async def end(self, reason: str) -> None:
        if self.end_reason is not None:
            return
        self.end_reason = reason
        if not self.sm.ended:
            event = (
                TurnEvent.TIMEOUT
                if reason in {"silence_timeout", "max_duration"}
                else TurnEvent.CALL_END
            )
            if reason in {"asr_error", "brain_error", "brain_timeout", "tts_error"}:
                event = TurnEvent.ERROR if self.sm.can(TurnEvent.ERROR) else TurnEvent.CALL_END
            if self.sm.can(event):
                self.sm.handle(event)
            elif self.sm.can(TurnEvent.CALL_END):
                self.sm.handle(TurnEvent.CALL_END)
        duration_ms = self._clock.t_ms() if self._clock.started else 0
        self._emit(
            "call.end",
            {"end_reason": reason, "duration_ms": duration_ms},
        )
        if self._metrics_active:
            metrics.ACTIVE_CALLS.dec()
            self._metrics_active = False
        metrics.CALLS_TOTAL.labels(end_reason=reason).inc()
        await self._writer.aclose()
