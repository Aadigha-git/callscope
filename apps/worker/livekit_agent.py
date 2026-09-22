"""LiveKit Agents entrypoint: real ASR/TTS servers + Token Factory LLM.

Entrypoint MUST be module-level so LiveKit's spawn-based job process pool can
pickle it (a nested ``def`` inside ``run_livekit_agent`` raises PicklingError).
"""

from __future__ import annotations

import logging
import os
import sys
from typing import TYPE_CHECKING

from apps.worker.config import WorkerConfig
from apps.worker.livekit_glue import agent_session_kwargs, require_livekit_agents

if TYPE_CHECKING:
    from livekit.agents import AgentSession, JobContext

logger = logging.getLogger("callscope.worker.livekit")


def _align_livekit_env() -> None:
    """Align env names with LiveKit Agents CLI expectations."""
    os.environ.setdefault(
        "LIVEKIT_URL",
        os.environ.get("CALLSCOPE_LIVEKIT_URL", "ws://127.0.0.1:7880"),
    )
    os.environ.setdefault(
        "LIVEKIT_API_KEY",
        os.environ.get("CALLSCOPE_LIVEKIT_API_KEY", "devkey"),
    )
    os.environ.setdefault(
        "LIVEKIT_API_SECRET",
        os.environ.get("CALLSCOPE_LIVEKIT_API_SECRET", "secret"),
    )


def build_agent_session() -> AgentSession:
    """Construct an ``AgentSession`` with CallScope STT/TTS/LLM + Silero VAD."""
    require_livekit_agents()
    from livekit.agents import AgentSession
    from livekit.agents.stt import StreamAdapter
    from livekit.plugins import silero

    from apps.worker.livekit_glue import build_vad_kwargs
    from apps.worker.lk_adapters import CallScopeSTT, CallScopeTTS, TokenFactoryLLM

    cfg = WorkerConfig.with_domain_hotwords()
    vad = silero.VAD.load(**build_vad_kwargs(cfg))
    stt = StreamAdapter(stt=CallScopeSTT(), vad=vad)
    return AgentSession(
        vad=vad,
        stt=stt,
        llm=TokenFactoryLLM(),
        tts=CallScopeTTS(),
        **agent_session_kwargs(cfg),
    )


async def rtc_entrypoint(ctx: JobContext) -> None:
    """Module-level job entrypoint (must be picklable for proc pool spawn)."""
    require_livekit_agents()
    from livekit.agents import Agent, MetricsCollectedEvent, metrics

    ctx.log_context_fields = {"room": ctx.room.name}
    logger.info("job starting room=%s", ctx.room.name)
    cfg = WorkerConfig.with_domain_hotwords()
    session = build_agent_session()
    greeting = cfg.greeting_text

    class Receptionist(Agent):
        def __init__(self) -> None:
            super().__init__(
                instructions=(
                    "You are the CallScope Lakeside fictional receptionist. "
                    "Keep replies short and conversational. Never claim real personal data. "
                    "Do not use markdown."
                ),
            )

        async def on_enter(self) -> None:
            # Canned greeting via TTS only — do not wait on Token Factory here.
            # generate_reply() is slow and mic noise can cancel it before any audio.
            logger.info("greeting via say() text=%r", greeting[:80])
            await self.session.say(greeting, allow_interruptions=False)

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)

    await session.start(agent=Receptionist(), room=ctx.room)
    logger.info("session started room=%s", ctx.room.name)


def run_livekit_agent() -> None:
    """Blocking: run LiveKit Agents CLI (``dev`` / ``start`` via argv)."""
    _align_livekit_env()
    require_livekit_agents()
    from livekit.agents import AgentServer, cli

    server = AgentServer()
    # Register the module-level function so spawn workers can re-import + pickle it.
    server.rtc_session()(rtc_entrypoint)

    # Default to `dev` when no subcommand (honcho / make demo).
    if len(sys.argv) == 1 or (len(sys.argv) == 2 and sys.argv[1] in {"--livekit"}):
        sys.argv = [sys.argv[0], "dev"]
    cli.run_app(server)
