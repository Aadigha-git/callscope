"""Optional LLM judge for residual claims; gated by calibration agreement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from callscope.providers.base import BrainBackend, Msg
from callscope.providers.budget import DEFAULT_MODEL, BudgetGuard

JudgeLabel = Literal["supported", "unsupported", "borderline"]

DEFAULT_CALIBRATION = Path("eval/judge_calibration.jsonl")
DEFAULT_MIN_KAPPA = 0.8
# Must differ from agent default (Nemotron Lightning) per task acceptance.
DEFAULT_JUDGE_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"


@dataclass(frozen=True, slots=True)
class JudgeVerdict:
    label: JudgeLabel
    rationale: str
    model: str

    def to_dict(self) -> dict[str, Any]:
        return {"label": self.label, "rationale": self.rationale, "model": self.model}


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    n: int
    agreement: float
    cohens_kappa: float
    enabled: bool
    threshold: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "agreement": self.agreement,
            "cohens_kappa": self.cohens_kappa,
            "enabled": self.enabled,
            "threshold": self.threshold,
        }


def cohens_kappa(y_true: list[str], y_pred: list[str]) -> float:
    """Cohen's kappa for nominal labels (multi-class)."""
    if len(y_true) != len(y_pred) or not y_true:
        return 0.0
    labels = sorted(set(y_true) | set(y_pred))
    n = len(y_true)
    idx = {lab: i for i, lab in enumerate(labels)}
    k = len(labels)
    matrix = [[0] * k for _ in range(k)]
    for a, b in zip(y_true, y_pred, strict=True):
        matrix[idx[a]][idx[b]] += 1
    po = sum(matrix[i][i] for i in range(k)) / n
    row = [sum(matrix[i][j] for j in range(k)) for i in range(k)]
    col = [sum(matrix[i][j] for i in range(k)) for j in range(k)]
    pe = sum((row[i] / n) * (col[i] / n) for i in range(k))
    if abs(1.0 - pe) < 1e-12:
        return 1.0 if po == 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def load_calibration(path: Path | None = None) -> list[dict[str, Any]]:
    p = path or DEFAULT_CALIBRATION
    if not p.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def calibrate_judge(
    path: Path | None = None,
    *,
    min_kappa: float = DEFAULT_MIN_KAPPA,
    label_key: str = "human_label",
    pred_key: str = "judge_label",
) -> CalibrationReport:
    """Compute agreement vs human labels; enable judge only if kappa >= threshold."""
    rows = load_calibration(path)
    humans = [str(r.get(label_key) or "") for r in rows]
    preds = [str(r.get(pred_key) or "") for r in rows]
    n = len(rows)
    if n == 0:
        return CalibrationReport(0, 0.0, 0.0, False, min_kappa)
    agree = sum(1 for a, b in zip(humans, preds, strict=True) if a == b) / n
    kappa = cohens_kappa(humans, preds)
    enabled = n >= 50 and kappa >= min_kappa
    return CalibrationReport(n, agree, kappa, enabled, min_kappa)


async def judge_claim(
    claim_text: str,
    *,
    evidence: str,
    brain: BrainBackend,
    model: str = DEFAULT_JUDGE_MODEL,
    agent_model: str = DEFAULT_MODEL,
    budget: BudgetGuard | None = None,
    projected_usd: float = 0.002,
) -> JudgeVerdict:
    """Ask judge model whether claim is supported. Requires different model than agent."""
    if model == agent_model:
        raise ValueError(
            f"judge model must differ from agent model ({agent_model!r}); got {model!r}"
        )
    if budget is not None:
        budget.require_live_budget(projected_usd)
    prompt = (
        "You are a factuality judge for a fictional home-services receptionist. "
        "Reply with exactly one line: LABEL|<supported|unsupported|borderline>|short reason.\n"
        f"EVIDENCE:\n{evidence}\n\nCLAIM:\n{claim_text}\n"
    )
    parts: list[str] = []
    async for delta in brain.stream_reply(
        [Msg(role="user", content=prompt)],
        call_id="judge",
        turn_id="j1",
    ):
        if delta.kind == "text" and delta.text:
            parts.append(delta.text)
    raw = "".join(parts).strip()
    label: JudgeLabel = "borderline"
    rationale = raw
    if "unsupported" in raw.lower():
        label = "unsupported"
    elif "supported" in raw.lower() and "unsupported" not in raw.lower():
        label = "supported"
    return JudgeVerdict(label=label, rationale=rationale[:500], model=model)


def judge_enabled(path: Path | None = None) -> bool:
    return calibrate_judge(path).enabled


__all__ = [
    "DEFAULT_CALIBRATION",
    "DEFAULT_JUDGE_MODEL",
    "DEFAULT_MIN_KAPPA",
    "CalibrationReport",
    "JudgeVerdict",
    "calibrate_judge",
    "cohens_kappa",
    "judge_claim",
    "judge_enabled",
    "load_calibration",
]
