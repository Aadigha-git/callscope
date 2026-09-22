"""Worker turn configuration (design §4.2 + S-4 mapping)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class WorkerConfig(BaseModel):
    """Tunable turn-handling knobs stored with the stack version."""

    endpoint_min_delay_s: float = Field(default=0.4, ge=0.0)
    endpoint_max_delay_s: float = Field(default=1.2, ge=0.0)
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    vad_min_speech_ms: int = Field(default=200, ge=0)
    barge_in_min_duration_ms: int = Field(default=250, ge=0)
    barge_in_grace_ms_after_playback_start: int = Field(default=400, ge=0)
    chunker_min_chars: int = Field(default=24, ge=1)
    filler_after_ms: int = Field(default=1500, ge=0)
    turn_abort_ms: int = Field(default=8000, ge=1000)
    filler_text: str = "One moment."
    filler_clip_id: str = "filler_one_moment"
    apology_text: str = "Sorry, that took too long. How else can I help?"
    call_max_duration_s: float = Field(default=240.0, ge=1.0)
    call_silence_timeout_s: float = Field(default=20.0, ge=1.0)
    greeting_text: str = "Thanks for calling. How can I help you today?"
    tts_voice: str = "default"
    tts_speed: float = Field(default=1.0, gt=0.0)
    sample_rate: int = Field(default=16_000, ge=8_000)
    # Domain vocabulary for Whisper initial_prompt (E1 / T-M5-02).
    hotwords: list[str] = Field(default_factory=list)

    @classmethod
    def with_domain_hotwords(
        cls,
        *,
        hotwords_path: str | Path | None = "eval/hotwords.txt",
        **kwargs: Any,
    ) -> WorkerConfig:
        """Build config with E1 domain vocabulary when ``hotwords`` not supplied."""
        from callscope.experiments.hotwords import build_hotword_list, load_hotwords_file

        if "hotwords" not in kwargs:
            path = Path(hotwords_path) if hotwords_path else None
            if path is not None and path.is_file():
                kwargs["hotwords"] = load_hotwords_file(path)
            else:
                kwargs["hotwords"] = build_hotword_list(max_words=64)
        return cls(**kwargs)

    def turn_handling_options(self) -> dict[str, object]:
        """Map to livekit-agents 1.8.2 ``TurnHandlingOptions`` (D-20260920-05)."""
        return {
            "turn_detection": "vad",
            "endpointing": {
                "mode": "fixed",
                "min_delay": self.endpoint_min_delay_s,
                "max_delay": self.endpoint_max_delay_s,
            },
            "interruption": {
                "enabled": True,
                "mode": "vad",
                "min_duration": self.barge_in_min_duration_ms / 1000.0,
                "min_words": 0,
                "resume_false_interruption": True,
                "false_interruption_timeout": 2.0,
            },
            "preemptive_generation": {"enabled": False},
        }

    def vad_load_kwargs(self) -> dict[str, object]:
        """Kwargs for ``silero.VAD.load`` (seconds where the plugin expects them)."""
        return {
            "activation_threshold": self.vad_threshold,
            "min_speech_duration": self.vad_min_speech_ms / 1000.0,
            "min_silence_duration": self.endpoint_min_delay_s,
            "sample_rate": self.sample_rate,
            "force_cpu": True,
        }

    @property
    def aec_warmup_duration_s(self) -> float:
        return self.barge_in_grace_ms_after_playback_start / 1000.0
