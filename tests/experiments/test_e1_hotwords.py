"""E1 hotword experiment unit tests (T-M5-02)."""

from __future__ import annotations

from pathlib import Path

import pytest

from callscope.experiments.e1 import run_e1
from callscope.experiments.hotwords import (
    apply_hotword_bias,
    build_hotword_list,
    corrupt_entity_hyp,
    write_hotwords_file,
)

pytestmark = pytest.mark.unit


def test_hotwords_from_seed_pools_not_empty() -> None:
    words = build_hotword_list()
    assert "Maple Street" in words or "Maple" in words
    assert any("HVAC" in w or "Plumbing" in w for w in words)
    assert "98101" in words


def test_hotwords_file_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "hw.txt"
    words = write_hotwords_file(path, max_words=10)
    assert path.is_file()
    assert len(words) <= 10


def test_corrupt_and_bias_improves_address() -> None:
    ref = "123 Maple Street"
    corrupt = corrupt_entity_hyp(ref, seed=1)
    assert corrupt.casefold() != ref.casefold()
    biased = apply_hotword_bias(corrupt, ["Maple Street"])
    assert "Maple Street" in biased


def test_run_e1_writes_result(tmp_path: Path) -> None:
    result = run_e1(out_dir=tmp_path, seed=7, max_hotwords=48, log_mlflow=False)
    assert result["n_items"] > 0
    assert result["decision"] in {"adopt", "reject"}
    assert (tmp_path / "result.json").is_file()
    assert (tmp_path / "hotwords.txt").is_file()
    # Guardrail: C0 WER must not regress beyond margin on clean path
    assert float(result["wer_c0_delta"]) <= 0.005
