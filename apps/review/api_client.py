"""HTTP client for the CallScope review API (Streamlit talks only via this)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import httpx


class ReviewApiClient:
    def __init__(
        self,
        base_url: str,
        service_token: str,
        *,
        timeout_s: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {service_token}"}
        self._client = client or httpx.Client(timeout=timeout_s)

    def close(self) -> None:
        self._client.close()

    def list_calls(self, **params: Any) -> dict[str, Any]:
        r = self._client.get(f"{self.base_url}/v1/calls", params=params, headers=self._headers)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def call_detail(self, call_id: str | UUID) -> dict[str, Any]:
        r = self._client.get(f"{self.base_url}/v1/calls/{call_id}", headers=self._headers)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def audio_url(self, call_id: str | UUID) -> dict[str, Any]:
        r = self._client.get(f"{self.base_url}/v1/calls/{call_id}/audio", headers=self._headers)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def add_label(self, call_id: str | UUID, body: dict[str, Any]) -> dict[str, Any]:
        r = self._client.post(
            f"{self.base_url}/v1/calls/{call_id}/labels",
            json=body,
            headers=self._headers,
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def export_labelled(
        self,
        name: str,
        version: str,
        root_causes: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "version": version}
        if root_causes:
            payload["root_causes"] = root_causes
        r = self._client.post(
            f"{self.base_url}/v1/datasets:export-labelled",
            json=payload,
            headers=self._headers,
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def list_eval_runs(self) -> list[dict[str, Any]]:
        r = self._client.get(f"{self.base_url}/v1/eval/runs", headers=self._headers)
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def compare_runs(self, a: str, b: str) -> list[dict[str, Any]]:
        r = self._client.get(
            f"{self.base_url}/v1/eval/compare",
            params={"a": a, "b": b},
            headers=self._headers,
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def seed_demo(self, n: int = 40) -> dict[str, Any]:
        r = self._client.post(
            f"{self.base_url}/v1/devtools/seed-review",
            json={"n": n},
            headers=self._headers,
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]
