"""HTTP sink posting event batches to CallScope API (service token)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from callscope.events.models import Event


def make_http_event_sink(
    *,
    api_base_url: str,
    service_token: str,
    timeout_s: float = 10.0,
) -> Any:
    """Return an async sink compatible with ``EventWriter``."""

    base = api_base_url.rstrip("/")

    async def sink(events: Sequence[Event]) -> None:
        if not events:
            return
        payload = {
            "events": [
                {
                    "event_id": str(e.event_id),
                    "call_id": str(e.call_id),
                    "turn_id": str(e.turn_id) if e.turn_id else None,
                    "t_ms": e.t_ms,
                    "ts": e.ts.isoformat(),
                    "source": e.source.value,
                    "type": e.type,
                    "payload": e.payload,
                }
                for e in events
            ]
        }
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{base}/v1/events:batch",
                json=payload,
                headers={"Authorization": f"Bearer {service_token}"},
            )
            resp.raise_for_status()

    return sink
