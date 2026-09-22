"""Model inventory and lifecycle transition routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import StateDep, require_service_token
from apps.api.review_store import ModelVersionRecord
from apps.api.schemas import ModelTransitionRequest, ModelVersionCreate, ModelVersionOut

router = APIRouter(dependencies=[Depends(require_service_token)])


def _model_out(m: ModelVersionRecord) -> ModelVersionOut:
    return ModelVersionOut.model_validate(
        {
            "model_version_id": m.model_version_id,
            "component": m.component,
            "name": m.name,
            "revision": m.revision,
            "owner": m.owner,
            "base_model": m.base_model,
            "license": m.license,
            "artifact_uri": m.artifact_uri,
            "config": m.config,
            "intended_use": m.intended_use,
            "out_of_scope_use": m.out_of_scope_use,
            "mlflow_run_id": m.mlflow_run_id,
            "status": m.status,
            "created_at": m.created_at,
        }
    )


@router.get("/v1/models", response_model=list[ModelVersionOut])
async def list_models(
    state: StateDep,
    component: str | None = None,
    status: str | None = None,
) -> list[ModelVersionOut]:
    return [_model_out(m) for m in state.review.list_models(component=component, status=status)]


@router.post("/v1/models", response_model=ModelVersionOut, status_code=201)
async def register_model(body: ModelVersionCreate, state: StateDep) -> ModelVersionOut:
    rec = state.review.register_model(body.model_dump())
    return _model_out(rec)


@router.post("/v1/models/{model_version_id}/transition", response_model=ModelVersionOut)
async def transition_model(
    model_version_id: UUID,
    body: ModelTransitionRequest,
    state: StateDep,
) -> ModelVersionOut:
    try:
        rec = state.review.transition_model(model_version_id, to=body.to, report_id=body.report_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if rec is None:
        raise HTTPException(status_code=404, detail="unknown model_version_id")
    return _model_out(rec)
