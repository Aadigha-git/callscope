"""Hermes Agent plugin: CallScope receptionist tools + policy (T-M2-02/03).

Registration API verified against hermes-agent 0.19.0 spike plugins
(``PluginContext.register_tool`` / ``register_hook``; handlers return JSON strings).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hermes_callscope.policy import Deny, PolicyState, evaluate, record_success
from hermes_callscope.schemas import tool_json_schema
from hermes_callscope.tools import DESCRIPTIONS, HANDLERS

logger = logging.getLogger("hermes_callscope")

TOOLSET = "callscope-receptionist"
POLICY_STATE = PolicyState()

try:
    from callscope.observability import metrics as _metrics
except Exception:
    _metrics = None


def register(ctx: Any) -> None:
    """Entry point ``hermes_agent.plugins`` → ``callscope``."""

    def pre_tool_call(**kwargs: Any) -> Any:
        tool_name = str(kwargs.get("tool_name") or kwargs.get("name") or "")
        args = kwargs.get("args") or kwargs.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        decision = evaluate(tool_name, args, POLICY_STATE)
        if isinstance(decision, Deny):
            logger.info("policy deny rule=%s tool=%s", decision.rule, tool_name)
            if _metrics is not None:
                try:
                    _metrics.POLICY_DENIED.labels(rule=decision.rule).inc()
                except Exception:
                    pass
            # Hermes 0.19: return a substitute tool result string to block execution.
            # Spike hooks were log-only; returning a string is the fail-closed fallback.
            return json.dumps(
                {
                    "ok": False,
                    "error": decision.rule,
                    "message": decision.message,
                    "policy_denied": True,
                }
            )
        return None

    def post_tool_call(**kwargs: Any) -> None:
        tool_name = str(kwargs.get("tool_name") or "")
        args = kwargs.get("args") or {}
        call_id = ""
        if isinstance(args, dict):
            call_id = str(args.get("call_id") or "")
        if call_id and tool_name:
            record_success(tool_name, call_id, POLICY_STATE)
        logger.debug("post_tool_call tool=%s", tool_name)

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


__all__ = ["POLICY_STATE", "TOOLSET", "register"]
