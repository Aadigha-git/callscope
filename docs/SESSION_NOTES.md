# Session notes (newest first)
Short handoff log so a fresh Cursor chat can resume. Add an entry at the end of every session.

Template:
- Date / task:
- Done:
- Next:
- Open questions / blockers:
- Commands to resume:

## 2026-09-20 / T-M2-01
- Done: Lakeside Business API (`apps/biz`) — seed, availability, idempotent book, auth by
  code+last4, KB search, callbacks, admin reset; `docs/kb_gaps.md`; `docs/api/biz.openapi.yaml`.
- Next: PR merge → **T-M2-02** hermes-callscope plugin.
- Open questions: Postgres-backed biz store deferred (D-20260920-31).
- Commands to resume: `git switch feat/T-M2-01-biz-api && make biz && make ci`

## 2026-09-20 / T-M1-11
- Done: Procfile + honcho, `scripts/demo_{start,stop}.sh`, Grafana Live-ops + Prometheus scrapes,
  compose image pins, `tests/infra/test_compose_config.py`, DEV_GUIDE ports table (D-20260920-30).
- Next: Finish PR; M1 walking skeleton nearly complete — next backlog is M2 (or polish Agents wiring).
- Open questions: Hermes/biz not in Procfile; LiveKit Agents STT/TTS adapters still spike-only.
- Commands to resume: `git switch feat/T-M1-11-make-demo && make compose-validate && make ci`

## 2026-09-20 / T-M1-10
- Done: `apps/worker` — TurnStateMachine, CallSession (greeting/turns/errors/interrupt hook),
  WorkerConfig↔Agents mapping, EventWriter sink helper, `make worker --mock-call`, unit tests.
- Next: Finish PR; after merge → **T-M1-11** make demo (wire LiveKit Agents + native procs).
- Open questions: 60 s live timeline AC needs local livekit-server + Agents adapters (T-M1-11).
- Commands to resume: `git switch feat/T-M1-10-voice-worker && make worker && make ci`

## 2026-09-20 / T-M1-09
- Done: `infra/hermes` receptionist profile (TF custom provider, memory off, toolset lockdown +
  `make hermes-selftest`); `HermesBackend` SSE stream/cancel/first-token timeout/CALL_CONTEXT;
  cassette wrap contract tests (ASGI fixtures, no network).
- Next: Finish PR; after merge → **T-M1-10** voice worker.
- Open questions: `hermes-callscope` plugin (T-M2) must register toolset `callscope-receptionist`.
- Commands to resume: `git switch feat/T-M1-09-hermes-backend && make hermes-selftest && make ci`

## 2026-09-20 / T-M1-08
- Done: `apps/web` Vite/TS client — consent modal, fictional banner, status, LiveKit connect,
  data-channel transcript (textContent), vitest XSS/state, `make web-*`, CI web job.
- Next: Finish PR; after merge → **T-M1-09** Hermes profile/backend (or T-M1-10 worker).
- Open questions: full E2E needs worker (T-M1-10) publishing agent audio + callscope events.
- Commands to resume: `git switch feat/T-M1-08-web-client && make web-test && make ci`

## 2026-09-20 / T-M1-07
- Done: CallScope API — status/sessions/end/events:batch, LiveKit tokens, session cap,
  service-token ingest, RFC 7807, metrics; MemoryCallStore for CI.
- Next: Open PR; after merge → **T-M1-08** web client.
- Open questions: SQL-backed CallStore when demo needs Postgres persistence.
- Commands to resume: `git switch feat/T-M1-07-callscope-api && make ci`

## 2026-09-20 / T-M1-06
- Done: TTS FastAPI server (chunked PCM `/v1/tts/stream`, voices, health/metrics TTFB),
  FakeTTS + optional Piper/kokoro-onnx, `TTSClient`, `make tts`.
- Next: Open PR; after merge → **T-M1-07** CallScope API.
- Open questions: none; real TTFB/RTF remain S-5 / D-20260920-19.
- Commands to resume: `git switch feat/T-M1-06-tts-server && make ci`

## 2026-09-20 / T-M1-13
- Done: CassetteStore + CassetteBrain (replay/record/live + budget gate); tests; eval/cassettes/.
- Next: Finish PR; after merge → **T-M1-06** TTS (S4) or wire Hermes in T-M1-09.
- Open questions: none; HermesBackend uses this wrapper when T-M1-09 lands.
- Commands to resume: `git switch feat/T-M1-13-llm-cassettes && make ci`

## 2026-09-20 / T-M1-05
- Done: ASR FastAPI server (WS `/v1/stream`, POST `/v1/transcribe`, `/healthz`, `/metrics`),
  FakeASR + EnergyVAD + lazy mlx-whisper backend, `ASRClient` STTProvider, `make asr`.
