"""Regression: LiveKit job entrypoint must be picklable for spawn workers."""

from __future__ import annotations

import pickle

from apps.worker.livekit_agent import rtc_entrypoint


def test_rtc_entrypoint_is_module_level_and_picklable() -> None:
    assert rtc_entrypoint.__module__ == "apps.worker.livekit_agent"
    assert rtc_entrypoint.__qualname__ == "rtc_entrypoint"
    # Nested locals fail here — that was why browser calls got no agent.
    blob = pickle.dumps(rtc_entrypoint)
    restored = pickle.loads(blob)  # noqa: S301 — round-trip our own entrypoint only
    assert restored.__name__ == "rtc_entrypoint"
