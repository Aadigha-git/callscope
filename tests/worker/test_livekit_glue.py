"""WorkerConfig ↔ LiveKit Agents mapping (S-4 / D-20260920-05)."""

from __future__ import annotations

import pytest

from apps.worker.config import WorkerConfig
from apps.worker.livekit_glue import (
    agent_session_kwargs,
    build_turn_handling,
    build_vad_kwargs,
    require_livekit_agents,
)


def test_turn_handling_mapping() -> None:
    cfg = WorkerConfig(
        endpoint_min_delay_s=0.4,
        endpoint_max_delay_s=1.2,
        barge_in_min_duration_ms=250,
        barge_in_grace_ms_after_playback_start=400,
        call_silence_timeout_s=20.0,
    )
    th = build_turn_handling(cfg)
    assert th["endpointing"]["min_delay"] == 0.4
    assert th["endpointing"]["max_delay"] == 1.2
    assert th["interruption"]["min_duration"] == 0.25
    assert th["turn_detection"] == "vad"
    vad = build_vad_kwargs(cfg)
    assert vad["activation_threshold"] == 0.5
    assert vad["min_speech_duration"] == 0.2
    kw = agent_session_kwargs(cfg)
    assert kw["aec_warmup_duration"] == 0.4
    assert kw["user_away_timeout"] == 20.0


def test_require_livekit_agents_message() -> None:
    import importlib.util

    if importlib.util.find_spec("livekit.agents") is not None:
        pytest.skip("livekit-agents installed in this environment")
    with pytest.raises(ImportError, match="uv sync --extra worker"):
        require_livekit_agents()
