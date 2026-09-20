"""Stub STT / LLM / TTS for LiveKit Agents — verified against livekit-agents 1.8.2."""

from __future__ import annotations

import asyncio
import math
from typing import Any

import numpy as np
from livekit.agents import LanguageCode, utils
from livekit.agents.llm import (
    LLM,
    ChatChunk,
    ChatContext,
    ChoiceDelta,
    LLMStream,
    Tool,
    ToolChoice,
)
from livekit.agents.stt import (
    STT,
    SpeechData,
    SpeechEvent,
    SpeechEventType,
    STTCapabilities,
)
from livekit.agents.tts import (
    TTS,
    AudioEmitter,
    ChunkedStream,
    SynthesizeStream,
    TTSCapabilities,
)
from livekit.agents.types import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    APIConnectOptions,
    NotGivenOr,
)
from livekit.agents.utils.audio import AudioBuffer

SAMPLE_RATE = 24000


class EchoSTT(STT):
    """Non-streaming batch STT: any audio segment → fixed transcript (echo stub).

    Pair with ``livekit.agents.stt.StreamAdapter`` + Silero VAD for streaming.
    """

    def __init__(self, *, transcript: str = "hello from caller") -> None:
        super().__init__(
            capabilities=STTCapabilities(streaming=False, interim_results=False),
        )
        self._transcript = transcript

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> SpeechEvent:
        lang = language if isinstance(language, str) else "en"
        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                SpeechData(text=self._transcript, language=LanguageCode(lang)),
            ],
        )


class CannedLLM(LLM):
    """Deterministic replies for spike demos (no network)."""

    def __init__(self, *, reply: str | None = None) -> None:
        super().__init__()
        self._reply = reply

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[Tool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> LLMStream:
        return _CannedLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            reply=self._reply,
        )


class _CannedLLMStream(LLMStream):
    def __init__(
        self,
        llm: CannedLLM,
        *,
        chat_ctx: ChatContext,
        tools: list[Tool],
        conn_options: APIConnectOptions,
        reply: str | None,
    ) -> None:
        super().__init__(llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._reply = reply

    async def _run(self) -> None:
        user_text = _last_user_text(self.chat_ctx)
        content = self._reply
        if content is None:
            if user_text:
                content = (
                    f"Stub agent heard: {user_text}. This is CallScope spike T-M0-05."
                )
            else:
                # generate_reply(instructions=...) lands as a system/developer message.
                content = "Hello from the CallScope stub agent. How can I help?"
        await asyncio.sleep(0.05)
        # Stream in small chunks like a real LLM.
        chunk_size = 12
        for i in range(0, len(content), chunk_size):
            delta = content[i : i + chunk_size]
            self._event_ch.send_nowait(
                ChatChunk(
                    id=str(id(self)),
                    delta=ChoiceDelta(role="assistant", content=delta),
                )
            )
            await asyncio.sleep(0.01)


def _last_user_text(chat_ctx: ChatContext) -> str:
    for item in reversed(chat_ctx.items):
        if getattr(item, "type", None) == "message" and getattr(item, "role", None) == "user":
            text = getattr(item, "text_content", None)
            if text:
                return str(text)
    return ""


class SineTTS(TTS):
    """Audible sine PCM proportional to text length (stub voice)."""

    def __init__(self, *, sample_rate: int = SAMPLE_RATE, hz: float = 440.0) -> None:
        super().__init__(
            capabilities=TTSCapabilities(streaming=True),
            sample_rate=sample_rate,
            num_channels=1,
        )
        self._hz = hz

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> ChunkedStream:
        return _SineChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    def stream(
        self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> SynthesizeStream:
        return _SineSynthesizeStream(tts=self, conn_options=conn_options)


def _sine_pcm(duration_s: float, *, sample_rate: int, hz: float) -> bytes:
    n = max(1, int(sample_rate * duration_s))
    t = np.arange(n, dtype=np.float32) / float(sample_rate)
    # Soft envelope to avoid clicks.
    wave = 0.2 * np.sin(2.0 * math.pi * hz * t)
    if n > 64:
        env = np.ones(n, dtype=np.float32)
        env[:32] = np.linspace(0.0, 1.0, 32, dtype=np.float32)
        env[-32:] = np.linspace(1.0, 0.0, 32, dtype=np.float32)
        wave *= env
    samples = (wave * 32767.0).astype(np.int16)
    return samples.tobytes()


def _duration_for_text(text: str) -> float:
    # ~12 chars/sec spoken estimate; clamp for barge-in demos.
    return max(0.6, min(4.0, len(text) / 12.0))


class _SineChunkedStream(ChunkedStream):
    async def _run(self, output_emitter: AudioEmitter) -> None:
        assert isinstance(self._tts, SineTTS)
        output_emitter.initialize(
            request_id=utils.shortuuid("sine_tts_"),
            sample_rate=self._tts.sample_rate,
            num_channels=self._tts.num_channels,
            mime_type="audio/pcm",
        )
        await asyncio.sleep(0.03)  # tiny TTFB
        pcm = _sine_pcm(
            _duration_for_text(self._input_text),
            sample_rate=self._tts.sample_rate,
            hz=self._tts._hz,
        )
        # Push in ~20 ms frames.
        frame_bytes = self._tts.sample_rate // 50 * 2
        for i in range(0, len(pcm), frame_bytes):
            output_emitter.push(pcm[i : i + frame_bytes])
            await asyncio.sleep(0)
        output_emitter.flush()


class _SineSynthesizeStream(SynthesizeStream):
    async def _run(self, output_emitter: AudioEmitter) -> None:
        assert isinstance(self._tts, SineTTS)
        output_emitter.initialize(
            request_id=utils.shortuuid("sine_tts_"),
            sample_rate=self._tts.sample_rate,
            num_channels=self._tts.num_channels,
            mime_type="audio/pcm",
            stream=True,
        )
        buf = ""
        async for data in self._input_ch:
            if isinstance(data, str):
                buf += data
                continue
            if isinstance(data, SynthesizeStream._FlushSentinel) and not buf:
                continue
            text = buf
            buf = ""
            if not text.strip():
                continue
            self._mark_started()
            output_emitter.start_segment(segment_id=utils.shortuuid("sine_seg_"))
            await asyncio.sleep(0.03)
            pcm = _sine_pcm(
                _duration_for_text(text),
                sample_rate=self._tts.sample_rate,
                hz=self._tts._hz,
            )
            frame_bytes = self._tts.sample_rate // 50 * 2
            for i in range(0, len(pcm), frame_bytes):
                output_emitter.push(pcm[i : i + frame_bytes])
                await asyncio.sleep(0)
            output_emitter.flush()
