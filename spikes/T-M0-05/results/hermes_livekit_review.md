# hermes-livekit review (kortexa-ai/hermes-livekit)

Reviewed source checkout at commit `640812f` (2026-09-13), package version **0.4.0**.
Not installed into CallScope product code. Not adopted.

## What it is

Realtime voice gateway **plugin for hermes-agent**:

- OpenAI-compatible **direct WebRTC** endpoint (`aiortc`)
- Optional **LiveKit room** “conference” agent
- Shared conversation event contract; ASR → Hermes agent loop → TTS

Entry point: `hermes_agent.plugins` → `livekit = hermes_livekit`.

## Licence / maintenance signals

| Signal | Finding |
|---|---|
| Licence | MIT (Copyright 2026 kortexa.ai) |
| PyPI | **No** `hermes-livekit` distribution (install via git URL) |
| Stars (at review) | ~14 |
| Hermes requirement | `hermes-agent>=0.20.0` — **not published on PyPI** as of T-M0-02 (0.19.0 latest) |
| LiveKit pins | `livekit==1.1.14`, `livekit-api==1.2.0` (older than this spike’s 1.1.18 / 1.2.1) |
| Size | ~7k LOC under `hermes_livekit/` |

## Reusable ideas (reference only)

- Silero VAD packaging / adaptive thresholds (`vad.py`, `speech_detector.py`)
- Streaming TTS publish path + audio onset helpers
- Voice metrics helpers (`voice_metrics.py`)
- Tool-safety / confirmation patterns (orthogonal to LiveKit Agents)

## Gaps vs CallScope needs

| Need | Gap |
|---|---|
| FR-06 per-stage events / worker as latency SoT (ADR-006) | Plugin owns the loop inside Hermes; hard to emit CallScope stage events uniformly |
| Self-hosted ASR/TTS behind `callscope.providers` | Gateway assumes Hermes-side ASR/TTS plumbing |
| Cascaded STT→LLM→TTS eval (ADR-004) | Coupled to Hermes realtime path |
| Pin/control LiveKit Agents turn options (§4.2 mapping) | Does not use LiveKit Agents `AgentSession` turn_handling model |
| Supply-chain / public path (T4) | Third-party plugin; design already says spike-only until reviewed |

## Decision

**Do not adopt** as the CallScope voice worker. Keep **own LiveKit Agents worker** +
Hermes via API server (ADR-001/002). Revisit only if Hermes 0.20+ + hermes-livekit
expose the same stage events we need — still would need a conscious ADR change.
