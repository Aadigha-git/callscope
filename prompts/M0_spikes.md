# M0 - Setup and spikes (spikes produce decisions, not product code)
Spike rules: time-boxed; throwaway code in `spikes/<TASK-ID>/`; results go into `docs/DECISIONS.md`
using the spike write-up prompt in ceremonies.md. Wrap every prompt with the workflow in
P01_task_wrapper.md (branch, status, CI, artifacts).

**Scope reminder:** everything runs on the Apple Silicon Mac except Token Factory LLM calls.
Do not provision VMs. Do not spend Token Factory credit without an estimate and a hard cap.
Verify third-party APIs against installed source/docs.

## T-M0-02
```text
Spike S-1 (task T-M0-02): can a per-call/turn ID reach Hermes plugin hook kwargs when Hermes is
called through its OpenAI-compatible API server?
- In a scratch venv under spikes/T-M0-02/, install Hermes Agent (record exact version), enable the
  API server (API_SERVER_ENABLED, API_SERVER_KEY, port 8642) with a dedicated profile.
- Write a ~30-line plugin (pip entry point group `hermes_agent.plugins`, `register(ctx)`) whose
  hooks log all kwargs they receive. Verify hook names/signatures from the installed Hermes source.
- Call /v1/chat/completions with the `user` field, headers X-Call-Id/X-Turn-Id, and CALL_CONTEXT.
- Also test: does closing the SSE connection cancel generation and tool execution?
Deliver: DECISIONS.md entry with the verdict (already landed as D-20260920-04 — re-open only if
re-verifying a newer Hermes).
```

## T-M0-07
```text
Spike S-6 (task T-M0-07): Mac sizing + Token Factory latency.
- Record chip/RAM (sysctl/sw_vers/uname) and usable budget (≥4 GB reserved for OS/browser).
- brew install livekit; run `livekit-server --dev`; confirm arm64 binary; note ports. If it fails,
  draft a FastAPI WebSocket audio-transport fallback ADR + tasks (do not implement yet).
- Note: Docker Desktop cannot use Mac Metal — ASR/TTS stay native.
- With TOKEN_FACTORY_API_KEY set, run 100 tiny chat.completions probes; record RTT/TTFT p50/p95.
  Cap spend (cents). Do not download models >2 GB without stating sizes first.
- Sketch memory budget table for design §9.5 (placeholders OK if ASR/TTS not loaded yet).
Deliver: DECISIONS.md entry; fill design §9.5; livekit-server verdict; TF latency table.
```

## T-M0-04
```text
Spike S-3 (task T-M0-04): LLM shortlist via Token Factory + Hermes tool-call reliability.
- Candidates: 2–3 catalog models with function_calling (see D-20260920-12). Confirm licences/prices.
- Configure Hermes custom provider → Token Factory (verify config keys in Hermes docs/source).
  Optional: sketch mlx-lm/llama.cpp local fallback config (best-effort, not a gate). Prefer not Ollama.
- Harness ~60 scripted receptionist turns through Hermes with stub tools. Score valid tool calls,
  schema-correct args, recovery, injection refusal. Keep spend under budget; log USD.
Deliver: results table + chosen model in DECISIONS.md. Exit: ≥95% valid tool calls for the winner.
```

## T-M0-03
```text
Spike S-2 (task T-M0-03): Hermes per-turn overhead vs Token Factory direct.
- Using the chosen TF model, script 50 turns against (a) OpenAI client → Token Factory direct and
  (b) Hermes API server with slim receptionist profile pointing at Token Factory.
- Measure TTFT p50/p95 and prompt tokens. Keep spend under $1. Prefer cassettes after T-M1-13.
Deliver: table + verdict vs brain stage budget (incl. network/TTFT row in design 3.6).
```

## T-M0-05
```text
Spike S-4 (task T-M0-05): LiveKit Agents wiring and hermes-livekit comparison.
(Already done as D-20260920-05 with docker livekit-server.) Follow-up native brew verification is
part of T-M0-07. Re-open only if re-verifying newer livekit-agents.
```

## T-M0-06
```text
Spike S-5 (task T-M0-06): Apple Silicon ASR/TTS/VAD shortlist probe.
- Candidates (verify versions/licences before download): mlx-whisper / mlx-audio Whisper,
  whisper.cpp, parakeet-mlx, faster-whisper CPU; Silero VAD; Kokoro (mlx-audio/kokoro-onnx), Piper.
  State sizes before any download >2 GB. Run natively (not in Docker).
- Probe 30 utterances; C1 telephony chain; measure RTF, unified-memory, first-audio, WER clean vs C1.
  Prefer streaming ASR; else VAD-segmented chunking.
- Feasibility note for optional E2 LoRA on whisper-small/base via MPS/MLX (or defer).
Deliver: shortlist table in DECISIONS.md; probe assets under eval/probe/ (no personal voices).
```
