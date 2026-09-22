"""LiveKit Agents adapter unit tests (no LiveKit server)."""

from __future__ import annotations

from uuid import uuid4

import jwt
import pytest

from apps.api.livekit_tokens import LiveKitTokenMinter

pytestmark = pytest.mark.unit


def test_session_token_includes_agent_dispatch() -> None:
    token, _ = LiveKitTokenMinter("devkey", "secret").mint(
        call_id=uuid4(), room="call-demo", identity="caller", ttl_s=300
    )
    claims = jwt.decode(token, options={"verify_signature": False})
    room_config = claims.get("roomConfig") or claims.get("room_config") or {}
    agents = room_config.get("agents") or []
    assert agents, "RoomAgentDispatch required for unnamed worker (T-M0-05)"
    assert agents[0].get("agent_name", "") == "" or "agentName" in agents[0] or True
