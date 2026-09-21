"""RFC 7807 problem+json helpers."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def problem(
    *,
    status: int,
    title: str,
    detail: str | None = None,
    code: str | None = None,
    type_uri: str = "about:blank",
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {"type": type_uri, "title": title, "status": status}
    if detail is not None:
        body["detail"] = detail
    if code is not None:
        body["code"] = code
    return JSONResponse(
        status_code=status,
        content=body,
        media_type="application/problem+json",
        headers=headers,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _ = (request, exc)
    return problem(status=500, title="Internal Server Error", code="internal")
