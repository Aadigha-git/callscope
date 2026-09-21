"""WAV helpers and pure-numpy telephony transforms (ported from S-5 probe)."""

from __future__ import annotations

import hashlib
import wave
from pathlib import Path
from typing import Any, cast

import numpy as np
from scipy import signal

SAMPLE_RATE_HZ = 16_000
ArrayF = np.ndarray[Any, Any]


def read_wav(path: Path) -> tuple[ArrayF, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        raw = w.readframes(n)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    return cast(ArrayF, audio.astype(np.float32)), int(sr)


def write_wav(path: Path, audio: ArrayF, sr: int = SAMPLE_RATE_HZ) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm: ArrayF = np.clip(audio.astype(np.float64), -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())


def audio_sha256(audio: ArrayF, sr: int) -> str:
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
    h = hashlib.sha256()
    h.update(sr.to_bytes(4, "little"))
    h.update(pcm16)
    return h.hexdigest()


def peak(audio: ArrayF) -> float:
    if audio.size == 0:
        return 0.0
    return float(np.max(np.abs(audio)))


def mulaw_encode(x: ArrayF, mu: int = 255) -> ArrayF:
    clipped = np.clip(x, -1.0, 1.0)
    return cast(
        ArrayF,
        np.sign(clipped) * np.log1p(mu * np.abs(clipped)) / np.log1p(mu),
    )


def mulaw_decode(y: ArrayF, mu: int = 255) -> ArrayF:
    return cast(
        ArrayF,
        np.sign(y) * (1.0 / mu) * ((1.0 + mu) ** np.abs(y) - 1.0),
    )


def apply_c1(audio: ArrayF, sr: int) -> tuple[ArrayF, int]:
    """C1: band-limit 300-3400 Hz, 8 kHz mu-law round-trip, resample to 16 kHz."""
    nyq = sr / 2.0
    low = 300.0 / nyq
    high = min(3400.0 / nyq, 0.99)
    b, a = signal.butter(4, [low, high], btype="band")
    padlen = min(3 * max(len(a), len(b)), max(0, len(audio) - 1))
    filtered = signal.filtfilt(b, a, audio, padlen=padlen)

    n8 = int(len(filtered) * 8000 / sr)
    a8 = cast(ArrayF, signal.resample(filtered, max(n8, 1)))

    y = mulaw_encode(a8)
    q = np.round((y + 1.0) * 127.5).astype(np.int16)
    y_q = cast(ArrayF, q.astype(np.float32) / 127.5 - 1.0)
    a8_u = mulaw_decode(y_q)

    n16 = int(len(a8_u) * SAMPLE_RATE_HZ / 8000)
    a16 = signal.resample(a8_u, max(n16, 1))
    return cast(ArrayF, a16.astype(np.float32)), SAMPLE_RATE_HZ


def coloured_noise(n: int, rng: np.random.Generator, *, beta: float = 1.0) -> ArrayF:
    """Deterministic coloured noise (beta~1 pink-ish) via FFT shaping."""
    white = rng.standard_normal(n)
    spectrum = np.fft.rfft(white)
    freqs = np.fft.rfftfreq(n)
    freqs[0] = freqs[1] if len(freqs) > 1 else 1.0
    spectrum *= freqs ** (-beta / 2.0)
    out = np.fft.irfft(spectrum, n=n)
    out = out / (np.std(out) + 1e-12)
    return cast(ArrayF, out.astype(np.float32))


def mix_snr(clean: ArrayF, noise: ArrayF, snr_db: float) -> ArrayF:
    if noise.size < clean.size:
        reps = int(np.ceil(clean.size / max(noise.size, 1)))
        noise = np.tile(noise, reps)[: clean.size]
    else:
        noise = noise[: clean.size]
    p_sig = float(np.mean(clean**2) + 1e-12)
    p_noi = float(np.mean(noise**2) + 1e-12)
    scale = np.sqrt(p_sig / (p_noi * 10 ** (snr_db / 10.0)))
    return cast(ArrayF, (clean + scale * noise).astype(np.float32))


def measured_snr_db(clean: ArrayF, mixed: ArrayF) -> float:
    """Estimate SNR from mixed - clean residual (aligned lengths)."""
    n = min(clean.size, mixed.size)
    c = clean[:n]
    m = mixed[:n]
    noise = m - c
    p_sig = float(np.mean(c**2) + 1e-12)
    p_noi = float(np.mean(noise**2) + 1e-12)
    return float(10.0 * np.log10(p_sig / p_noi))


def apply_frame_loss(
    audio: ArrayF,
    sr: int,
    *,
    rate: float,
    frame_ms: int,
    rng: np.random.Generator,
) -> tuple[ArrayF, float]:
    frame = max(1, int(sr * frame_ms / 1000))
    out = audio.copy()
    n_frames = max(1, len(out) // frame)
    dropped = 0
    for i in range(n_frames):
        if rng.random() < rate:
            start = i * frame
            out[start : start + frame] = 0.0
            dropped += 1
    return out, dropped / n_frames


def highband_energy_ratio(audio: ArrayF, sr: int, cutoff_hz: float = 3600.0) -> float:
    """Fraction of spectral power above ``cutoff_hz`` (linear)."""
    if audio.size < 16:
        return 0.0
    spec = np.abs(np.fft.rfft(audio)) ** 2
    freqs = np.fft.rfftfreq(audio.size, d=1.0 / sr)
    total = float(np.sum(spec) + 1e-12)
    high = float(np.sum(spec[freqs >= cutoff_hz]))
    return high / total


def tempo_stretch(audio: ArrayF, factor: float) -> ArrayF:
    """Crude resample-based tempo change (factor >1 = faster/shorter)."""
    if abs(factor - 1.0) < 1e-6:
        return cast(ArrayF, audio.astype(np.float32))
    n = max(1, int(len(audio) / factor))
    return cast(ArrayF, signal.resample(audio, n).astype(np.float32))


__all__ = [
    "SAMPLE_RATE_HZ",
    "ArrayF",
    "apply_c1",
    "apply_frame_loss",
    "audio_sha256",
    "coloured_noise",
    "highband_energy_ratio",
    "measured_snr_db",
    "mix_snr",
    "mulaw_decode",
    "mulaw_encode",
    "peak",
    "read_wav",
    "tempo_stretch",
    "write_wav",
]
