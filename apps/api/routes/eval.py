"""Evaluation run list/create/detail/compare routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from apps.api.deps import StateDep, require_service_token
from apps.api.review_store import EvalRunRecord
from apps.api.schemas import (
    CompareDeltaOut,
    EvalRunCreate,
    EvalRunDetailOut,
    EvalRunOut,
    MetricOut,
)

router = APIRouter(dependencies=[Depends(require_service_token)])


def _run_out(run: EvalRunRecord) -> EvalRunOut:
    return EvalRunOut(
        run_id=run.run_id,
        dataset_id=run.dataset_id,
        stack_version_id=run.stack_version_id,
        mode=run.mode,
        status=run.status,
        git_sha=run.git_sha,
        estimated_usd=run.estimated_usd,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


@router.get("/v1/eval/runs", response_model=list[EvalRunOut])
async def list_eval_runs(state: StateDep) -> list[EvalRunOut]:
    return [_run_out(r) for r in state.review.list_eval_runs()]


@router.post("/v1/eval/runs", response_model=EvalRunOut, status_code=202)
async def create_eval_run(body: EvalRunCreate, state: StateDep) -> EvalRunOut:
    run = state.review.create_eval_run(
        dataset_id=body.dataset_id,
        stack_version_id=body.stack_version_id,
        mode=body.mode,
    )
    return _run_out(run)


@router.get("/v1/eval/runs/{run_id}", response_model=EvalRunDetailOut)
async def get_eval_run(run_id: UUID, state: StateDep) -> EvalRunDetailOut:
    run = state.review.get_eval_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="unknown run_id")
    base = _run_out(run)
    metrics = [MetricOut.model_validate(m) for m in run.metrics]
    return EvalRunDetailOut(**base.model_dump(), metrics=metrics)


@router.get("/v1/eval/compare", response_model=list[CompareDeltaOut])
async def compare_eval_runs(
    state: StateDep,
    a: Annotated[UUID, Query()],
    b: Annotated[UUID, Query()],
) -> list[CompareDeltaOut]:
    deltas = state.review.compare_runs(a, b)
    if deltas is None:
        raise HTTPException(status_code=404, detail="unknown run id(s)")
    return [CompareDeltaOut.model_validate(d) for d in deltas]
