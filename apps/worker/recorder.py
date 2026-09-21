"""Local call audio recorder (design §4.2 / T-M2-06). Consent-gated."""

from __future__ import annotations

import logging
import wave
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class RecordingUris:
    mixed_uri: str
    caller_uri: str
    agent_uri: str
    root: Path


@dataclass
class CallRecorder:
    """Accumulate PCM16 mono tracks and write WAVs on finalize.

    When ``consent_recording`` is False the recorder is a no-op (no files created).
    """

    call_id: UUID
    consent_recording: bool
    root: Path
    sample_rate: int = 16_000
    _caller: bytearray = field(default_factory=bytearray, repr=False)
    _agent: bytearray = field(default_factory=bytearray, repr=False)
    _finalized: bool = False

    def __post_init__(self) -> None:
        if self.consent_recording:
            self.root.mkdir(parents=True, exist_ok=True)

    @property
    def enabled(self) -> bool:
        return self.consent_recording

    def append_caller(self, pcm: bytes) -> None:
        if self.enabled and pcm:
            self._caller.extend(pcm)

    def append_agent(self, pcm: bytes) -> None:
        if self.enabled and pcm:
            self._agent.extend(pcm)

    def finalize(self) -> RecordingUris | None:
        """Write caller/agent/mixed WAVs. Returns None when consent was missing."""
        if not self.enabled:
            logger.info("recorder skipped call_id=%s (no consent)", self.call_id)
            return None
        if self._finalized:
            return self._uris()
        self._finalized = True
        call_dir = self.root / str(self.call_id)
        call_dir.mkdir(parents=True, exist_ok=True)
        caller_path = call_dir / "caller.wav"
        agent_path = call_dir / "agent.wav"
        mixed_path = call_dir / "mixed.wav"
        _write_wav(caller_path, bytes(self._caller), self.sample_rate)
        _write_wav(agent_path, bytes(self._agent), self.sample_rate)
        mixed = _mix_pcm16(bytes(self._caller), bytes(self._agent))
        _write_wav(mixed_path, mixed, self.sample_rate)
        self._caller.clear()
        self._agent.clear()
        return RecordingUris(
            mixed_uri=mixed_path.resolve().as_uri(),
            caller_uri=caller_path.resolve().as_uri(),
            agent_uri=agent_path.resolve().as_uri(),
            root=call_dir,
        )

    def _uris(self) -> RecordingUris | None:
        call_dir = self.root / str(self.call_id)
        if not (call_dir / "mixed.wav").exists():
            return None
        return RecordingUris(
            mixed_uri=(call_dir / "mixed.wav").resolve().as_uri(),
            caller_uri=(call_dir / "caller.wav").resolve().as_uri(),
            agent_uri=(call_dir / "agent.wav").resolve().as_uri(),
            root=call_dir,
        )


def _write_wav(path: Path, pcm: bytes, sample_rate: int) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm if pcm else b"\x00\x00")


def _mix_pcm16(a: bytes, b: bytes) -> bytes:
    """Average two PCM16 little-endian streams (pad shorter with silence)."""
    n = max(len(a), len(b))
    if n == 0:
        return b"\x00\x00"
    if n % 2:
        n -= 1
    out = bytearray(n)
    for i in range(0, n, 2):
        sa = int.from_bytes(a[i : i + 2] if i + 1 < len(a) else b"\x00\x00", "little", signed=True)
        sb = int.from_bytes(b[i : i + 2] if i + 1 < len(b) else b"\x00\x00", "little", signed=True)
        mixed = max(-32768, min(32767, (sa + sb) // 2))
        out[i : i + 2] = int(mixed).to_bytes(2, "little", signed=True)
    return bytes(out)
