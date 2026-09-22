"""LiveKit Agents STT/TTS/LLM adapters over CallScope providers (real demo path).

Verified against livekit-agents 1.8.2 APIs used by spikes/T-M0-05 stubs.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

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
from livekit.agents.utils.audio import AudioBuffer, combine_frames

from callscope.providers.asr_client import ASRClient
from callscope.providers.tts_client import TTSClient


class CallScopeSTT(STT):
    """Batch STT via CallScope ASR HTTP ``/v1/transcribe`` (pair with StreamAdapter+VAD)."""

    def __init__(self, *, base_url: str | None = None) -> None:
        super().__init__(
            capabilities=STTCapabilities(streaming=False, interim_results=False),
        )
        self._client = ASRClient(
            base_url or os.environ.get("CALLSCOPE_ASR_URL", "http://127.0.0.1:8200")
        )

    async def _recognize_impl(
        self,
        buffer: AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> SpeechEvent:
        _ = conn_options
        frame = combine_frames(buffer)
        wav = frame.to_wav_bytes()
        transcript = await self._client.transcribe(wav, sample_rate=int(frame.sample_rate))
        lang = language if isinstance(language, str) else "en"
        return SpeechEvent(
            type=SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[
                SpeechData(text=transcript.text or "", language=LanguageCode(lang)),
            ],
        )


class CallScopeTTS(TTS):
    """Streaming TTS via CallScope TTS HTTP ``/v1/tts/stream``."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        sample_rate: int = 24_000,
        voice: str | None = None,
    ) -> None:
        super().__init__(
            capabilities=TTSCapabilities(streaming=True),
            sample_rate=sample_rate,
            num_channels=1,
        )
        self._client = TTSClient(
            base_url or os.environ.get("CALLSCOPE_TTS_URL", "http://127.0.0.1:8300"),
            sample_rate=sample_rate,
            default_voice=voice or os.environ.get("CALLSCOPE_TTS_VOICE", "en_US-lessac-medium"),
        )
        self._voice = self._client._default_voice

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> ChunkedStream:
        return _CallScopeChunkedStream(tts=self, input_text=text, conn_options=conn_options)

    def stream(
        self, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> SynthesizeStream:
        return _CallScopeSynthesizeStream(tts=self, conn_options=conn_options)


class _CallScopeChunkedStream(ChunkedStream):
    async def _run(self, output_emitter: AudioEmitter) -> None:
        assert isinstance(self._tts, CallScopeTTS)
        output_emitter.initialize(
            request_id=utils.shortuuid("cs_tts_"),
            sample_rate=self._tts.sample_rate,
            num_channels=self._tts.num_channels,
            mime_type="audio/pcm",
        )
        async for chunk in self._tts._client.stream(
            self._input_text, voice=self._tts._voice, speed=1.0
        ):
            # Prefer server-reported sample rate if client updated it mid-stream.
            if self._tts._client.sample_rate != self._tts.sample_rate:
                self._tts.sample_rate = self._tts._client.sample_rate
            output_emitter.push(chunk)
            await asyncio.sleep(0)
        output_emitter.flush()


class _CallScopeSynthesizeStream(SynthesizeStream):
    async def _run(self, output_emitter: AudioEmitter) -> None:
        assert isinstance(self._tts, CallScopeTTS)
        output_emitter.initialize(
            request_id=utils.shortuuid("cs_tts_"),
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
            output_emitter.start_segment(segment_id=utils.shortuuid("cs_seg_"))
            async for chunk in self._tts._client.stream(text, voice=self._tts._voice, speed=1.0):
                output_emitter.push(chunk)
                await asyncio.sleep(0)
            output_emitter.flush()
            output_emitter.end_segment()


class TokenFactoryLLM(LLM):
    """OpenAI-compatible chat against Nebius Token Factory (no Hermes required for demo)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        super().__init__()
        self._api_key = (
            api_key
            or os.environ.get("TOKEN_FACTORY_API_KEY")
            or os.environ.get("NEBIUS_API_KEY", "")
        )
        self._base_url = (
            base_url
            or os.environ.get("TOKEN_FACTORY_BASE_URL")
            or "https://api.tokenfactory.nebius.com/v1/"
        )
        self._model = model or os.environ.get(
            "TOKEN_FACTORY_MODEL", "nvidia/Nemotron-3_5-Lightning"
        )

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
        _ = (parallel_tool_calls, tool_choice, extra_kwargs)
        return _TokenFactoryStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )


class _TokenFactoryStream(LLMStream):
    def __init__(
        self,
        llm_inst: TokenFactoryLLM,
        *,
        chat_ctx: ChatContext,
        tools: list[Tool],
        conn_options: APIConnectOptions,
    ) -> None:
        super().__init__(llm_inst, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._llm = llm_inst

    async def _run(self) -> None:
        if not self._llm._api_key:
            raise RuntimeError("TOKEN_FACTORY_API_KEY is required for live LLM (set in .env)")
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=self._llm._api_key, base_url=self._llm._base_url)
        messages = _chat_ctx_to_openai(self.chat_ctx)
        stream = await client.chat.completions.create(
            model=self._llm._model,
            messages=messages,
            stream=True,
            temperature=0.3,
        )
        async for event in stream:
            choice = event.choices[0] if event.choices else None
            if choice is None or choice.delta is None:
                continue
            content = choice.delta.content
            if not content:
                continue
            self._event_ch.send_nowait(
                ChatChunk(
                    id=str(event.id or id(self)),
                    delta=ChoiceDelta(role="assistant", content=content),
                )
            )


def _chat_ctx_to_openai(chat_ctx: ChatContext) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in chat_ctx.items:
        if getattr(item, "type", None) != "message":
            continue
        role = str(getattr(item, "role", "user") or "user")
        if role == "developer":
            role = "system"
        text = getattr(item, "text_content", None)
        if not text:
            continue
        out.append({"role": role, "content": str(text)})
    if not out:
        out.append(
            {
                "role": "system",
                "content": (
                    "You are the CallScope Lakeside fictional receptionist. "
                    "Keep replies short. Do not use markdown. Fictional data only."
                ),
            }
        )
    return out


__all__ = ["CallScopeSTT", "CallScopeTTS", "TokenFactoryLLM"]
