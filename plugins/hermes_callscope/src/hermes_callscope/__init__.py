"""Hermes Agent plugin: CallScope receptionist tools (T-M2-02).

Registration API verified against hermes-agent 0.19.0 spike plugins
(``PluginContext.register_tool`` / ``register_hook``; handlers return JSON strings).
"""

from __future__ import annotations

import logging
from typing import Any

from hermes_callscope.schemas import tool_json_schema
from hermes_callscope.tools import DESCRIPTIONS, HANDLERS

logger = logging.getLogger("hermes_callscope")

TOOLSET = "callscope-receptionist"


def register(ctx: Any) -> None:
    """Entry point ``hermes_agent.plugins`` → ``callscope``."""

    def pre_tool_call(**kwargs: Any) -> None:
        # Policy enforcement lands in T-M2-03; hook is registered for discovery.
        logger.debug("pre_tool_call keys=%s", sorted(kwargs.keys()))

    def post_tool_call(**kwargs: Any) -> None:
        logger.debug("post_tool_call tool=%s", kwargs.get("tool_name"))

    if hasattr(ctx, "register_hook"):
        ctx.register_hook("pre_tool_call", pre_tool_call)
        ctx.register_hook("post_tool_call", post_tool_call)

    for name, handler in HANDLERS.items():
        desc = DESCRIPTIONS[name]
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=tool_json_schema(name, desc),
            handler=handler,
            description=desc,
        )
    logger.info("registered %d tools on toolset=%s", len(HANDLERS), TOOLSET)


__all__ = ["TOOLSET", "register"]
