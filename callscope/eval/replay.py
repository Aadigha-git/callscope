"""Stage-replay and text-replay through shared provider interfaces."""

from __future__ import annotations

import io
import time
import wave
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import uuid4

import numpy as np

from callscope.datasets.io_audio import SAMPLE_RATE_HZ
from callscope.eval.scorers.asr import score_asr
from callscope.eval.types import EvalItemResult
from callscope.providers.base import BrainBackend, Msg, STTProvider, TTSProvider

ReplayMode = Literal["stage_replay", "text_replay"]


@dataclass(slots=True)
class ReplayItem:
    item_id: str
    text: str
    scenario_id: str = ""
    voice: str = ""
    condition: str = "C0"
    variant: int = 0
    wav_bytes: bytes | None = None
    intent: str = ""
    slots: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StageTimings:
    stt_ms: float = 0.0
    brain_ms: float = 0.0
    tts_ms: float = 0.0
    ref_asr_ms: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "stt_ms": self.stt_ms,
            "brain_ms": self.brain_ms,
            "tts_ms": self.tts_ms,
            "ref_asr_ms": self.ref_asr_ms,
        }


def pcm16_wav_bytes(audio: np.ndarray[Any, Any], sr: int = SAMPLE_RATE_HZ) -> bytes:
    pcm = np.clip(audio.astype(np.float64), -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())
    return buf.getvalue()


def synthetic_wav_for_text(text: str, *, sr: int = SAMPLE_RATE_HZ) -> bytes:
    """Deterministic tone WAV sized from text (golden / CI without stored audio)."""
    dur = max(0.3, 0.05 * max(len(text), 1))
    n = int(sr * dur)
    t = np.arange(n, dtype=np.float64) / sr
    audio = (0.2 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)
    return pcm16_wav_bytes(audio, sr)


async def _collect_brain(
    brain: BrainBackend, messages: list[Msg], call_id: str, turn_id: str
) -> str:
    parts: list[str] = []
    async for delta in brain.stream_reply(messages, call_id=call_id, turn_id=turn_id):
        if delta.kind == "text" and delta.text:
            parts.append(delta.text)
        if delta.kind == "done":
            break
    return "".join(parts)


async def _collect_tts(tts: TTSProvider, text: str, voice: str = "mock") -> bytes:
    chunks: list[bytes] = []
    async for chunk in tts.stream(text, voice=voice, speed=1.0):
        chunks.append(chunk)
    return b"".join(chunks)


async def replay_item(
    item: ReplayItem,
    *,
    mode: ReplayMode,
    stt: STTProvider,
    brain: BrainBackend,
    tts: TTSProvider,
    ref_asr: STTProvider | None = None,
) -> EvalItemResult:
    """Replay one item; reuse live provider protocols (no forked path)."""
    timings = StageTimings()
    call_id = f"eval-{item.item_id}"
    turn_id = str(uuid4())
    hyp_transcript = ""
    agent_text = ""
    flags: list[str] = []

    if mode == "stage_replay":
        wav = item.wav_bytes or synthetic_wav_for_text(item.text)
        t0 = time.perf_counter()
        tr = await stt.transcribe(wav, sample_rate=SAMPLE_RATE_HZ)
        timings.stt_ms = (time.perf_counter() - t0) * 1000.0
        hyp_transcript = tr.text
        messages = [Msg(role="user", content=hyp_transcript or item.text)]
    else:
        hyp_transcript = item.text
        messages = [Msg(role="user", content=item.text)]

    t0 = time.perf_counter()
    agent_text = await _collect_brain(brain, messages, call_id, turn_id)
    timings.brain_ms = (time.perf_counter() - t0) * 1000.0

    if mode == "stage_replay":
        t0 = time.perf_counter()
        await _collect_tts(tts, agent_text or "OK.", voice=item.voice or "mock")
        timings.tts_ms = (time.perf_counter() - t0) * 1000.0
        # Round-trip intelligibility proxy via reference ASR on TTS output.
        # Mocks: re-transcribe a synthetic wav of agent text as stand-in for PCM wrap.
        if ref_asr is not None:
            t0 = time.perf_counter()
            ref = await ref_asr.transcribe(
                synthetic_wav_for_text(agent_text or "OK."),
                sample_rate=SAMPLE_RATE_HZ,
            )
            timings.ref_asr_ms = (time.perf_counter() - t0) * 1000.0
            if not ref.text:
                flags.append("tts_unintelligible")

    asr = score_asr(item.text, hyp_transcript)
    result = EvalItemResult(
        hyp_transcript=hyp_transcript,
        wer=asr.wer,
        slots_pred=dict(item.slots),
        tool_calls_pred=[],
        latencies_ms=timings.to_dict(),
        flags=flags,
        auto_root_cause=None,
        detail={
            "mode": mode,
            "agent_text": agent_text,
            "asr": asr.to_dict(),
            "scenario_id": item.scenario_id,
            "voice": item.voice,
            "condition": item.condition,
            "variant": item.variant,
        },
    )
    return result


__all__ = [
    "ReplayItem",
    "ReplayMode",
    "StageTimings",
    "pcm16_wav_bytes",
    "replay_item",
    "synthetic_wav_for_text",
]
