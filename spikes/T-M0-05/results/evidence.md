# Evidence — T-M0-05 / S-4

## Headless smoke (primary automated proof)

```
command: LIVEKIT_URL=ws://127.0.0.1:7880 LIVEKIT_API_KEY=devkey LIVEKIT_API_SECRET=secret \
         SPIKE_ROOM=callscope-spike-2 python scripts/smoke_call.py
result: SMOKE_OK agent_audio_subscribed
agent: participant_connected identity=agent-AJ_yb45jdfTfRC5
worker: received job request room=callscope-spike-2; session started; TTS metrics audio_duration≈4.01s
server: livekit/livekit-server:v1.9.1 --dev (API Key=devkey, API Secret=secret)
packages: livekit-agents==1.8.2, livekit==1.1.18, livekit-api==1.2.1
```

Failure mode without `RoomAgentDispatch`: room stayed at `num_participants=1`;
worker never received a job. Fix: mint tokens with
`AccessToken.with_room_config(RoomConfiguration(agents=[RoomAgentDispatch(agent_name="")]))`.

## Browser page

`web/index.html` uses `livekit-client@2.15.6` (CDN ESM), requests mic with
AEC/NS/AGC, publishes audio, attaches remote agent audio. Manual join uses the same
token shape as `mint_token.py`.

## Artifacts produced

- `config_mapping.md` — §4.2 ↔ Agents 1.8.2
- `barge_in_notes.md` — interruption behaviour
- `hermes_livekit_review.md` — adopt/reject evidence
- `ENVIRONMENT.md` — versions

Worker runtime logs (`results/worker.log`) are gitignored (noisy / may contain room IDs).
