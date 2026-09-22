"""E1 offline experiment: hotword bias vs corrupted entity ASR (T-M5-02)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from callscope.eval.compare import paired_bootstrap
from callscope.eval.scenarios import ExpandedScenario, expand_scenario, load_all_scenarios
from callscope.eval.scorers.asr import score_asr
from callscope.eval.scorers.entities import score_address, score_name
from callscope.experiments.hotwords import (
    apply_hotword_bias,
    build_hotword_list,
    corrupt_entity_hyp,
    write_hotwords_file,
)


@dataclass(frozen=True, slots=True)
class E1Item:
    item_id: str
    condition: str
    name_ref: str
    address_ref: str
    ref_transcript: str


def build_e1_items(*, seed: int = 42, n_variants: int = 3) -> list[E1Item]:
    """Train-style expansions only (variant index used as stand-in for train fold)."""
    scenarios = [
        s
        for s in load_all_scenarios()
        if "{{name}}" in str(s.slots) or "{{address}}" in str(s.slots)
    ]
    items: list[E1Item] = []
    for sc in scenarios:
        for variant in range(n_variants):
            exp: ExpandedScenario = expand_scenario(sc, seed=seed, variant=variant)
            name = str(exp.slots.get("name") or "")
            address = str(exp.slots.get("address") or "")
            if not name and not address:
                continue
            # Map variant → telephony-ish condition label for slicing
            cond = ("C0", "C1", "C2", "C3")[variant % 4]
            ref = " ".join(t.caller for t in exp.turns)
            items.append(
                E1Item(
                    item_id=f"{exp.scenario_id}-v{variant}",
                    condition=cond,
                    name_ref=name,
                    address_ref=address,
                    ref_transcript=ref,
                )
            )
    return items


def _entity_score(item: E1Item, hyp: str) -> float:
    scores: list[float] = []
    if item.name_ref:
        scores.append(score_name(item.name_ref, hyp).score)
    if item.address_ref:
        scores.append(score_address(item.address_ref, hyp).score)
    return sum(scores) / len(scores) if scores else 0.0


def run_e1(
    *,
    out_dir: Path,
    seed: int = 42,
    max_hotwords: int | None = 64,
    log_mlflow: bool = True,
) -> dict[str, Any]:
    """Run control (corrupt) vs treatment (hotword bias) once; write artifacts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    hotwords = build_hotword_list(max_words=max_hotwords)
    hw_path = out_dir / "hotwords.txt"
    write_hotwords_file(hw_path, max_words=max_hotwords)

    items = build_e1_items(seed=seed)
    control_entity: list[float] = []
    treat_entity: list[float] = []
    control_wer_c0: list[float] = []
    treat_wer_c0: list[float] = []
    rows: list[dict[str, Any]] = []

    for i, item in enumerate(items):
        # Control: garb ASR hyp from name+address refs (entity-bearing span)
        span = " ".join(x for x in (item.name_ref, item.address_ref) if x)
        corrupt = corrupt_entity_hyp(span, seed=seed + i)
        biased = apply_hotword_bias(corrupt, hotwords)
        c_ent = _entity_score(item, corrupt)
        t_ent = _entity_score(item, biased)
        control_entity.append(c_ent)
        treat_entity.append(t_ent)
        if item.condition == "C0":
            # Guardrail: on clean C0, hyp == ref (no corruption) → WER 0 both sides
            clean_hyp = item.ref_transcript
            clean_biased = apply_hotword_bias(clean_hyp, hotwords)
            control_wer_c0.append(score_asr(item.ref_transcript, clean_hyp).wer)
            treat_wer_c0.append(score_asr(item.ref_transcript, clean_biased).wer)
        rows.append(
            {
                "item_id": item.item_id,
                "condition": item.condition,
                "control_entity": c_ent,
                "treatment_entity": t_ent,
                "corrupt": corrupt,
                "biased": biased,
            }
        )

    cmp = paired_bootstrap(
        control_entity,
        treat_entity,
        margin=0.05,
        direction="higher_better",
        seed=seed,
    )
    mean_c = sum(control_entity) / len(control_entity) if control_entity else 0.0
    mean_t = sum(treat_entity) / len(treat_entity) if treat_entity else 0.0
    delta_pp = (mean_t - mean_c) * 100.0
    wer_c = sum(control_wer_c0) / len(control_wer_c0) if control_wer_c0 else 0.0
    wer_t = sum(treat_wer_c0) / len(treat_wer_c0) if treat_wer_c0 else 0.0
    wer_delta = wer_t - wer_c

    adopt = bool(delta_pp >= 5.0 and cmp.ci_low > 0 and wer_delta <= 0.005)
    decision = "adopt" if adopt else "reject"

    mlflow_run_id: str | None = None
    if log_mlflow:
        try:
            from callscope.governance.mlflow_utils import log_eval_run

            mlflow_run_id = log_eval_run(
                experiment="callscope-e1",
                run_name="e1-hotwords",
                params={
                    "seed": str(seed),
                    "max_hotwords": str(max_hotwords or "all"),
                    "n_items": str(len(items)),
                    "hotwords_path": str(hw_path),
                },
                metrics={
                    "entity_mean_control": mean_c,
                    "entity_mean_treatment": mean_t,
                    "entity_delta_pp": delta_pp,
                    "entity_ci_low": cmp.ci_low,
                    "entity_ci_high": cmp.ci_high,
                    "wer_c0_delta": wer_delta,
                },
                tags={"experiment": "E1", "decision": decision},
            )
        except Exception as exc:  # optional extra
            mlflow_run_id = f"skipped:{exc}"

    payload: dict[str, Any] = {
        "experiment": "E1",
        "n_items": len(items),
        "n_hotwords": len(hotwords),
        "entity_mean_control": mean_c,
        "entity_mean_treatment": mean_t,
        "entity_delta_pp": delta_pp,
        "paired_bootstrap": cmp.to_dict(),
        "wer_c0_control": wer_c,
        "wer_c0_treatment": wer_t,
        "wer_c0_delta": wer_delta,
        "decision": decision,
        "success_criterion": {
            "entity_delta_pp_min": 5.0,
            "ci_low_gt_0": True,
            "wer_c0_delta_max": 0.005,
        },
        "mlflow_run_id": mlflow_run_id,
        "hotwords_path": str(hw_path),
        "rows_path": str(out_dir / "items.jsonl"),
    }
    (out_dir / "result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    with (out_dir / "items.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return payload


__all__ = ["E1Item", "build_e1_items", "run_e1"]
