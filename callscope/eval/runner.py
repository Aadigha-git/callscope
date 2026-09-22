"""Eval runner: stage-replay / text-replay over a dataset with resumable persist."""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from callscope.eval.persist import FileEvalStore, aggregate_metrics
from callscope.eval.replay import ReplayItem, ReplayMode, replay_item
from callscope.eval.scorers.nlu import score_nlu
from callscope.eval.scorers.task import score_task
from callscope.eval.scorers.tools import score_tools
from callscope.eval.types import EvalItemResult
from callscope.providers.base import BrainBackend, STTProvider, TTSProvider
from callscope.providers.budget import BudgetGuard, estimate_usd
from callscope.providers.cassettes import CassetteMode, resolve_mode

DEFAULT_PROMPT_TOKENS_PER_ITEM = 400
DEFAULT_COMPLETION_TOKENS_PER_ITEM = 120


class BizReset(Protocol):
    """Deterministic Business DB reset before each scenario (design §4.6 / biz admin)."""

    def reset(self, seed: int) -> dict[str, Any]: ...


@dataclass(slots=True)
class NoOpBizReset:
    """In-process stand-in for CI when Business API is not running."""

    last_seed: int | None = None
    calls: list[int] = field(default_factory=list)

    def reset(self, seed: int) -> dict[str, Any]:
        self.last_seed = seed
        self.calls.append(seed)
        return {"seed": seed, "fingerprint": f"noop-{seed}"}


@dataclass(frozen=True, slots=True)
class EvalRunConfig:
    dataset_id: str
    stack_version_id: str
    mode: ReplayMode
    git_sha: str
    live: bool = False
    seed: int = 42
    concurrency: int = 1
    thresholds_path: Path | None = None
    estimated_usd: float | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EvalRunResult:
    run_id: str
    status: str
    n_items: int
    n_finished: int
    estimated_usd: float | None
    metrics: list[dict[str, Any]]
    store_path: Path


