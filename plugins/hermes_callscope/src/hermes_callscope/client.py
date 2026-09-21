"""Async HTTP client for the Lakeside Business API."""

from __future__ import annotations

import os
from typing import Any

import httpx


class BizClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout_s: float = 8.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = (
            base_url or os.environ.get("CALLSCOPE_BIZ_BASE_URL", "http://127.0.0.1:8100")
        ).rstrip("/")
        self._timeout = timeout_s
        self._client = client
        self._owns = client is None

    async def aclose(self) -> None:
        if self._owns and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _get(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        resp = await self._get().get(f"{self._base}{path}", params=params)
        return {"status_code": resp.status_code, "body": _safe_json(resp)}

    async def post_json(
        self,
        path: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Any:
        resp = await self._get().post(f"{self._base}{path}", json=json, headers=headers)
        return {"status_code": resp.status_code, "body": _safe_json(resp)}

    async def patch_json(self, path: str, *, json: dict[str, Any]) -> Any:
        resp = await self._get().patch(f"{self._base}{path}", json=json)
        return {"status_code": resp.status_code, "body": _safe_json(resp)}

    async def delete(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        resp = await self._get().delete(f"{self._base}{path}", params=params)
        return {"status_code": resp.status_code, "body": _safe_json(resp)}


def _safe_json(resp: httpx.Response) -> Any:
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text[:300]}
