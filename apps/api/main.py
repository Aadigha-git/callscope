"""CallScope API FastAPI application."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from apps.api.deps import ApiState, build_api_state
from apps.api.errors import problem
from apps.api.routes import router
from callscope.observability.logging import call_id_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[..., object]) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        # Bind call_id from path when present (sessions/{id}/end).
        call_id = request.path_params.get("call_id") if request.path_params else None
        token = call_id_var.set(str(call_id) if call_id else None)
        try:
            response = await call_next(request)  # type: ignore[misc]
            if not isinstance(response, Response):
                raise TypeError("middleware expected Response")
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            call_id_var.reset(token)


def create_app(state: ApiState | None = None) -> FastAPI:
    api_state = state or build_api_state()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.api = api_state
        yield

    app = FastAPI(title="CallScope API", version="0.1.0", lifespan=lifespan)
    app.state.api = api_state
    app.add_middleware(RequestIdMiddleware)
    app.include_router(router)

    @app.exception_handler(HTTPException)
    async def http_exc_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        code = "http_error"
        if exc.status_code == 401:
            code = "unauthorized"
        return problem(
            status=exc.status_code,
            title=exc.detail if isinstance(exc.detail, str) else "Error",
            detail=exc.detail if isinstance(exc.detail, str) else None,
            code=code,
            headers=dict(exc.headers) if exc.headers else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(
            status=422,
            title="Unprocessable Entity",
            detail=str(exc.errors()),
            code="validation_error",
        )

    return app


app = create_app()
