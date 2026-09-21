"""Hermes Agent plugin: CallScope receptionist tools, policy, and skill.

Registration API verified against hermes-agent 0.19.0 spike plugins
(``PluginContext.register_tool`` / ``register_hook``; handlers return JSON strings).
``register_skill`` is used when present (design V1); otherwise the skill text is
logged and available via ``hermes_callscope.skill`` for the worker system prompt.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from hermes_callscope.policy import Deny, PolicyState, evaluate, record_success
from hermes_callscope.schemas import tool_json_schema
from hermes_callscope.skill import SKILL_NAME, prompt_hash, skill_text
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

    text = skill_text()
    ph = prompt_hash()
    registered_skill = False
    if hasattr(ctx, "register_skill"):
        try:
            ctx.register_skill(name=SKILL_NAME, content=text)
            registered_skill = True
        except TypeError:
            try:
                ctx.register_skill(SKILL_NAME, text)
                registered_skill = True
            except Exception:
                logger.warning("register_skill failed; skill available via skill_text()")
        except Exception:
            logger.warning("register_skill failed; skill available via skill_text()")
    logger.info(
        "registered %d tools toolset=%s skill=%s registered_skill=%s prompt_hash=%s",
        len(HANDLERS),
        TOOLSET,
        SKILL_NAME,
        registered_skill,
        ph,
    )


__all__ = ["POLICY_STATE", "TOOLSET", "prompt_hash", "register", "skill_text"]
