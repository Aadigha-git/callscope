"""DQ / splits / manifest / registry tests (T-M3-04)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from callscope.datasets.dq import (
    check_duplicate_hashes,
    check_split_leakage,
    run_dq,
)
from callscope.datasets.io_audio import SAMPLE_RATE_HZ, write_wav
from callscope.datasets.manifest import (
    attach_splits_and_dq,
    manifest_sha256,
    write_manifest,
)
from callscope.datasets.registry import FileRegistry, RegistryError
from callscope.datasets.splits import assign_splits
from callscope.datasets.synth import build_dataset
from callscope.devtools import dataset_cli

pytestmark = pytest.mark.unit


def _tone(path: Path, seconds: float = 1.0) -> None:
    t = np.arange(int(SAMPLE_RATE_HZ * seconds), dtype=np.float64) / SAMPLE_RATE_HZ
    audio = (0.3 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    write_wav(path, audio, SAMPLE_RATE_HZ)


def test_split_leakage_detects_planted_leak() -> None:
    items = [
        {"item_id": "a", "voice": "v1", "scenario_id": "s", "variant": 0, "split": "train"},
        {"item_id": "b", "voice": "v1", "scenario_id": "s", "variant": 0, "split": "dev"},
    ]
    findings = check_split_leakage(items)
    assert any(f.check == "split_leakage" and f.severity == "error" for f in findings)


def test_assign_splits_no_leakage() -> None:
    items = []
    voices = [f"v{i}" for i in range(6)]
    for i in range(60):
        items.append(
            {
                "item_id": f"i{i}",
                "scenario_id": f"sc{i % 8}",
                "variant": i % 3,
                "voice": voices[i % 6],
                "condition": "C0",
                "audio_sha256": f"h{i}",
                "text": "hello world " * 5,
            }
        )
    plan = assign_splits(items, seed=1, train_n=30, dev_n=10, test_n=10)
    assert plan.counts()["train"] >= 1
    leaks = check_split_leakage(plan.all_items())
    assert leaks == []
    assert len(plan.held_voices) == 2
    assert len(plan.held_variants) == 2


def test_manifest_hash_stable(tmp_path: Path) -> None:
    man = {
        "version": 1,
        "n_calls": 2,
        "seed": 1,
        "voices": ["a", "b"],
        "conditions": ["C0"],
        "items": [
            {"audio_sha256": "bbb"},
            {"audio_sha256": "aaa"},
        ],
    }
    h1 = manifest_sha256(man)
    h2 = manifest_sha256(man)
    assert h1 == h2
    path = tmp_path / "manifest.json"
    write_manifest(path, man)
    again = manifest_sha256(
        {
            **man,
            "items": [{"audio_sha256": "aaa"}, {"audio_sha256": "bbb"}],
        }
    )
    assert again == h1  # sorted item hashes


def test_duplicate_hash_finding() -> None:
    items = [
        {"item_id": "1", "audio_sha256": "deadbeef"},
        {"item_id": "2", "audio_sha256": "deadbeef"},
    ]
    assert check_duplicate_hashes(items)


def test_run_dq_on_built_dataset(tmp_path: Path) -> None:
    out = tmp_path / "ds"
    build_dataset(out_dir=out, n_calls=12, seed=3)
    man = (out / "manifest.json").read_text(encoding="utf-8")
    import json

    items = json.loads(man)["items"]
    plan = assign_splits(items, seed=3, train_n=6, dev_n=2, test_n=2)
    report = run_dq(plan.all_items(), audio_root=out)
    assert report.n_items == len(plan.all_items())
    # Synthetic beeps should pass core gates
    errors = [f for f in report.findings if f.severity == "error"]
    assert errors == [], errors


def test_registry_refuse_dq_fail_and_frozen(tmp_path: Path) -> None:
    reg = FileRegistry(tmp_path)
    bad = {
        "dq_passed": False,
        "manifest_sha256": "abc",
        "dq_report": {},
        "items": [],
    }
    with pytest.raises(RegistryError, match="dq_passed"):
        reg.publish(name="x", version="1", manifest_uri="m", manifest=bad)

    good = {
        "dq_passed": True,
        "manifest_sha256": "abc",
        "dq_report": {"dq_passed": True},
        "items": [{"item_id": "1", "split": "train", "scenario_id": "s", "variant": 0}],
    }
    entry = reg.publish(name="x", version="1", manifest_uri="m.json", manifest=good)
    assert not entry.frozen
    reg.freeze("x", "1")
    with pytest.raises(RegistryError, match="frozen"):
        reg.publish(name="x", version="1", manifest_uri="m.json", manifest=good)
    with pytest.raises(RegistryError, match="frozen"):
        reg.assert_mutable("x", "1")


def test_cli_validate_publish_freeze(tmp_path: Path) -> None:
    ds = tmp_path / "ds"
    build_dataset(out_dir=ds, n_calls=12, seed=5)
    rc = dataset_cli.main(["validate", "--dataset", str(ds), "--seed", "5"])
    assert rc == 0
    import json

    man = json.loads((ds / "manifest.json").read_text(encoding="utf-8"))
    assert man["dq_passed"] is True
    assert "manifest_sha256" in man
    h1 = man["manifest_sha256"]
    # rewrite same content -> stable hash
    enriched = attach_splits_and_dq(
        man,
        items=man["items"],
        dq_report=man["dq_report"],
        held_voices=tuple(man.get("held_voices") or []),
        held_variants=tuple(man.get("held_variants") or []),
    )
    assert enriched["manifest_sha256"] == h1

    reg_root = tmp_path / "reg"
    rc = dataset_cli.main(
        [
            "publish",
            "--dataset",
            str(ds),
            "--name",
            "syn",
            "--version",
            "v1",
            "--registry",
            str(reg_root),
        ]
    )
    assert rc == 0
    rc = dataset_cli.main(
        ["freeze", "--name", "syn", "--version", "v1", "--registry", str(reg_root)]
    )
    assert rc == 0
    rc = dataset_cli.main(
        [
            "publish",
            "--dataset",
            str(ds),
            "--name",
            "syn",
            "--version",
            "v1",
            "--registry",
            str(reg_root),
        ]
    )
    assert rc == 1


def test_duration_and_format_negative(tmp_path: Path) -> None:
    wav = tmp_path / "short.wav"
    write_wav(wav, np.zeros(10, dtype=np.float32), SAMPLE_RATE_HZ)
    item = {
        "item_id": "x",
        "scenario_id": "s",
        "voice": "v",
        "condition": "C0",
        "audio_sha256": "z",
        "text": "hi",
        "wav_relpath": "short.wav",
    }
    report = run_dq([item], audio_root=tmp_path)
    assert report.dq_passed is False
    assert any(f.check == "duration_bounds" for f in report.findings)