def resolve_git_sha(*, explicit: str | None = None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("CALLSCOPE_GIT_SHA") or os.environ.get("GITHUB_SHA")
    if env:
        return env.strip()
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return out.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def thresholds_sha256(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def estimate_eval_usd(
    n_items: int,
    *,
    model: str | None = None,
    prompt_tokens: int = DEFAULT_PROMPT_TOKENS_PER_ITEM,
    completion_tokens: int = DEFAULT_COMPLETION_TOKENS_PER_ITEM,
) -> float:
    """Projected Token Factory spend for a live eval run (no network)."""
    model_id = model or "nvidia/Nemotron-3_5-Lightning"
    per = estimate_usd(prompt_tokens, completion_tokens, model=model_id)
    return round(per * max(n_items, 0), 8)


def load_golden_items(path: Path) -> list[ReplayItem]:
    """Load ``tests/golden/eval_items.json`` (list or ``{items: [...]}``)."""
    import json

    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw["items"] if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ValueError(f"golden items must be a list: {path}")
    out: list[ReplayItem] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"item {i} must be an object")
        out.append(
            ReplayItem(
                item_id=str(row.get("item_id") or f"golden-{i:02d}"),
                text=str(row["text"]),
                scenario_id=str(row.get("scenario_id") or ""),
                voice=str(row.get("voice") or "v0"),
                condition=str(row.get("condition") or "C0"),
                variant=int(row.get("variant") or 0),
                intent=str(row.get("intent") or ""),
                slots=dict(row.get("slots") or {}),
            )
        )
    return out


def _enrich_scores(item: ReplayItem, result: EvalItemResult) -> EvalItemResult:
    """Attach NLU/tools/task scores into ``detail`` (predictions default empty for mock)."""
    nlu = score_nlu(
        intent_ref=item.intent or "unknown",
        intent_hyp=str(result.detail.get("intent_hyp") or item.intent or "unknown"),
        slots_ref=item.slots,
        slots_hyp=dict(result.slots_pred or item.slots),
    )
    tools = score_tools(
        expected=list(result.detail.get("tool_calls_ref") or []),
        predicted=list(result.tool_calls_pred or []),
    )
    task = score_task(
        expected_final_state=dict(result.detail.get("final_state_ref") or {}),
        actual_final_state=dict(result.detail.get("final_state_hyp") or {}),
        tool_calls_pred=list(result.tool_calls_pred or []),
    )
    result.detail["nlu"] = nlu.to_dict()
    result.detail["tools"] = tools.to_dict()
    result.detail["task"] = task.to_dict()
    return result


async def run_eval(
    items: Sequence[ReplayItem],
    *,
    store: FileEvalStore,
    stt: STTProvider,
    brain: BrainBackend,
    tts: TTSProvider,
    config: EvalRunConfig,
    biz: BizReset | None = None,
    ref_asr: STTProvider | None = None,
    stt_factory: Callable[[ReplayItem], STTProvider] | None = None,
    resume_run_id: str | None = None,
    budget: BudgetGuard | None = None,
) -> EvalRunResult:
    """Replay ``items``; persist per-item results; skip finished when resumable."""
    mode = resolve_mode(live=config.live)
    estimated: float | None
    if mode is not CassetteMode.REPLAY and config.live:
        projected = config.estimated_usd
        if projected is None:
            projected = estimate_eval_usd(len(items), model=budget.model if budget else None)
        guard = budget or BudgetGuard.from_settings()
        guard.require_live_budget(projected)
        estimated = guard.estimated_usd_for_eval_run(projected)
    else:
        estimated = config.estimated_usd
        if estimated is None and config.live:
            estimated = estimate_eval_usd(len(items))

    thr = thresholds_sha256(config.thresholds_path)
    if resume_run_id:
        run = store.load(resume_run_id)
        run_id = run.run_id
        done = set(run.item_results)
    else:
        run = store.create_run(
            dataset_id=config.dataset_id,
            stack_version_id=config.stack_version_id,
            mode=config.mode,
            git_sha=config.git_sha,
            config={
                **config.config,
                "seed": config.seed,
                "concurrency": config.concurrency,
                "live": config.live,
                "cassette_mode": str(mode),
            },
            thresholds_sha256=thr,
            estimated_usd=estimated,
        )
        run_id = run.run_id
        done = set()

    biz_reset = biz or NoOpBizReset()
    sem = asyncio.Semaphore(max(1, config.concurrency))
    lock = asyncio.Lock()

    async def _one(item: ReplayItem) -> None:
        if item.item_id in done:
            return
        async with sem:
            seed = config.seed + (hash(item.scenario_id or item.item_id) % 10_000)
            biz_reset.reset(seed)
            provider_stt = stt_factory(item) if stt_factory is not None else stt
            result = await replay_item(
                item,
                mode=config.mode,
                stt=provider_stt,
                brain=brain,
                tts=tts,
                ref_asr=ref_asr or provider_stt,
            )
            result = _enrich_scores(item, result)
            async with lock:
                store.write_item(run_id, item.item_id, result)

    await asyncio.gather(*[_one(it) for it in items])

    final = store.load(run_id)
    metrics = aggregate_metrics(final.item_results)
    # Extra slice metrics
    by_voice: dict[str, list[float]] = {}
    by_scenario: dict[str, list[float]] = {}
    for row in final.item_results.values():
        wer = row.get("wer")
        if wer is None:
            continue
        detail = row.get("detail") or {}
        by_voice.setdefault(str(detail.get("voice") or "unknown"), []).append(float(wer))
        by_scenario.setdefault(str(detail.get("scenario_id") or "unknown"), []).append(float(wer))
    for voice, vals in sorted(by_voice.items()):
        metrics.append(
            {
                "metric": "wer",
                "slice": f"voice={voice}",
                "value": sum(vals) / len(vals),
                "n": len(vals),
            }
        )
    for sc, vals in sorted(by_scenario.items()):
        metrics.append(
            {
                "metric": "wer",
                "slice": f"scenario={sc}",
                "value": sum(vals) / len(vals),
                "n": len(vals),
            }
        )
    final = store.finalize(run_id, status="succeeded", metrics=metrics)
    return EvalRunResult(
        run_id=final.run_id,
        status=final.status,
        n_items=len(items),
        n_finished=len(final.item_results),
        estimated_usd=final.estimated_usd,
        metrics=final.metrics,
        store_path=store.path_for(final.run_id),
    )


__all__ = [
    "BizReset",
    "EvalRunConfig",
    "EvalRunResult",
    "NoOpBizReset",
    "estimate_eval_usd",
    "load_golden_items",
    "resolve_git_sha",
    "run_eval",
    "thresholds_sha256",
]
