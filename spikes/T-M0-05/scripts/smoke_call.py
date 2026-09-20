"""Headless smoke: join room, publish sine audio, wait for agent track.

Does not replace the browser check; proves worker + LiveKit wiring without a GUI.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import math
import os
import struct
import time

from livekit import api, rtc


ROOM = os.environ.get("SPIKE_ROOM", "callscope-spike")
URL = os.environ.get("LIVEKIT_URL", "ws://127.0.0.1:7880")
KEY = os.environ.get("LIVEKIT_API_KEY", "devkey")
SECRET = os.environ.get("LIVEKIT_API_SECRET", "secret")


def _token(identity: str, *, agent: bool = False) -> str:
    grants = api.VideoGrants(
        room_join=True,
        room=ROOM,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
        agent=agent or None,
    )
    # Empty agent_name dispatches to unnamed workers (AgentServer default).
    room_config = api.RoomConfiguration(
        agents=[api.RoomAgentDispatch(agent_name="")],
    )
    return (
        api.AccessToken(KEY, SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_ttl(dt.timedelta(seconds=600))
        .with_grants(grants)
        .with_room_config(room_config)
        .to_jwt()
    )


def _sine_frame(sample_rate: int = 48000, samples: int = 480, hz: float = 440.0) -> rtc.AudioFrame:
    buf = bytearray()
    for i in range(samples):
        t = i / sample_rate
        sample = int(0.2 * 32767 * math.sin(2 * math.pi * hz * t))
        buf.extend(struct.pack("<h", sample))
    return rtc.AudioFrame(
        data=bytes(buf),
        sample_rate=sample_rate,
        num_channels=1,
        samples_per_channel=samples,
    )


async def main() -> int:
    room = rtc.Room()
    agent_audio = asyncio.Event()
    got_participant = asyncio.Event()

    @room.on("track_subscribed")
    def _on_track(track: rtc.Track, *_args) -> None:  # type: ignore[no-untyped-def]
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            agent_audio.set()

    @room.on("participant_connected")
    def _on_part(p: rtc.RemoteParticipant) -> None:
        print(f"participant_connected identity={p.identity}")
        got_participant.set()

    await room.connect(URL, _token("smoke-caller"))
    print(f"connected room={room.name} as smoke-caller")

    source = rtc.AudioSource(48000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("mic", source)
    await room.local_participant.publish_track(track)

    # Publish ~2s of tone so Silero VAD sees speech, then silence for endpointing.
    deadline = time.monotonic() + 45.0
    speech_until = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        if time.monotonic() < speech_until:
            await source.capture_frame(_sine_frame())
        else:
            silence = rtc.AudioFrame(
                data=b"\x00\x00" * 480,
                sample_rate=48000,
                num_channels=1,
                samples_per_channel=480,
            )
            await source.capture_frame(silence)
        await asyncio.sleep(0.01)
        if agent_audio.is_set():
            print("SMOKE_OK agent_audio_subscribed")
            await room.disconnect()
            return 0

    print("SMOKE_FAIL timeout waiting for agent audio")
    await room.disconnect()
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
