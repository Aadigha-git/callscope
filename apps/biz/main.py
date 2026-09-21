"""Business API FastAPI application (Lakeside Home Services)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from apps.biz.routes import router
from apps.biz.store import seed_store


def create_app(*, seed: int | None = None) -> FastAPI:
    initial_seed = seed if seed is not None else int(os.environ.get("CALLSCOPE_BIZ_SEED", "42"))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.store = seed_store(initial_seed)
        yield

    app = FastAPI(
        title="Lakeside Home Services Business API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.store = seed_store(initial_seed)
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_exc(_request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "code": "biz_error"},
        )

    @app.exception_handler(RequestValidationError)
    async def validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors(), "code": "validation_error"},
        )

    return app


app = create_app()
