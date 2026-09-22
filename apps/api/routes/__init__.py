"""Compose CallScope API routers."""

from __future__ import annotations

from fastapi import APIRouter

from apps.api.routes import calls, devtools, labels, models, sessions
from apps.api.routes import eval as eval_routes

router = APIRouter()
router.include_router(sessions.router)
router.include_router(calls.router)
router.include_router(labels.router)
router.include_router(eval_routes.router)
router.include_router(models.router)
router.include_router(devtools.router)

__all__ = ["router"]
