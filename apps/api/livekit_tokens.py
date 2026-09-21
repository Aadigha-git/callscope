"""LiveKit JWT minting (verified against livekit-api 1.2.1 AccessToken API)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from livekit import api


class TokenMinter(Protocol):
    def mint(
        self,
        *,
        call_id: UUID,
        room: str,
        identity: str,
        ttl_s: int,
    ) -> tuple[str, datetime]:
        """Return (jwt, expires_at UTC)."""


class LiveKitTokenMinter:
    """Mints room-scoped tokens: publish + subscribe + data (transcript channel)."""

    def __init__(self, api_key: str, api_secret: str) -> None:
        self._key = api_key
        self._secret = api_secret

    def mint(
        self,
        *,
        call_id: UUID,
        room: str,
        identity: str,
        ttl_s: int = 300,
    ) -> tuple[str, datetime]:
        _ = call_id
        expires = datetime.now(UTC) + timedelta(seconds=ttl_s)
        token = (
            api.AccessToken(self._key, self._secret)
            .with_identity(identity)
            .with_name(identity)
            .with_ttl(timedelta(seconds=ttl_s))
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                    # Audio-only publish intent: video publish not required for grants API.
                )
            )
            .to_jwt()
        )
        return token, expires
