"""Mint a short-lived LiveKit room token for the spike web client."""

from __future__ import annotations

import argparse
import datetime as dt
import os
import time

from livekit import api


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--room", default="callscope-spike")
    p.add_argument("--identity", default="browser-caller")
    p.add_argument("--ttl-s", type=int, default=600)
    p.add_argument(
        "--url",
        default=os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880"),
    )
    args = p.parse_args()

    key = os.environ.get("LIVEKIT_API_KEY", "devkey")
    secret = os.environ.get("LIVEKIT_API_SECRET", "secret")

    token = (
        api.AccessToken(key, secret)
        .with_identity(args.identity)
        .with_name(args.identity)
        .with_ttl(dt.timedelta(seconds=args.ttl_s))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=args.room,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .with_room_config(
            api.RoomConfiguration(
                agents=[api.RoomAgentDispatch(agent_name="")],
            )
        )
        .to_jwt()
    )
    print(f"LIVEKIT_URL={args.url}")
    print(f"ROOM={args.room}")
    print(f"IDENTITY={args.identity}")
    print(f"TOKEN={token}")
    print(f"# expires_approx_unix={int(time.time()) + args.ttl_s}")


if __name__ == "__main__":
    main()
