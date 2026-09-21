"""Dataset builder / telephony augmentation tests (T-M3-03)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from callscope.datasets.augment import apply_condition
from callscope.datasets.io_audio import (
    SAMPLE_RATE_HZ,
    apply_c1,
    audio_sha256,
    coloured_noise,
    highband_energy_ratio,
    measured_snr_db,
    mix_snr,
    peak,
)
from callscope.datasets.synth import (
    CI_WIDTH_NOTE,
    DEFAULT_N_CALLS,
    DEFAULT_VOICES,
    SynthVoiceTTS,
    build_dataset,
    plan_calls,
)
from callscope.eval.scenarios import load_all_scenarios


def _tone(sr: int = SAMPLE_RATE_HZ, seconds: float = 1.0, f0: float = 440.0) -> np.ndarray:
    t = np.arange(int(sr * seconds), dtype=np.float64) / sr
    return (0.5 * np.sin(2 * np.pi * f0 * t)).astype(np.float32)


def test_default_size_and_voices() -> None:
    assert DEFAULT_N_CALLS == 120
    assert len(DEFAULT_VOICES) >= 6
    assert "120" in CI_WIDTH_NOTE


def test_snr_within_half_db() -> None:
    clean = _tone()
    rng = np.random.default_rng(0)
    noise = coloured_noise(len(clean), rng)
    for snr in (20.0, 10.0, 5.0):
        mixed = mix_snr(clean, noise, snr)
        got = measured_snr_db(clean, mixed)
        assert abs(got - snr) <= 0.5, (snr, got)


def test_c1_highband_suppressed() -> None:
    # Broadband-ish input: mix of tones including 5 kHz
    sr = SAMPLE_RATE_HZ
    t = np.arange(sr, dtype=np.float64) / sr
    wide = (0.4 * np.sin(2 * np.pi * 1000 * t) + 0.4 * np.sin(2 * np.pi * 5000 * t)).astype(
        np.float32
    )
    before = highband_energy_ratio(wide, sr, 3600.0)
    after, sr2 = apply_c1(wide, sr)
    assert sr2 == SAMPLE_RATE_HZ
    after_r = highband_energy_ratio(after, sr2, 3600.0)
    assert after_r < 0.05
    assert after_r < before


def test_c5_frame_loss_ratio() -> None:
    audio = _tone(seconds=10.0)
    out, rec = apply_condition(audio, condition="C5", seed=7)
    assert rec.frame_loss_measured is not None
    assert abs(rec.frame_loss_measured - 0.05) < 0.025
    assert peak(out) <= 0.99


def test_determinism_same_hash(tmp_path: Path) -> None:
    a = build_dataset(out_dir=tmp_path / "a", n_calls=6, seed=99)
    b = build_dataset(out_dir=tmp_path / "b", n_calls=6, seed=99)
    hashes_a = [i["audio_sha256"] for i in a["items"]]
    hashes_b = [i["audio_sha256"] for i in b["items"]]
    assert hashes_a == hashes_b
    # Direct audio hash
    tone = _tone()
    x1, _ = apply_condition(tone, condition="C2", seed=1)
    x2, _ = apply_condition(tone, condition="C2", seed=1)
    assert audio_sha256(x1, SAMPLE_RATE_HZ) == audio_sha256(x2, SAMPLE_RATE_HZ)


def test_no_clipping_on_augment() -> None:
    loud = _tone() * 0.95
    for cond in ("C0", "C1", "C2", "C3", "C4", "C5"):
        out, _ = apply_condition(loud, condition=cond, seed=3)  # type: ignore[arg-type]
        assert peak(out) < 0.99


def test_plan_and_synth_tts() -> None:
    scs = load_all_scenarios()
    plan = plan_calls(scs, n_calls=12, seed=1)
    assert len(plan) == 12
    tts = SynthVoiceTTS()
    wav = tts.synthesize("hello five five five", voice=DEFAULT_VOICES[0], seed=0)
    assert wav.ndim == 1 and wav.size > 100
    assert peak(wav) < 0.99


def test_build_small_dataset(tmp_path: Path) -> None:
    man = build_dataset(out_dir=tmp_path, n_calls=12, seed=5)
    assert man["n_calls"] == 12
    assert (tmp_path / "manifest.json").exists()
    assert len(list((tmp_path / "audio").glob("*.wav"))) == 12


def test_cli_build(tmp_path: Path) -> None:
    from callscope.devtools.dataset_cli import main

    out = tmp_path / "ds"
    spec = Path("eval/dataset_specs/v1.yaml")
    rc = main(["build", "--spec", str(spec), "--out", str(out), "--n", "6", "--seed", "2"])
    assert rc == 0
    assert (out / "manifest.json").exists()