- Next: Open PR; after merge mark done → **T-M1-06** TTS server (or T-M1-13 per sprint).
- Open questions: none; real mlx RTF/memory remain those in D-20260920-19 / S-5.
- Commands to resume: `git switch feat/T-M1-05-asr-server && make ci`

## 2026-09-20 / T-M1-04
- Done: `SentenceChunker` + `tts_norm` with golden/property tests under `tests/norm/`.
- Next: After merge mark done; **T-M1-05** ASR server (or T-M1-13 per sprint order).
- Open questions: none.
- Commands to resume: `git switch feat/T-M1-04-chunker-tts-norm && make ci`

## 2026-09-20 / T-M1-03
- Done: provider protocols + mocks; merged #62; status done.
- Next: **T-M1-04** (started).
- Open questions: none.
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M1-02
- Done: Alembic baseline + repos; merged #61; status done.
- Next: **T-M1-03** (started).
- Open questions: none.
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M1-12
- Done: Budget guard + CLI; merged #60; status done.
- Next: **T-M1-02** (started).
- Open questions: none; wiring into eval/Hermes backends lands with those tasks + T-M1-13.
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M1-01
- Done: Event envelope + CallClock + EventWriter + `instrument()`; merged #59; status done.
- Next: **T-M1-12** (started).
- Open questions: none for the envelope; sink stays injected until T-M1-02 ingest/repos.
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M0-03
- Done: S-2 Hermes vs TF TTFT — direct p50 884 ms, Hermes p50 2287 ms, overhead p50 **1385 ms** (FAIL ≤450); ~$0.006; D-20260920-20 adopts R-02 thin FAQ fast-path. Merged #58; status done.
- Next: **T-M1-01** (started).
- Open questions: exact worker router heuristics for FAQ vs Hermes; whether T-M1-09 can shrink Hermes prompt enough to revisit.
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M0-06
- Done: S-5 native ASR/TTS/VAD shortlist; merged #57; status done.
- Next: T-M0-03 (started).

## 2026-09-20 / T-M0-04
- Done: Spike S-3 — Hermes 0.19.0 → Token Factory; winner **Nemotron-3_5-Lightning** 100%; merged #56; status done.
- Next: T-M0-06 (started).
- Open questions: Lightning region vs us-central1 preference; OpenMDW licence wording for showcase.
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M0-07
- Done: Mac baseline; native livekit 1.13.7; TF regional RTT (us-central1); chat probe 100× Nemotron-3-Nano p50 **699 ms** / p95 **824 ms**, spend ~$0.00022; D-20260920-17; merged #55; status done.
- Next: T-M0-04 (started / in progress on this session).
- Open questions / blockers: Docker still holds :7880.
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / chore/rescope-local-mac
- Done: Documentation/backlog rescope from public Nebius GPU VM demo → local Apple Silicon Mac +
  Token Factory LLM. Facts in DECISIONS D-20260920-10..16; design v1.1; backlog rewrite (+dropped);
  removed deploy.yml/deploy.sh; DEV_GUIDE/README/prompts/rules/.env.example updated; scrubber +
  gitleaks extended. T-M0-01 left as done (not re-marked). No API credit spent.
- Next: Open PR for this branch. Then start **T-M0-07** (Mac sizing + TF latency / native livekit).
- Open questions: native `livekit-server --dev` not yet executed on this Mac; TF verbose rate limits
  not queried without a key; ASR/TTS not yet benchmarked (T-M0-06).
- Commands to resume: `git switch chore/rescope-local-mac && make ci`

## 2026-09-20 / T-M0-05
- Done: Spike S-4 — LiveKit Agents 1.8.2 stub worker (EchoSTT/CannedLLM/SineTTS), docker livekit-server v1.9.1, headless `SMOKE_OK`, §4.2 mapping, hermes-livekit 0.4.0 review; D-20260920-05; ADR-002 confirmed (own worker). Also marked T-M0-01/T-M0-02 done after #52 merge.
- Next: After rescope merge: T-M0-07.
- Open questions / blockers: none for S-4. Tokens need `RoomAgentDispatch` or workers are not dispatched.
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M0-02
- Done: Spike S-1 against hermes-agent 0.19.0; correlation matrix + SSE source analysis; D-20260920-04; design §4.4/ADR-006/U1 notes; scrubbed evidence under `spikes/T-M0-02/results/`. Merged #52.
- Next: T-M0-05 (started).
- Open questions / blockers: PyPI latest Hermes is 0.19.0 (design mentioned 0.20.0).
- Commands to resume: `git switch main && git pull`

## 2026-09-20 / T-M0-01
- Done: Bootstrap CI fixes merged (PR #51); status to be marked done with T-M0-02/05 housekeeping.
- Next: T-M0-02 / T-M0-05.
- Open questions / blockers: Secret scanning may need Settings enable on free private.
- Commands to resume: `git switch main && git pull`
