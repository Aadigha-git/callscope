/**
 * LiveKit room session — API verified against livekit-client (Room, createLocalAudioTrack).
 */

import {
  Room,
  RoomEvent,
  Track,
  createLocalAudioTrack,
  type RemoteTrack,
  type RemoteTrackPublication,
  type RemoteParticipant,
} from "livekit-client";

import type { CallscopeMessage } from "./types";
import { DATACHANNEL_TOPIC } from "./types";

export interface CallSessionHandlers {
  onAgentAudio: (stream: MediaStream) => void;
  onMessage: (msg: CallscopeMessage) => void;
  onDisconnected: () => void;
}

export class CallSession {
  private room: Room | null = null;

  async connect(
    url: string,
    token: string,
    handlers: CallSessionHandlers,
  ): Promise<void> {
    const room = new Room();
    this.room = room;

    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack, _pub: RemoteTrackPublication, _p: RemoteParticipant) => {
      if (track.kind === Track.Kind.Audio) {
        // Prefer LiveKit attach() — more reliable than manually wrapping MediaStreamTrack.
        const el = track.attach() as HTMLAudioElement;
        el.autoplay = true;
        el.setAttribute("playsinline", "true");
        el.muted = false;
        el.volume = 1;
        void el.play().catch(() => {
          /* gesture already happened on Start call; ignore autoplay races */
        });
        handlers.onAgentAudio(new MediaStream([track.mediaStreamTrack]));
      }
    });

    room.on(RoomEvent.DataReceived, (payload: Uint8Array, _p, _kind, topic) => {
      if (topic && topic !== DATACHANNEL_TOPIC) return;
      try {
        const text = new TextDecoder().decode(payload);
        const msg = JSON.parse(text) as CallscopeMessage;
        handlers.onMessage(msg);
      } catch {
        handlers.onMessage({ type: "error", message: "bad data-channel payload" });
      }
    });

    room.on(RoomEvent.Disconnected, () => {
      handlers.onDisconnected();
    });

    await room.connect(url, token);

    const mic = await createLocalAudioTrack({
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    });
    await room.localParticipant.publishTrack(mic);
  }

  async sendControlEnd(): Promise<void> {
    if (!this.room) return;
    const data = new TextEncoder().encode(JSON.stringify({ type: "control.end" }));
    await this.room.localParticipant.publishData(data, {
      reliable: true,
      topic: DATACHANNEL_TOPIC,
    });
  }

  async disconnect(): Promise<void> {
    if (this.room) {
      await this.room.disconnect();
      this.room = null;
    }
  }
}
