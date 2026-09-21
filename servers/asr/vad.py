"""Lightweight energy VAD for segmenting non-streaming ASR backends."""

from __future__ import annotations

import array
import math


class EnergyVAD:
    """Simple RMS energy VAD — no model weights (CI-safe).

    Silero remains available for the LiveKit worker path (T-M0-05); this
    energy gate is enough to drive VAD-segmented Whisper decoding in the ASR
    server without importing torch in CI.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 16_000,
        frame_ms: int = 20,
        speech_threshold: float = 500.0,
        hangover_frames: int = 10,
    ) -> None:
        self._frame_samples = max(int(sample_rate * frame_ms / 1000), 1)
        self._threshold = speech_threshold
        self._hangover = hangover_frames
        self._buf = bytearray()
        self._in_speech = False
        self._silence_run = 0
        self._speech_pcm = bytearray()

    @property
    def frame_bytes(self) -> int:
        return self._frame_samples * 2

    def push(self, pcm: bytes) -> list[bytes]:
        """Feed PCM16LE; return completed speech segments (may be empty)."""
        self._buf.extend(pcm)
        segments: list[bytes] = []
        fb = self.frame_bytes
        while len(self._buf) >= fb:
            frame = bytes(self._buf[:fb])
            del self._buf[:fb]
            rms = _rms_pcm16(frame)
            if rms >= self._threshold:
                self._in_speech = True
                self._silence_run = 0
                self._speech_pcm.extend(frame)
            elif self._in_speech:
                self._speech_pcm.extend(frame)
                self._silence_run += 1
                if self._silence_run >= self._hangover:
                    segments.append(bytes(self._speech_pcm))
                    self._speech_pcm.clear()
                    self._in_speech = False
                    self._silence_run = 0
        return segments

    def flush(self) -> bytes | None:
        leftover = bytes(self._speech_pcm) + bytes(self._buf)
        self._speech_pcm.clear()
        self._buf.clear()
        self._in_speech = False
        self._silence_run = 0
        return leftover if leftover else None


def _rms_pcm16(frame: bytes) -> float:
    if len(frame) < 2:
        return 0.0
    samples = array.array("h")
    samples.frombytes(frame[: len(frame) - (len(frame) % 2)])
    if not samples:
        return 0.0
    acc = sum(float(s) * float(s) for s in samples)
    return math.sqrt(acc / len(samples))
