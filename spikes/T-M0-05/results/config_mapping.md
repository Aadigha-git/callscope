# Design §4.2 → livekit-agents 1.8.2 config mapping

Source of truth: installed `livekit/agents/voice/turn.py` (`TurnHandlingOptions`,
`EndpointingOptions`, `InterruptionOptions`) and `livekit/plugins/silero/vad.py`
(`VAD.load`). Deprecated flat `AgentSession(min_interruption_duration=…)` kwargs still
exist but emit deprecation warnings; prefer `turn_handling=`.

| CallScope design key (§4.2) | Default | LiveKit Agents 1.8.2 target | Notes |
|---|---|---|---|
| `endpoint.min_delay_s` | 0.4 | `turn_handling.endpointing.min_delay` (seconds) | Framework default 0.5 |
| `endpoint.max_delay_s` | 1.2 | `turn_handling.endpointing.max_delay` (seconds) | Framework default 3.0 |
| `vad.threshold` | 0.5 | `silero.VAD.load(activation_threshold=…)` | Same scale |
| `vad.min_speech_ms` | 200 | `silero.VAD.load(min_speech_duration=0.2)` | Silero uses **seconds** |
| `barge_in.min_duration_ms` | 250 | `turn_handling.interruption.min_duration` = 0.25 s | **Seconds**, not ms |
| `barge_in.grace_ms_after_playback_start` | 400 | `AgentSession(aec_warmup_duration=0.4)` | Seconds; blocks interruptions while AEC warms |
| `chunker.min_chars` | 24 | *(CallScope worker)* | No LiveKit equivalent — keep in our chunker |
| `filler.after_ms` | 1500 | *(CallScope worker)* | No LiveKit equivalent |
| `call.max_duration_s` | 240 | Room / session API / our worker | Not an Agents turn option |
| `call.silence_timeout_s` | 20 | `AgentSession(user_away_timeout=20.0)` | Closest built-in |

## Related interruption knobs (framework-only)

| Key | Default | Use |
|---|---|---|
| `interruption.enabled` | true | Master interrupt switch |
| `interruption.mode` | auto / `"vad"` / `"adaptive"` | Spike uses `"vad"` offline |
| `interruption.min_words` | 0 | STT-gated interruptions |
| `interruption.resume_false_interruption` | true | Resume after false barge-in |
| `interruption.false_interruption_timeout` | 2.0 s | Silence before classifying false |
| `turn_detection` | auto (may hit Cloud) | Spike pins `"vad"` to stay offline |

## Deprecated aliases (still accepted)

`min_endpointing_delay`, `max_endpointing_delay`, `min_interruption_duration`,
`min_interruption_words`, `allow_interruptions`, `false_interruption_timeout`,
`resume_false_interruption` on `AgentSession.__init__` map into `TurnHandlingOptions`
via `livekit.agents.voice.turn` helpers — prefer the nested dict form.
