"""Minimal LiveKit Agents worker with stub STT/LLM/TTS (spike T-M0-05).

APIs verified against installed livekit-agents==1.8.2 source
(AgentServer.rtc_session, AgentSession(turn_handling=...), StreamAdapter,
silero.VAD.load parameters).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    TurnHandlingOptions,
    cli,
    metrics,
)
from livekit.agents.stt import StreamAdapter
from livekit.agents import MetricsCollectedEvent
from livekit.plugins import silero

from stubs import CannedLLM, EchoSTT, SineTTS

logger = logging.getLogger("callscope.spike.t_m0_05")

# Design §4.2 defaults → LiveKit Agents 1.8.2 TurnHandlingOptions / Silero VAD
# (see results/config_mapping.md).
DESIGN_TURN: TurnHandlingOptions = {
    "turn_detection": "vad",  # avoid LiveKit Cloud turn-detector (401 offline)
    "endpointing": {
        "mode": "fixed",
        "min_delay": 0.4,  # endpoint.min_delay_s
        "max_delay": 1.2,  # endpoint.max_delay_s
    },
    "interruption": {
        "enabled": True,
        "mode": "vad",
        "min_duration": 0.25,  # barge_in.min_duration_ms / 1000
        "min_words": 0,
        "resume_false_interruption": True,
        "false_interruption_timeout": 2.0,
    },
    "preemptive_generation": {"enabled": False},
}

# barge_in.grace_ms_after_playback_start → aec_warmup_duration (seconds)
AEC_WARMUP_S = 0.4

server = AgentServer()


def _build_session() -> AgentSession:
    vad = silero.VAD.load(
        activation_threshold=0.5,  # vad.threshold
        min_speech_duration=0.2,  # vad.min_speech_ms / 1000
        min_silence_duration=0.4,  # aligned with endpoint.min_delay_s for spike
        sample_rate=16000,
        force_cpu=True,
    )
    stt = StreamAdapter(stt=EchoSTT(transcript="hello from caller"), vad=vad)
    return AgentSession(
        vad=vad,
        stt=stt,
        llm=CannedLLM(),
        tts=SineTTS(),
        turn_handling=DESIGN_TURN,
        aec_warmup_duration=AEC_WARMUP_S,
        user_away_timeout=20.0,  # call.silence_timeout_s (design)
    )


class StubReceptionist(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are a stub CallScope receptionist used only for spike T-M0-05. "
                "Keep replies short. Do not use markdown."
            ),
        )

    async def on_enter(self) -> None:
        self.session.generate_reply(
            instructions="Greet the caller in one short sentence and wait."
        )


@server.rtc_session()
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name, "spike": "T-M0-05"}
    logger.info("job starting room=%s", ctx.room.name)

    session = _build_session()

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)

    await session.start(agent=StubReceptionist(), room=ctx.room)
    logger.info("session started room=%s", ctx.room.name)


if __name__ == "__main__":
    # Dev keys match docker-compose --dev defaults / .env.example placeholders.
    os.environ.setdefault("LIVEKIT_URL", "ws://127.0.0.1:7880")
    os.environ.setdefault("LIVEKIT_API_KEY", "devkey")
    os.environ.setdefault(
        "LIVEKIT_API_SECRET", "secret"
    )  # livekit-server --dev uses key=devkey secret=secret
    # Allow importing stubs from this directory when launched as a script.
    os.chdir(Path(__file__).resolve().parent)
    cli.run_app(server)
