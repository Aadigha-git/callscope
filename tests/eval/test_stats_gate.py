"""Bootstrap CI coverage, paired compare, and regression gate (T-M3-06)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from callscope.eval.compare import paired_bootstrap, paired_bootstrap_ratio
from callscope.eval.gate import (
    DEFAULT_LOCK,
    DEFAULT_THRESHOLDS,
    gate_run,
    gate_vs_baseline,
    load_thresholds,
    read_thresholds_lock,
    thresholds_file_sha256,
)
from callscope.eval.persist import FileEvalStore
from callscope.eval.stats import (
    bootstrap_mean,
    bootstrap_percentile,
    bootstrap_ratio,
    ci_width_note,
)

pytestmark = pytest.mark.unit


def test_bootstrap_mean_covers_truth() -> None:
    rng = np.random.default_rng(0)
    # Known mean 0.5; CI should usually contain 0.5
    hits = 0
    trials = 40
    for t in range(trials):
        x = rng.normal(0.5, 0.1, size=80)
        r = bootstrap_mean(x.tolist(), n_boot=400, seed=100 + t)
        if r.ci_low <= 0.5 <= r.ci_high:
            hits += 1
    # Expect ~95%; allow slack for 40 trials
    assert hits / trials >= 0.80


def test_bootstrap_ratio_wer_not_mean_of_rates() -> None:
    # Two calls: 1/10 and 9/10 → mean of WERs = 0.5, true WER = 10/20 = 0.5
    # Uneven: 0/10 and 5/10 → mean rates 0.25, ratio 5/20 = 0.25 — same.
    # Distinct case: 1/2 and 1/100 → mean of rates ≈ 0.505, ratio 2/102 ≈ 0.0196
    nums = [1.0, 1.0]
    dens = [2.0, 100.0]
    r = bootstrap_ratio(nums, dens, n_boot=200, seed=1)
    assert abs(r.estimate - (2.0 / 102.0)) < 1e-9
    mean_rates = (1 / 2 + 1 / 100) / 2
    assert abs(r.estimate - mean_rates) > 0.2


def test_bootstrap_percentile_p95() -> None:
    vals = list(range(100))
    r = bootstrap_percentile(vals, q=95, n_boot=300, seed=2)
    assert 90.0 <= r.estimate <= 99.0


def test_paired_non_inferior_and_regression() -> None:
    base = [0.05] * 40
    good = [0.04] * 40
    ok = paired_bootstrap(base, good, margin=0.01, direction="lower_better", n_boot=300)
    assert ok.non_inferior is True
    bad = [0.20] * 40
    reg = paired_bootstrap(base, bad, margin=0.01, direction="lower_better", n_boot=300)
    assert reg.non_inferior is False


def test_paired_ratio_regression() -> None:
    bn, bd = [1.0] * 30, [20.0] * 30
    cn, cd = [5.0] * 30, [20.0] * 30
    r = paired_bootstrap_ratio(bn, bd, cn, cd, margin=0.01, n_boot=200, seed=3)
    assert r.non_inferior is False


def test_gate_passes_and_planted_regression(tmp_path: Path) -> None:
    thr = load_thresholds(DEFAULT_THRESHOLDS)
    store = FileEvalStore(tmp_path / "runs")
    good = store.create_run(
        dataset_id="d",
        stack_version_id="s",
        mode="stage_replay",
        git_sha="a",
    )
    good.metrics = [
        {"metric": "wer", "slice": "cond=C0", "value": 0.05, "n": 10},
        {"metric": "wer", "slice": "cond=C1", "value": 0.10, "n": 10},
        {"metric": "wer", "slice": "cond=C3", "value": 0.15, "n": 10},
        {"metric": "task_success", "slice": "all", "value": 0.90, "n": 10},
        {"metric": "phone_seq_acc", "slice": "cond=C0", "value": 0.95, "n": 10},
        {"metric": "phone_seq_acc", "slice": "cond=C1", "value": 0.85, "n": 10},
        {"metric": "intent_macro_f1", "slice": "all", "value": 0.95, "n": 10},
        {"metric": "slot_f1", "slice": "all", "value": 0.92, "n": 10},
        {"metric": "tool_arg_acc", "slice": "all", "value": 0.93, "n": 10},
        {"metric": "unconfirmed_mutations", "slice": "all", "value": 0.0, "n": 10},
        {"metric": "hallucination_rate", "slice": "all", "value": 0.01, "n": 10},
        {"metric": "injection_success", "slice": "all", "value": 0.0, "n": 10},
        {"metric": "premature_endpoint", "slice": "all", "value": 0.02, "n": 10},
        {"metric": "false_barge_in", "slice": "all", "value": 0.01, "n": 10},
        {"metric": "missed_barge_in", "slice": "all", "value": 0.02, "n": 10},
    ]
    store.save(good)
    report = gate_run(store.load(good.run_id), thr, require_metric=True)
    assert report.passed, report.to_table()

    bad = store.create_run(
        dataset_id="d",
        stack_version_id="s2",
        mode="stage_replay",
        git_sha="b",
    )
    bad.metrics = list(good.metrics)
    # Plant WER regression on C0
    bad.metrics = [
        {**m, "value": 0.50} if m["metric"] == "wer" and m["slice"] == "cond=C0" else m
        for m in bad.metrics
    ]
    store.save(bad)
    fail = gate_run(store.load(bad.run_id), thr, require_metric=True)
    assert fail.passed is False
    assert any(c.gate_id == "wer_c0" and not c.passed for c in fail.checks)


def test_gate_vs_baseline_planted_ni_fail(tmp_path: Path) -> None:
    thr = load_thresholds(DEFAULT_THRESHOLDS)
    store = FileEvalStore(tmp_path / "runs")
    base = store.create_run(dataset_id="d", stack_version_id="s", mode="text_replay", git_sha="a")
    cand = store.create_run(dataset_id="d", stack_version_id="s2", mode="text_replay", git_sha="b")
    base.metrics = [{"metric": "wer", "slice": "all", "value": 0.05, "n": 20}]
    cand.metrics = [{"metric": "wer", "slice": "all", "value": 0.20, "n": 20}]
    # Minimal absolute gates: skip missing
    store.save(base)
    store.save(cand)
    pb = [0.05] * 20
    pc = [0.20] * 20
    report = gate_vs_baseline(
        store.load(base.run_id),
        store.load(cand.run_id),
        thr,
        per_call_baseline={"wer": pb},
        per_call_candidate={"wer": pc},
    )
    assert any(c.gate_id == "ni_wer" and not c.passed for c in report.compare_checks)


def test_thresholds_lock_matches_file() -> None:
    digest = thresholds_file_sha256(DEFAULT_THRESHOLDS)
    assert read_thresholds_lock(DEFAULT_LOCK) == digest


def test_ci_width_note_mentions_n() -> None:
    note = ci_width_note(n_calls=120, n_recorded=30)
    assert "120" in note and "30" in note and "sqrt" in note


def test_eval_cli_gate_exit_codes(tmp_path: Path) -> None:
    from callscope.devtools import eval_cli

    thr = load_thresholds(DEFAULT_THRESHOLDS)
    store = FileEvalStore(tmp_path)
    run = store.create_run(dataset_id="d", stack_version_id="s", mode="stage_replay", git_sha="x")
    run.metrics = [
        {"metric": "wer", "slice": "cond=C0", "value": 0.50, "n": 5},
    ]
    store.save(run)
    # Without --require-metric, missing metrics skip → may still fail on wer_c0
    rc = eval_cli.main(
        [
            "gate",
            "--run",
            run.run_id,
            "--out",
            str(tmp_path),
            "--thresholds",
            str(DEFAULT_THRESHOLDS),
        ]
    )
    assert rc == 1
    _ = thr
