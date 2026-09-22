"""Simulated caller participant for LiveKit rooms (T-M4-04).

Uses ``livekit.rtc`` APIs verified from the installed ``livekit`` package
(``Room.connect``, ``AudioSource``, ``LocalAudioTrack.create_audio_track``,
``LocalParticipant.publish_track``, ``AudioSource.capture_frame``).
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from callscope.eval.scenarios import ExpandedScenario, ScenarioTurn


@dataclass(slots=True)
class CallerAction:
    kind: str  # speak | pause | barge
    text: str = ""
    at_ms: int = 0
    duration_ms: int = 0


@dataclass(slots=True)
class CallerRunResult:
    actions: list[CallerAction] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    heard_pcm_bytes: int = 0
    connected: bool = False


class CallerTransport(Protocol):
    async def connect(self, url: str, token: str) -> None: ...

    async def publish_pcm16(
        self, pcm: bytes, *, sample_rate: int = 16_000, num_channels: int = 1
    ) -> None: ...

    async def disconnect(self) -> None: ...


class MockCallerTransport:
    """In-memory transport for CI (no LiveKit)."""

    def __init__(self) -> None:
        self.connected = False
        self.published: list[bytes] = []

    async def connect(self, url: str, token: str) -> None:
        _ = (url, token)
        self.connected = True

    async def publish_pcm16(
        self, pcm: bytes, *, sample_rate: int = 16_000, num_channels: int = 1
    ) -> None:
        _ = (sample_rate, num_channels)
        if not self.connected:
            raise RuntimeError("not connected")
        self.published.append(pcm)

    async def disconnect(self) -> None:
        self.connected = False


class LiveKitCallerTransport:
    """Real LiveKit rtc transport (requires ``uv sync --extra worker``)."""

    def __init__(self) -> None:
        self._room: Any = None
        self._source: Any = None

    async def connect(self, url: str, token: str) -> None:
        from livekit.rtc import AudioSource, LocalAudioTrack, Room

        room = Room()
        await room.connect(url, token)
        source = AudioSource(16_000, 1)
        track = LocalAudioTrack.create_audio_track("caller-audio", source)
        await room.local_participant.publish_track(track)
        self._room = room
        self._source = source

    async def publish_pcm16(
        self, pcm: bytes, *, sample_rate: int = 16_000, num_channels: int = 1
    ) -> None:
        from livekit.rtc import AudioFrame

        if self._source is None:
            raise RuntimeError("not connected")
        samples = len(pcm) // (2 * num_channels)
        if samples <= 0:
            return
        frame = AudioFrame(pcm, sample_rate, num_channels, samples)
        await self._source.capture_frame(frame)

    async def disconnect(self) -> None:
        if self._room is not None:
            await self._room.disconnect()
        self._room = None
        self._source = None


def _tone_pcm16(duration_ms: int, *, sample_rate: int = 16_000) -> bytes:
    import math
    import struct

    n = max(1, int(sample_rate * duration_ms / 1000))
    out = bytearray()
    for i in range(n):
        t = i / sample_rate
        sample = int(0.2 * 32767 * math.sin(2 * math.pi * 440.0 * t))
        out += struct.pack("<h", sample)
    return bytes(out)


def plan_actions(turns: list[ScenarioTurn], *, t0_ms: int = 0) -> list[CallerAction]:
    """Build a timed speak/pause/barge plan from scenario turns."""
    actions: list[CallerAction] = []
    t = t0_ms
    for turn in turns:
        pause = int(turn.pause_ms or 400)
        if pause:
            actions.append(CallerAction(kind="pause", at_ms=t, duration_ms=pause))
            t += pause
        speak_ms = max(400, 60 * max(len(turn.caller.split()), 1))
        if turn.barge_in_at_ms is not None:
            actions.append(
                CallerAction(
                    kind="barge",
                    text=turn.caller,
                    at_ms=t + int(turn.barge_in_at_ms),
                    duration_ms=speak_ms,
                )
            )
            t += int(turn.barge_in_at_ms) + speak_ms
        else:
            actions.append(
                CallerAction(kind="speak", text=turn.caller, at_ms=t, duration_ms=speak_ms)
            )
            t += speak_ms
    return actions


@dataclass
class SimulatedCaller:
    transport: CallerTransport
    sample_rate: int = 16_000

    async def run_scenario(
        self,
        scenario: ExpandedScenario,
        *,
        livekit_url: str,
        token: str,
        wall_clock: bool = False,
    ) -> CallerRunResult:
        actions = plan_actions(scenario.turns)
        result = CallerRunResult(actions=list(actions))
        await self.transport.connect(livekit_url, token)
        result.connected = True
        t0 = time.monotonic()
        for action in actions:
            if wall_clock:
                target = t0 + action.at_ms / 1000.0
                delay = target - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
            if action.kind == "pause":
                result.events.append(
                    {
                        "type": "caller.pause",
                        "t_ms": action.at_ms,
                        "payload": {"duration_ms": action.duration_ms},
                    }
                )
                continue
            pcm = _tone_pcm16(action.duration_ms, sample_rate=self.sample_rate)
            await self.transport.publish_pcm16(pcm, sample_rate=self.sample_rate)
            result.heard_pcm_bytes += len(pcm)
            etype = "barge_in" if action.kind == "barge" else "caller.start"
            result.events.append(
                {
                    "type": etype,
                    "t_ms": action.at_ms,
                    "payload": {"text": action.text},
                }
            )
            result.events.append(
                {
                    "type": "stt.final",
                    "t_ms": action.at_ms + action.duration_ms,
                    "payload": {"text": action.text, "avg_conf": 0.9},
                }
            )
            result.events.append(
                {
                    "type": "caller.stop",
                    "t_ms": action.at_ms + action.duration_ms,
                    "payload": {},
                }
            )
        await self.transport.disconnect()
        return result
