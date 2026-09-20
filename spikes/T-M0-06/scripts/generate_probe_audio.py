#!/usr/bin/env python3
"""Generate 30 synthetic probe utterances (macOS `say`) + C1 telephony chain.

No personal voices — system TTS only. Writes under eval/probe/.
C1 (design §5): band-limit ~300–3400 Hz, 8 kHz, μ-law encode/decode.
"""

from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path

import numpy as np
from scipy import signal

ROOT = Path(__file__).resolve().parents[3]
PROBE = ROOT / "eval" / "probe"
AUDIO_C0 = PROBE / "audio" / "c0"
AUDIO_C1 = PROBE / "audio" / "c1"
TX = PROBE / "transcripts"

# 30 fictional Lakeside lines (digits, names, dates, FAQs).
UTTERANCES: list[tuple[str, str]] = [
    ("u01", "What are your hours of operation?"),
    ("u02", "Do you serve Lakeside County?"),
    ("u03", "How much is a standard visit?"),
    ("u04", "I'd like to book a plumbing appointment."),
    ("u05", "Is Tuesday September twenty ninth available?"),
    ("u06", "My phone number is five five five zero one zero zero one zero zero."),
    ("u07", "Please call Alex Rivera back at five five five zero one zero zero two zero zero."),
    ("u08", "Confirmation code L H S one zero zero one."),
    ("u09", "Reschedule to October first at eleven thirty."),
    ("u10", "Cancel my appointment confirmation L H S two zero zero one."),
    ("u11", "The address is one two three Maple Street."),
    ("u12", "I need an H V A C tune-up quote."),
    ("u13", "Are you open on Saturdays?"),
    ("u14", "Book electrical for October second at three P M."),
    ("u15", "My name is Jordan Lee."),
    ("u16", "The callback reason is a remodel quote."),
    ("u17", "Please transfer me to a human agent."),
    ("u18", "What is the price for an H V A C tune-up?"),
    ("u19", "Check availability for appliance repair on October third."),
    ("u20", "Phone five five five zero two zero zero three zero zero."),
    ("u21", "Confirm booking for Sam Patel on October second."),
    ("u22", "We are at four five six Oak Avenue unit B."),
    ("u23", "The appointment was for nine A M."),
    ("u24", "I confirm those details yes."),
    ("u25", "How far out do you travel from downtown?"),
    ("u26", "Code L H S one zero zero five please."),
    ("u27", "Date twenty twenty six dash ten dash zero seven."),
    ("u28", "Name Casey Ng phone five five five zero one zero zero four zero zero."),
    ("u29", "Is downtown Lakeside in your service area?"),
    ("u30", "Take a callback for Pat Caller about plumbing."),
]


def say_to_wav(text: str, out_wav: Path, voice: str = "Albert") -> None:
    """macOS `say` → AIFF → WAV 16 kHz mono PCM16."""
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    aiff = out_wav.with_suffix(".aiff")
    subprocess.run(
        ["say", "-v", voice, "-o", str(aiff), text],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "afconvert",
            "-f",
            "WAVE",
            "-d",
            "LEI16@16000",
            "-c",
            "1",
            str(aiff),
            str(out_wav),
        ],
        check=True,
        capture_output=True,
    )
    aiff.unlink(missing_ok=True)
    with wave.open(str(out_wav), "rb") as w:
        if w.getnframes() < 1600:
            raise RuntimeError(f"empty/short wav from say: {out_wav}")


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        n = w.getnframes()
        ch = w.getnchannels()
        raw = w.readframes(n)
    audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        audio = audio.reshape(-1, ch).mean(axis=1)
    return audio, sr


def write_wav(path: Path, audio: np.ndarray, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.clip(audio, -1.0, 1.0)
    pcm16 = (pcm * 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm16.tobytes())


def mulaw_encode(x: np.ndarray, mu: int = 255) -> np.ndarray:
    x = np.clip(x, -1.0, 1.0)
    return np.sign(x) * np.log1p(mu * np.abs(x)) / np.log1p(mu)


def mulaw_decode(y: np.ndarray, mu: int = 255) -> np.ndarray:
    return np.sign(y) * (1.0 / mu) * ((1.0 + mu) ** np.abs(y) - 1.0)


def apply_c1(audio: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """C1: band-limit 300–3400 Hz, resample to 8 kHz, μ-law round-trip, back to 16 kHz."""
    # Band-limit at original rate
    nyq = sr / 2.0
    low = 300.0 / nyq
    high = min(3400.0 / nyq, 0.99)
    b, a = signal.butter(4, [low, high], btype="band")
    padlen = min(3 * max(len(a), len(b)), max(0, len(audio) - 1))
    filtered = signal.filtfilt(b, a, audio, padlen=padlen)

    # Resample to 8 kHz
    n8 = int(len(filtered) * 8000 / sr)
    a8 = signal.resample(filtered, max(n8, 1))

    # Quantize to 8-bit μ-law then decode
    y = mulaw_encode(a8)
    # 8-bit quantization
    q = np.round((y + 1.0) * 127.5).astype(np.int16)
    y_q = q.astype(np.float32) / 127.5 - 1.0
    a8_u = mulaw_decode(y_q)

    # Upsample back to 16 kHz for ASR consumers that expect 16k
    n16 = int(len(a8_u) * 16000 / 8000)
    a16 = signal.resample(a8_u, max(n16, 1))
    return a16.astype(np.float32), 16000


def main() -> None:
    AUDIO_C0.mkdir(parents=True, exist_ok=True)
    AUDIO_C1.mkdir(parents=True, exist_ok=True)
    TX.mkdir(parents=True, exist_ok=True)

    meta = []
    for uid, text in UTTERANCES:
        c0 = AUDIO_C0 / f"{uid}.wav"
        c1 = AUDIO_C1 / f"{uid}.wav"
        print(f"say {uid}: {text[:48]}…", flush=True)
        say_to_wav(text, c0)
        audio, sr = read_wav(c0)
        a1, sr1 = apply_c1(audio, sr)
        write_wav(c1, a1, sr1)
        (TX / f"{uid}.txt").write_text(text + "\n", encoding="utf-8")
        meta.append(
            {
                "id": uid,
                "text": text,
                "c0": str(c0.relative_to(ROOT)),
                "c1": str(c1.relative_to(ROOT)),
                "duration_c0_s": round(len(audio) / sr, 3),
            }
        )

    manifest = {
        "n": len(meta),
        "voice": "Albert (macOS say — synthetic system TTS, not a personal recording)",
        "c1": "band 300-3400 Hz, 8 kHz μ-law round-trip, resampled to 16 kHz",
        "utterances": meta,
    }
    (PROBE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(meta)} utterances → {PROBE}")


if __name__ == "__main__":
    main()
