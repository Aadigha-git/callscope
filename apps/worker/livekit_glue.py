"""Thin LiveKit Agents adapter (D-20260920-05). Verified against spike T-M0-05 / agents 1.8.2."""

from __future__ import annotations

from typing import Any

from apps.worker.config import WorkerConfig


def build_turn_handling(config: WorkerConfig) -> dict[str, Any]:
    """Return a ``TurnHandlingOptions``-shaped dict for ``AgentSession``."""
    return config.turn_handling_options()


def build_vad_kwargs(config: WorkerConfig) -> dict[str, Any]:
    """Kwargs for ``silero.VAD.load`` (seconds where the plugin expects them)."""
    return config.vad_load_kwargs()


def agent_session_kwargs(config: WorkerConfig) -> dict[str, Any]:
    """Common ``AgentSession(...)`` kwargs from §4.2 (excluding stt/llm/tts/vad objects)."""
    return {
        "turn_handling": build_turn_handling(config),
        "aec_warmup_duration": config.aec_warmup_duration_s,
        "user_away_timeout": config.call_silence_timeout_s,
    }


def require_livekit_agents() -> Any:
    """Import livekit.agents or raise a clear error (optional extra ``worker``)."""
    try:
        import livekit.agents as agents
    except ImportError as exc:  # pragma: no cover - exercised when extra missing
        raise ImportError(
            "livekit-agents is required for the LiveKit worker entrypoint. "
            "Install with: uv sync --extra worker"
        ) from exc
    return agents
