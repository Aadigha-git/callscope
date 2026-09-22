"""Label and labelled-dataset export routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from apps.api.deps import StateDep, require_service_token
from apps.api.schemas import ExportLabelledOut, ExportLabelledRequest, LabelOut, LabelRequest

router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/v1/calls/{call_id}/labels", response_model=LabelOut, status_code=201)
async def add_label(call_id: UUID, body: LabelRequest, state: StateDep) -> LabelOut:
    try:
        lab = state.review.add_label(call_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if lab is None:
        raise HTTPException(status_code=404, detail="unknown call_id")
    return LabelOut.model_validate(
        {
            "label_id": lab.label_id,
            "turn_id": lab.turn_id,
            "root_cause_code": lab.root_cause_code,
            "severity": lab.severity,
            "reviewer": lab.reviewer,
            "notes": lab.notes,
            "add_to_dataset": lab.add_to_dataset,
            "created_at": lab.created_at,
        }
    )


@router.post("/v1/datasets:export-labelled", response_model=ExportLabelledOut, status_code=202)
async def export_labelled(body: ExportLabelledRequest, state: StateDep) -> ExportLabelledOut:
    dataset_id = state.review.export_labelled(
        name=body.name, version=body.version, root_causes=body.root_causes
    )
    return ExportLabelledOut(dataset_id=dataset_id)
