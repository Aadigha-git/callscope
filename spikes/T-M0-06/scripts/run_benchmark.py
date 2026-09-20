#!/usr/bin/env python3
"""Benchmark native ASR / TTS / VAD candidates for T-M0-06 (S-5).

Downloads stay under 2 GB (see docs/DOWNLOAD_SIZES.md). Measures RTF, peak
RSS delta, first-audio latency (TTS), and WER on C0 vs C1 probe audio.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import psutil
import soundfile as sf
from jiwer import wer as compute_wer

ROOT = Path(__file__).resolve().parents[3]
SPIKE = Path(__file__).resolve().parents[1]
PROBE = ROOT / "eval" / "probe"
RESULTS = SPIKE / "results"
CACHE = SPIKE / ".model_cache"
CACHE.mkdir(parents=True, exist_ok=True)


@dataclass
class AsrResult:
    engine: str
    model: str
    licence: str
    condition: str
    n: int
    wer: float
    rtf_mean: float
    rtf_p95: float
    peak_rss_mb: float
    streaming: str
    errors: int
    notes: str = ""


@dataclass
class TtsResult:
    engine: str
    model: str
    licence: str
    n: int
    first_audio_p50_ms: float
    first_audio_p95_ms: float
    rtf_mean: float
    peak_rss_mb: float
    streaming: str
    errors: int
    notes: str = ""


@dataclass
class VadResult:
    engine: str
    model: str
    licence: str
    n: int
    mean_speech_ratio: float
    latency_p50_ms: float
    peak_rss_mb: float
    errors: int
    notes: str = ""


def _rss_mb() -> float:
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def _pct(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f)


def load_probe(condition: str) -> list[tuple[str, str, Path]]:
    manifest = json.loads((PROBE / "manifest.json").read_text(encoding="utf-8"))
    rows = []
    for u in manifest["utterances"]:
        uid = u["id"]
        text = u["text"]
        wav = ROOT / u[condition]
        rows.append((uid, text, wav))
    return rows


def run_asr(
    name: str,
    model_id: str,
    licence: str,
    streaming: str,
    transcribe: Callable[[Path], str],
    condition: str,
    limit: int,
) -> AsrResult:
    rows = load_probe(condition)[:limit]
    wers: list[float] = []
    rtfs: list[float] = []
    errors = 0
    rss0 = _rss_mb()
    peak = rss0
    for uid, ref, wav in rows:
        try:
            info = sf.info(str(wav))
            dur = float(info.frames) / float(info.samplerate)
            t0 = time.perf_counter()
            hyp = transcribe(wav)
            elapsed = time.perf_counter() - t0
            rtfs.append(elapsed / max(dur, 1e-6))
            w = float(compute_wer(ref.lower(), hyp.lower().strip()))
            wers.append(w)
            peak = max(peak, _rss_mb())
            print(f"  ASR {name}/{condition} {uid}: wer={w:.3f} rtf={rtfs[-1]:.3f}", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  ASR {name}/{condition} {uid} ERROR: {exc}", flush=True)
            traceback.print_exc()
    rtfs_s = sorted(rtfs)
    return AsrResult(
        engine=name,
        model=model_id,
        licence=licence,
        condition=condition,
        n=len(rows),
        wer=round(float(np.mean(wers)) if wers else float("nan"), 4),
        rtf_mean=round(float(np.mean(rtfs)) if rtfs else float("nan"), 4),
        rtf_p95=round(_pct(rtfs_s, 95), 4) if rtfs_s else float("nan"),
        peak_rss_mb=round(peak - rss0, 1),
        streaming=streaming,
        errors=errors,
    )


def bench_mlx_whisper(limit: int) -> list[AsrResult]:
    import mlx_whisper

    out: list[AsrResult] = []
    # mlx-whisper pulls openai/whisper-* converted for MLX; tiny/base << 2 GB
    for model, licence in (
        ("mlx-community/whisper-tiny", "MIT (code+weights)"),
        ("mlx-community/whisper-base.en-mlx", "MIT (code+weights)"),
    ):
        # Warmup once
        def make_fn(m: str = model) -> Callable[[Path], str]:
            def _t(path: Path) -> str:
                r = mlx_whisper.transcribe(str(path), path_or_hf_repo=m)
                return str(r.get("text") or "")

            return _t

        for cond in ("c0", "c1"):
            out.append(
                run_asr(
                    "mlx-whisper",
                    model,
                    licence,
                    "batch (VAD-segment for streaming)",
                    make_fn(),
                    cond,
                    limit,
                )
            )
    return out


def bench_faster_whisper(limit: int) -> list[AsrResult]:
    from faster_whisper import WhisperModel

    out: list[AsrResult] = []
    for size in ("tiny", "base"):
        model = WhisperModel(size, device="cpu", compute_type="int8")
        model_id = f"Systran/faster-whisper-{size}"

        def make_fn(m: WhisperModel = model) -> Callable[[Path], str]:
            def _t(path: Path) -> str:
                segments, _info = m.transcribe(str(path), beam_size=1)
                return " ".join(s.text.strip() for s in segments)

            return _t

        for cond in ("c0", "c1"):
            out.append(
                run_asr(
                    "faster-whisper",
                    model_id,
                    "MIT",
                    "batch (CPU; VAD-segment for streaming)",
                    make_fn(),
                    cond,
                    limit,
                )
            )
    return out


def bench_parakeet(limit: int) -> list[AsrResult]:
    """Optional: parakeet-mlx if importable. Prefer models <2 GB."""
    try:
        from parakeet_mlx import from_pretrained
    except Exception as exc:  # noqa: BLE001
        print(f"parakeet-mlx unavailable: {exc}", flush=True)
        return []

    # int8 / smaller checkpoint if the package supports model id override
    model_id = os.environ.get(
        "PARAKEET_MODEL", "mlx-community/parakeet-tdt-0.6b-v3"
    )
    # Guard: skip if user didn't confirm BF16 ~2.5GB
    if "int8" not in model_id.lower() and "int4" not in model_id.lower():
        print(
            f"SKIP parakeet default {model_id} (~2.5 GB BF16). "
            "Set PARAKEET_MODEL to an int8/int4 id under 2 GB to enable.",
            flush=True,
        )
        return [
            AsrResult(
                engine="parakeet-mlx",
                model=model_id,
                licence="Apache-2.0 code; weights often CC-BY-4.0",
                condition="skipped",
                n=0,
                wer=float("nan"),
                rtf_mean=float("nan"),
                rtf_p95=float("nan"),
                peak_rss_mb=0.0,
                streaming="native streaming (TDT) when enabled",
                errors=0,
                notes="Skipped BF16 ~2.5GB download per size gate; prefer int8",
            )
        ]

    model = from_pretrained(model_id)

    def _t(path: Path) -> str:
        r = model.transcribe(str(path))
        if hasattr(r, "text"):
            return str(r.text)
        if isinstance(r, dict):
            return str(r.get("text") or "")
        return str(r)

    out = []
    for cond in ("c0", "c1"):
        out.append(
            run_asr(
                "parakeet-mlx",
                model_id,
                "Apache-2.0 / CC-BY-4.0 weights",
                "native streaming (TDT)",
                _t,
                cond,
                limit,
            )
        )
    return out


def bench_silero_vad(limit: int) -> VadResult:
    import onnxruntime as ort
    import urllib.request

    model_path = CACHE / "silero_vad.onnx"
    if not model_path.is_file():
        url = (
            "https://github.com/snakers4/silero-vad/raw/master/"
            "src/silero_vad/data/silero_vad.onnx"
        )
        print(f"Downloading Silero VAD (~2 MB) → {model_path}", flush=True)
        urllib.request.urlretrieve(url, model_path)

    sess = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    rows = load_probe("c0")[:limit]
    ratios: list[float] = []
    lats: list[float] = []
    errors = 0
    rss0 = _rss_mb()
    peak = rss0
    for uid, _ref, wav in rows:
        try:
            audio, sr = sf.read(str(wav), dtype="float32")
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            # Silero expects 16k chunks of 512
            if sr != 16000:
                # naive resample via numpy linspace
                n = int(len(audio) * 16000 / sr)
                audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(
                    np.float32
                )
            hop = 512
            speech = 0
            total = 0
            t0 = time.perf_counter()
            state = np.zeros((2, 1, 128), dtype=np.float32)
            for i in range(0, max(0, len(audio) - hop + 1), hop):
                chunk = audio[i : i + hop].astype(np.float32)
                if len(chunk) < hop:
                    chunk = np.pad(chunk, (0, hop - len(chunk)))
                feeds = {
                    "input": chunk.reshape(1, -1),
                    "state": state,
                    "sr": np.array(16000, dtype=np.int64),
                }
                outs = sess.run(None, feeds)
                prob = float(np.array(outs[0]).reshape(-1)[0])
                state = np.array(outs[1], dtype=np.float32)
                total += 1
                if prob >= 0.5:
                    speech += 1
            lats.append((time.perf_counter() - t0) * 1000.0)
            ratios.append(speech / max(total, 1))
            peak = max(peak, _rss_mb())
            print(f"  VAD {uid}: speech_ratio={ratios[-1]:.2f}", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  VAD {uid} ERROR: {exc}", flush=True)
            traceback.print_exc()
            break  # if API mismatch, stop
    lats_s = sorted(lats)
    return VadResult(
        engine="silero-vad",
        model="silero_vad.onnx",
        licence="MIT",
        n=len(ratios),
        mean_speech_ratio=round(float(np.mean(ratios)) if ratios else float("nan"), 4),
        latency_p50_ms=round(_pct(lats_s, 50), 2) if lats_s else float("nan"),
        peak_rss_mb=round(peak - rss0, 1),
        errors=errors,
        notes="ONNX Runtime CPU; chunk 512 @ 16 kHz",
    )


def bench_piper(limit: int) -> TtsResult:
    """Piper via piper-tts package if available; else note skip."""
    try:
        from piper import PiperVoice
    except Exception as exc:  # noqa: BLE001
        return TtsResult(
            engine="piper",
            model="en_US-lessac-medium",
            licence="GPL-3.0-or-later (caution)",
            n=0,
            first_audio_p50_ms=float("nan"),
            first_audio_p95_ms=float("nan"),
            rtf_mean=float("nan"),
            peak_rss_mb=0.0,
            streaming="chunked PCM",
            errors=1,
            notes=f"piper package missing: {exc}",
        )

    # Download voice onnx (~61 MB) into cache if needed
    voice_dir = CACHE / "piper"
    voice_dir.mkdir(parents=True, exist_ok=True)
    onnx = voice_dir / "en_US-lessac-medium.onnx"
    conf = voice_dir / "en_US-lessac-medium.onnx.json"
    if not onnx.is_file():
        import urllib.request

        base = (
            "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
            "en/en_US/lessac/medium"
        )
        print("Downloading Piper en_US-lessac-medium (~61 MB)…", flush=True)
        urllib.request.urlretrieve(f"{base}/en_US-lessac-medium.onnx", onnx)
        urllib.request.urlretrieve(f"{base}/en_US-lessac-medium.onnx.json", conf)

    voice = PiperVoice.load(str(onnx), config_path=str(conf), use_cuda=False)
    texts = [t for _uid, t, _p in load_probe("c0")[:limit]]
    firsts: list[float] = []
    rtfs: list[float] = []
    errors = 0
    rss0 = _rss_mb()
    peak = rss0
    for i, text in enumerate(texts):
        try:
            t0 = time.perf_counter()
            first = None
            n_samples = 0
            sr = 22050
            for chunk in voice.synthesize(text):
                if first is None:
                    first = time.perf_counter()
                audio = np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16)
                n_samples += len(audio)
                sr = chunk.sample_rate
            if first is None:
                raise RuntimeError("no audio")
            firsts.append((first - t0) * 1000.0)
            dur = n_samples / float(sr)
            rtfs.append((time.perf_counter() - t0) / max(dur, 1e-6))
            peak = max(peak, _rss_mb())
            print(f"  TTS piper {i}: first={firsts[-1]:.0f}ms rtf={rtfs[-1]:.3f}", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  TTS piper ERROR: {exc}", flush=True)
            traceback.print_exc()
    firsts_s = sorted(firsts)
    return TtsResult(
        engine="piper",
        model="en_US-lessac-medium",
        licence="GPL-3.0-or-later (distribution caution)",
        n=len(firsts),
        first_audio_p50_ms=round(_pct(firsts_s, 50), 2) if firsts_s else float("nan"),
        first_audio_p95_ms=round(_pct(firsts_s, 95), 2) if firsts_s else float("nan"),
        rtf_mean=round(float(np.mean(rtfs)) if rtfs else float("nan"), 4),
        peak_rss_mb=round(peak - rss0, 1),
        streaming="chunked PCM",
        errors=errors,
    )


def bench_kokoro(limit: int) -> TtsResult:
    try:
        from kokoro_onnx import Kokoro
    except Exception as exc:  # noqa: BLE001
        return TtsResult(
            engine="kokoro-onnx",
            model="kokoro-v1.0",
            licence="Apache-2.0 weights; MIT wrappers",
            n=0,
            first_audio_p50_ms=float("nan"),
            first_audio_p95_ms=float("nan"),
            rtf_mean=float("nan"),
            peak_rss_mb=0.0,
            streaming="full utterance (chunk via streaming API if used)",
            errors=1,
            notes=f"kokoro-onnx missing: {exc}",
        )

    model_path = CACHE / "kokoro-v1.0.onnx"
    voices_path = CACHE / "voices-v1.0.bin"
    if not model_path.is_file() or not voices_path.is_file():
        import urllib.request

        print("Downloading Kokoro ONNX (~330 MB model + voices)…", flush=True)
        urllib.request.urlretrieve(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx",
            model_path,
        )
        urllib.request.urlretrieve(
            "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin",
            voices_path,
        )

    kokoro = Kokoro(str(model_path), str(voices_path))
    texts = [t for _uid, t, _p in load_probe("c0")[:limit]]
    firsts: list[float] = []
    rtfs: list[float] = []
    errors = 0
    rss0 = _rss_mb()
    peak = rss0
    for i, text in enumerate(texts):
        try:
            t0 = time.perf_counter()
            samples, sr = kokoro.create(text, voice="af_sarah", speed=1.0)
            firsts.append((time.perf_counter() - t0) * 1000.0)  # full synth ≈ first audio for non-stream
            dur = len(samples) / float(sr)
            rtfs.append((time.perf_counter() - t0) / max(dur, 1e-6))
            # recompute properly
            elapsed = firsts[-1] / 1000.0
            rtfs[-1] = elapsed / max(dur, 1e-6)
            peak = max(peak, _rss_mb())
            print(f"  TTS kokoro {i}: first≈{firsts[-1]:.0f}ms rtf={rtfs[-1]:.3f}", flush=True)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  TTS kokoro ERROR: {exc}", flush=True)
            traceback.print_exc()
    firsts_s = sorted(firsts)
    return TtsResult(
        engine="kokoro-onnx",
        model="kokoro-v1.0 + voices-v1.0",
        licence="Apache-2.0 weights",
        n=len(firsts),
        first_audio_p50_ms=round(_pct(firsts_s, 50), 2) if firsts_s else float("nan"),
        first_audio_p95_ms=round(_pct(firsts_s, 95), 2) if firsts_s else float("nan"),
        rtf_mean=round(float(np.mean(rtfs)) if rtfs else float("nan"), 4),
        peak_rss_mb=round(peak - rss0, 1),
        streaming="utterance (stream API available in package)",
        errors=errors,
        notes="first_audio ≈ full utterance latency for non-stream create()",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    parser.add_argument(
        "--skip",
        default="",
        help="Comma list: mlx-whisper,faster-whisper,parakeet,vad,piper,kokoro",
    )
    args = parser.parse_args()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    RESULTS.mkdir(parents=True, exist_ok=True)

    if not (PROBE / "manifest.json").is_file():
        raise SystemExit("Run generate_probe_audio.py first")

    asr: list[AsrResult] = []
    tts: list[TtsResult] = []
    vad: list[VadResult] = []

    if "mlx-whisper" not in skip:
        print("=== mlx-whisper ===", flush=True)
        asr.extend(bench_mlx_whisper(args.limit))
    if "faster-whisper" not in skip:
        print("=== faster-whisper ===", flush=True)
        asr.extend(bench_faster_whisper(args.limit))
    if "parakeet" not in skip:
        print("=== parakeet-mlx ===", flush=True)
        asr.extend(bench_parakeet(args.limit))
    if "vad" not in skip:
        print("=== silero vad ===", flush=True)
        vad.append(bench_silero_vad(args.limit))
    if "piper" not in skip:
        print("=== piper ===", flush=True)
        tts.append(bench_piper(args.limit))
    if "kokoro" not in skip:
        print("=== kokoro ===", flush=True)
        tts.append(bench_kokoro(args.limit))

    summary = {
        "task": "T-M0-06",
        "spike": "S-5",
        "limit": args.limit,
        "asr": [asdict(x) for x in asr],
        "tts": [asdict(x) for x in tts],
        "vad": [asdict(x) for x in vad],
        "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    out = RESULTS / "benchmark.json"
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
