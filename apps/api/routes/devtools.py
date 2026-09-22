"""Devtools seed endpoint for the review console demo."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from apps.api.deps import StateDep, require_service_token

router = APIRouter(dependencies=[Depends(require_service_token)])


class SeedReviewRequest(BaseModel):
    n: int = Field(default=40, ge=1, le=200)
    reviewer: str = "seed-demo"


class SeedReviewResponse(BaseModel):
    created: int
    labelled: int
    call_ids: list[str]


@router.post("/v1/devtools/seed-review", response_model=SeedReviewResponse, status_code=201)
async def seed_review(body: SeedReviewRequest, state: StateDep) -> SeedReviewResponse:
    result = state.review.seed_review_demo(n=body.n, reviewer=body.reviewer)
    return SeedReviewResponse(
        created=int(result["created"]),
        labelled=int(result["labelled"]),
        call_ids=list(result["call_ids"]),
    )
