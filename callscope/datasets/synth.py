"""Synthetic caller audio renderer (deterministic; not the agent TTS)."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np

from callscope.datasets.augment import apply_condition
from callscope.datasets.conditions import ALL_CONDITIONS, ConditionCode
from callscope.datasets.io_audio import SAMPLE_RATE_HZ, ArrayF, audio_sha256, write_wav
from callscope.eval.scenarios import Scenario, expand_scenario, load_all_scenarios

# ≥6 synthetic caller voices (formant / F0 profiles). Not agent Piper/Kokoro.
DEFAULT_VOICES: tuple[str, ...] = (
    "caller_alto_a",
    "caller_alto_b",
    "caller_tenor_a",
    "caller_tenor_b",
    "caller_baritone_a",
    "caller_baritone_b",
)

_VOICE_F0: dict[str, float] = {
    "caller_alto_a": 210.0,
    "caller_alto_b": 195.0,
    "caller_tenor_a": 165.0,
    "caller_tenor_b": 150.0,
    "caller_baritone_a": 120.0,
    "caller_baritone_b": 105.0,
}

DEFAULT_N_CALLS = 120
CI_WIDTH_NOTE = (
    "Default synthetic set is ~120 calls (not 300); bootstrap CIs are wider - "
    "always report n per slice."
)


class CallerTTS(Protocol):
    def synthesize(
        self,
        text: str,
        *,
        voice: str,
        seed: int,
        sr: int = SAMPLE_RATE_HZ,
    ) -> ArrayF:
        """Return mono float32 PCM in [-1, 1]."""


@dataclass(frozen=True, slots=True)
class SynthVoiceTTS:
    """Deterministic hash-driven formant beeps - CI-safe stand-in for caller TTS."""

    def synthesize(
        self,
        text: str,
        *,
        voice: str,
        seed: int,
        sr: int = SAMPLE_RATE_HZ,
    ) -> ArrayF:
        f0 = _VOICE_F0.get(voice, 150.0)
        digest = hashlib.sha256(f"{seed}:{voice}:{text}".encode()).digest()
        # ~80 ms per character, min 0.4 s
        dur = max(0.4, 0.08 * max(len(text), 1))
        n = int(sr * dur)
        t = np.arange(n, dtype=np.float64) / sr
        # Slight F0 jitter from digest
        jitter = (digest[0] / 255.0 - 0.5) * 8.0
        phase = 2 * math.pi * (f0 + jitter) * t
        # Simple formants
        wave = 0.45 * np.sin(phase)
        wave += 0.25 * np.sin(2 * phase)
        wave += 0.12 * np.sin(3 * phase)
        # Amplitude envelope from text length pattern
        env = 0.5 + 0.5 * np.sin(np.linspace(0, math.pi, n))
        # Gate silences between "syllables"
        gate = np.ones(n)
        step = max(1, n // max(len(text), 1))
        for i, ch in enumerate(text[:64]):
            if ch.isspace() or ch in ".,!?":
                a = i * step
                gate[a : a + step // 3] = 0.0
        out = (wave * env * gate).astype(np.float32)
        peak_v = float(np.max(np.abs(out)) + 1e-12)
        return cast(ArrayF, (out * (0.9 / peak_v)).astype(np.float32))


@dataclass(slots=True)
class DatasetItemMeta:
    item_id: str
    scenario_id: str
    variant: int
    voice: str
    condition: ConditionCode
    seed: int
    text: str
    wav_relpath: str
    sidecar_relpath: str
    audio_sha256: str
    augmentation: dict[str, Any]
    turns: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cache_key(text: str, voice: str, seed: int) -> str:
    return hashlib.sha256(f"{voice}:{seed}:{text}".encode()).hexdigest()[:16]


def render_turn(
    text: str,
    *,
    voice: str,
    seed: int,
    tts: CallerTTS,
    cache_dir: Path | None,
) -> ArrayF:
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        key = _cache_key(text, voice, seed)
        path = cache_dir / f"{key}.npy"
        if path.exists():
            return cast(ArrayF, np.load(path).astype(np.float32))
    audio = tts.synthesize(text, voice=voice, seed=seed)
    if cache_dir is not None:
        np.save(cache_dir / f"{_cache_key(text, voice, seed)}.npy", audio)
    return audio


def concat_turns(
    turns: list[ArrayF],
    *,
    gap_ms: int = 250,
    sr: int = SAMPLE_RATE_HZ,
) -> ArrayF:
    gap: ArrayF = np.zeros(int(sr * gap_ms / 1000), dtype=np.float32)
    parts: list[ArrayF] = []
    for i, t in enumerate(turns):
        parts.append(t)
        if i < len(turns) - 1:
            parts.append(gap)
    if not parts:
        return cast(ArrayF, np.zeros(sr // 4, dtype=np.float32))
    return cast(ArrayF, np.concatenate(parts).astype(np.float32))


def plan_calls(
    scenarios: list[Scenario],
    *,
    n_calls: int = DEFAULT_N_CALLS,
    voices: tuple[str, ...] = DEFAULT_VOICES,
    conditions: tuple[ConditionCode, ...] = ALL_CONDITIONS,
    seed: int = 42,
) -> list[tuple[Scenario, int, str, ConditionCode, int]]:
    """Deterministic (scenario, variant, voice, condition, item_seed) plan of size ``n_calls``."""
    if not scenarios:
        raise ValueError("no scenarios")
    if len(voices) < 6:
        raise ValueError("need ≥ 6 caller voices (distinct from agent TTS)")
    plan: list[tuple[Scenario, int, str, ConditionCode, int]] = []
    for i in range(n_calls):
        sc = scenarios[i % len(scenarios)]
        variant = (i // len(scenarios)) % 3
        voice = voices[i % len(voices)]
        cond = conditions[i % len(conditions)]
        item_seed = seed + i * 9973
        plan.append((sc, variant, voice, cond, item_seed))
    return plan


def build_dataset(
    *,
    out_dir: Path,
    n_calls: int = DEFAULT_N_CALLS,
    seed: int = 42,
    voices: tuple[str, ...] = DEFAULT_VOICES,
    conditions: tuple[ConditionCode, ...] = ALL_CONDITIONS,
    scenarios: list[Scenario] | None = None,
    tts: CallerTTS | None = None,
    tempo: float = 1.0,
) -> dict[str, Any]:
    """Build synthetic dataset; returns manifest dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    audio_dir = out_dir / "audio"
    cache_dir = out_dir / ".tts_cache"
    scs = scenarios if scenarios is not None else load_all_scenarios()
    engine = tts or SynthVoiceTTS()
    plan = plan_calls(scs, n_calls=n_calls, voices=voices, conditions=conditions, seed=seed)

    items: list[DatasetItemMeta] = []
    for idx, (sc, variant, voice, cond, item_seed) in enumerate(plan):
        expanded = expand_scenario(sc, seed=seed, variant=variant)
        turn_audio = [
            render_turn(
                t.caller or " ",
                voice=voice,
                seed=item_seed + j,
                tts=engine,
                cache_dir=cache_dir,
            )
            for j, t in enumerate(expanded.turns)
        ]
        raw = concat_turns(turn_audio)
        aug_audio, aug = apply_condition(raw, condition=cond, seed=item_seed, tempo=tempo)
        item_id = f"syn_{idx:04d}_{sc.id}_{cond}_{voice}"
        wav_name = f"{item_id}.wav"
        side_name = f"{item_id}.json"
        wav_path = audio_dir / wav_name
        write_wav(wav_path, aug_audio, SAMPLE_RATE_HZ)
        digest = audio_sha256(aug_audio, SAMPLE_RATE_HZ)
        text = " ".join(t.caller for t in expanded.turns)
        meta = DatasetItemMeta(
            item_id=item_id,
            scenario_id=sc.id,
            variant=variant,
            voice=voice,
            condition=cond,
            seed=item_seed,
            text=text,
            wav_relpath=f"audio/{wav_name}",
            sidecar_relpath=f"audio/{side_name}",
            audio_sha256=digest,
            augmentation=aug.to_dict(),
            turns=[t.caller for t in expanded.turns],
        )
        (audio_dir / side_name).write_text(
            json.dumps(meta.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        items.append(meta)

    manifest = {
        "version": 1,
        "n_calls": n_calls,
        "seed": seed,
        "voices": list(voices),
        "conditions": list(conditions),
        "sample_rate_hz": SAMPLE_RATE_HZ,
        "tts": "SynthVoiceTTS (deterministic formant beeps; not agent TTS)",
        "ci_width_note": CI_WIDTH_NOTE,
        "items": [m.to_dict() for m in items],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


__all__ = [
    "CI_WIDTH_NOTE",
    "DEFAULT_N_CALLS",
    "DEFAULT_VOICES",
    "CallerTTS",
    "DatasetItemMeta",
    "SynthVoiceTTS",
    "build_dataset",
    "concat_turns",
    "plan_calls",
    "render_turn",
]
