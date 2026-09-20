# Barge-in / interruption notes (S-4)

## Setup

- `livekit-agents==1.8.2` with Silero VAD, stub STT/LLM/TTS
- `turn_handling.interruption.mode = "vad"`
- `interruption.min_duration = 0.25` (design `barge_in.min_duration_ms`)
- `aec_warmup_duration = 0.4` (design `barge_in.grace_ms_after_playback_start`)

## Observations

1. **Framework owns interruption.** On agent speech, sustained user speech ≥
   `min_duration` cancels the current TTS/LLM generation. Exact word-level prefix
   recovery is still CallScope’s responsibility (design §4.2 interruption fidelity).
2. **Echo / false triggers.** `aec_warmup_duration` ignores interruptions for a short
   window after playback starts — maps cleanly to the design grace period. Browser
   should keep AEC/NS/AGC on (`web/index.html` requests them). Residual false barge-ins
   from speaker→mic coupling remain a measured risk (design R-04); raise
   `min_duration` / `min_words` or enable `resume_false_interruption` if needed.
3. **STT interim path.** Upstream issue livekit/agents#3515 notes that historically
   `min_duration` was only enforced on the VAD path; STT interim/final could bypass it.
   1.8.2 still documents `min_duration` on interruption options; measure again when
   swapping EchoSTT for a streaming ASR (T-M1-05).
4. **Smoke evidence.** Headless smoke publishes 2 s of tone then silence; agent greets
   immediately (`generate_reply` on enter) and publishes TTS audio that the caller
   subscribed to (`SMOKE_OK`). Full barge-in timing characterisation belongs with
   T-M2-05, not this spike.

## Recommendation for CallScope worker

Keep LiveKit Agents as the realtime loop; expose design §4.2 keys via a thin mapper
onto `TurnHandlingOptions` + Silero `VAD.load` + `aec_warmup_duration`. Do not fork
interruption logic.
