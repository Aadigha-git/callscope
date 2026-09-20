> Local-Mac scope: native ASR/TTS; Token Factory LLM; cassettes in CI; budget guard before `--live`. Verify APIs against installed source.

# M1 - Walking skeleton (a 60-second live browser call, events in Postgres)
Exit criterion: a live call with greeting + two turns + clean end; events reconstruct the timeline.
Wrap every prompt with P01 workflow. Design refs: sections 4.2, 4.3, 6.x, 7.

## T-M1-01
```text
Implement T-M1-01: event envelope, async batching writer, provider-call instrumentation.
Files: callscope/events/{models.py,writer.py,clock.py,instrument.py}, tests/events/.
- models.py: Pydantic v2 Event (event_id uuid4, call_id, turn_id|None, t_ms int, ts UTC, source
  Literal[worker|plugin|client|sim], type str, payload dict) matching docs/api/openapi.yaml Event.
  Include an enum/const list of event types from design 6.6.
- clock.py: CallClock started at call start; `t_ms()` from time.monotonic(); testable with a fake.
- writer.py: EventWriter with `emit(event)` (non-blocking, never raises), a bounded asyncio queue,
  batch flusher (size 100 or 250 ms) posting to an injected async `sink(list[Event])`; on sink
  failure retry with backoff then spill to a JSONL file in a spill dir (bounded size) and replay
  on recovery; graceful `aclose()` flushes.
- instrument.py: decorator/async context manager `instrument(stage, emitter)` that emits
  `<stage>.request`, first-byte (`first_token`/`first_audio`) and completion events and records
  `observe_stage` metrics; must work for async generators.
Tests (unit): batching, ordering, dedupe by event_id, sink failure -> spill -> replay, queue full
policy (drop oldest + counter), event validates against the OpenAPI schema, instrument on a fake
streaming provider measures first-byte and total latency with a fake clock.
Do not: write to Postgres here; the sink is injected.
```

## T-M1-02
```text
Implement T-M1-02: Alembic migrations + repositories.
- Add alembic; migrations/ with 0001 baseline that executes db/schema.sql content (split into
  ordered statements or use op.execute with the file). Add `make db-upgrade` targets to the Makefile.
- callscope/db/{engine.py,models.py,repositories.py}: async SQLAlchemy 2 (asyncpg or psycopg3)
  models for cs.calls, turns, events, tool_calls, root_cause_codes, stack_versions, model_versions;
  repositories: create_call, add_turns, bulk_insert_events (ON CONFLICT DO NOTHING on event_id),
  get_call_detail, list_calls(filters, cursor).
- tests: unit tests for query builders; integration tests (marker integration) using the CI
  Postgres via CALLSCOPE_TEST_DATABASE_URL, plus a snapshot test that pg_dump --schema-only of the
  migrated DB is equivalent to db/schema.sql (normalise ordering/whitespace) so schema.sql cannot drift.
- Update docs/DECISIONS.md if you change the schema (then update db/schema.sql AND openapi if affected).
Do not: put business logic in repositories; do not use blocking DB calls in async code.
```

## T-M1-03
```text
Implement T-M1-03: provider interfaces and mocks.
Files: callscope/providers/{base.py,mock.py}, tests/providers/.
- base.py: Protocols STTProvider (stream/transcribe), TTSProvider (stream, sample_rate),
  BrainBackend (stream_reply, cancel) exactly as in design 4.2; dataclasses STTEvent (partial/final,
  text, words, avg_conf, t offsets), Transcript, BrainDelta (text | tool_event | done), Msg.
- mock.py: MockSTT (scripted transcripts, configurable latency, optional failure at N-th call),
  MockTTS (generates deterministic PCM16 tone chunks proportional to text length; cancellable),
  MockBrain (scripted replies streamed token by token; supports cancel; simulates first-token delay).
  All accept a clock/sleep abstraction so tests run instantly with fake time.
- Contract test suite `tests/providers/contract.py` with parametrised fixtures: streaming yields
  in order, cancellation stops generation within one chunk, errors surface as ProviderError
  subclasses (define ProviderError, ProviderTimeout, ProviderUnavailable), first-byte latency is
  measurable. Real providers in later tasks must plug into the same suite.
Do not: import any real model library here.
```

## T-M1-04
```text
Implement T-M1-04: sentence chunker and TTS text normaliser.
Files: callscope/norm/{chunker.py,tts_norm.py}, tests/norm/ with golden tests.
- SentenceChunker: incremental `push(delta) -> None`, `ready() -> list[str]`, `flush()`. Emit at
  sentence end (. ! ? followed by space/end) or clause boundary (, ; :) once min_chars (default 24)
  reached, or after max_wait ms (injectable clock). Never split inside numbers (3.5, 949-555-0123),
  abbreviations (Dr., St., a.m.), or codes. Strip nothing here.
- tts_norm(text): remove markdown emphasis/lists, <think>...</think> blocks and tool traces; read US
  phone numbers digit by digit with grouping pauses ("nine four nine, five five five, ..."),
  confirmation codes character by character, dates ("Tuesday, October 6th"), times ("two thirty
  p m"), ordinals, currency ranges ("between one fifty and two fifty dollars"), street numbers.
- Property/edge tests: streaming one character at a time gives the same sentences as one big push;
  empty and whitespace-only input; very long sentence forced flush; unicode quotes.
Keep both pure and fast (no I/O).
```

## T-M1-05
```text
Implement T-M1-05: ASR server for the model chosen in T-M0-06.
Files: servers/asr/{app.py,backends/,vad.py,models.py}, tests/servers/asr/.
- FastAPI app implementing design 4.3: WebSocket /v1/stream (JSON start {sample_rate, encoding,
  hotwords?}, binary PCM16 frames, JSON end; server emits partial/final with words[{w,start_ms,
  end_ms,conf}] and avg_conf) and POST /v1/transcribe (multipart -> same final object), /healthz,
  /metrics (request latency, real-time factor, queue depth, active streams).
- Backend interface `ASRBackend` (load, transcribe_chunk, finalize) with the chosen implementation.
  If the model is not natively streaming: Silero VAD segmentation + rolling-window decoding with a
  local-agreement policy for partials; final emitted when the segment ends or on `end`.
- Provide `callscope/providers/asr_client.py` implementing STTProvider over that WebSocket, and run
  the shared provider contract suite against it using a fake backend in CI (no GPU) and the real
  backend under marker `gpu`.
- Handle: client disconnects, frames out of size bounds, unsupported sample rates (reject clearly),
  concurrency limit with backpressure, hotwords passthrough (verify the model API supports them).
Do not: log audio or transcripts; do not load the model at import time.
```

## T-M1-06
```text
Implement T-M1-06: TTS server for the model chosen in T-M0-06.
Files: servers/tts/{app.py,backends/}, callscope/providers/tts_client.py, tests/servers/tts/.
- POST /v1/tts/stream {text, voice, speed, sample_rate} -> chunked raw PCM16 (Content-Type
  audio/L16; X-Sample-Rate header), GET /v1/voices, /healthz, /metrics (TTFB, RTF, chars/s).
- Backend interface with async generator producing chunks as they are synthesised (smallest
  practical chunk, e.g. 20-40 ms) so first audio arrives fast; resample to the requested rate.
- Cancellation: client disconnect must stop synthesis quickly (test with a slow fake backend).
- TTSClient implements TTSProvider (httpx streaming); run the provider contract suite (fake backend
  in CI, real backend under marker gpu).
- Add a warm-up call at startup so the first real request is not slow.
Do not: cache or persist synthesised text; never log the text.
```

## T-M1-07
```text
Implement T-M1-07: CallScope API (contract-first).
Files: apps/api/{main.py,routes/,deps.py,ratelimit.py,livekit_tokens.py}, tests/api/.
- Implement /v1/status, /v1/sessions (POST), /v1/sessions/{id}/end, /v1/events:batch exactly per
  docs/api/openapi.yaml. Add contract tests that validate every response against the spec.
- Sessions: require consent_recording=true and policy_version match; verify consent (skip only when
  CALLSCOPE_ENV=dev/test); enforce caps (2 concurrent public sessions, 240 s max duration, 3
  sessions/min/IP, 20/day/IP) using a small in-process limiter behind an interface (Redis later);
  create the calls row (consent flags + policy version) and mint a LiveKit token (5 min TTL,
  identity- and room-scoped, publish audio only) with livekit-api (verify the package API from
  source). Return 503 problem+json when the local Mac/worker is offline (status endpoint reflects it).
- Ingest: bulk insert with ON CONFLICT DO NOTHING; returns accepted/duplicates; service-token auth.
- RFC 7807 errors, request-id middleware binding call_id to logs, /metrics endpoint.
- Tests: consent missing -> 4xx; caps; token claims; idempotent ingest; auth required on internal routes.
If the API needs to differ from openapi.yaml, change the spec in the same PR and log a decision.
```

## T-M1-08
```text
Implement T-M1-08: web client (apps/web, Vite + vanilla TypeScript, no framework).
- Pages: landing/status (calls GET /v1/status; when offline show the offline message and a slot for
  recorded sample calls), call view. Consent modal with recording notice, fictional-data banner,
  optional "donate to eval set" checkbox default OFF; the mic is requested ONLY after consent.
- Start session via POST /v1/sessions, connect with livekit-client (verify API from installed
  package), publish mic with echoCancellation/noiseSuppression/autoGainControl on, play agent audio,
  handle the `callscope` data topic (agent.state, transcript.partial/final, agent.text, notice,
  error), End button sends control.end and POST /end.
- Security: strict CSP meta, render all transcript text with textContent (never innerHTML), no
  third-party scripts except the consent widget, no secrets in the bundle.
- Tests (vitest): consent gating, state machine of the UI, XSS test with a hostile transcript string.
- Add `make web-build` and CI job for lint/test/build if Node is available in the workflow.
```

## T-M1-09
```text
Implement T-M1-09: Hermes receptionist profile + HermesBackend.
Files: infra/hermes/{profile,README.md}, callscope/providers/hermes_backend.py, tests/providers/.
- infra/hermes: the receptionist profile config (memory off, API server on, provider = Token Factory
  OpenAI-compatible endpoint, toolset restricted to plugin tools; verify each setting name in
  Hermes docs/source) and a startup self-test script that lists the effective toolset and exits
  non-zero if it contains anything outside the allowlist.
- HermesBackend implements BrainBackend with httpx streaming to POST /v1/chat/completions
  (stream=true, bearer key, fixed model alias, `user`=call_id, optional X-Call-Id/X-Turn-Id per the
  S-1 finding): parse SSE deltas, yield BrainDelta, support cancel() by closing the stream, map
  HTTP/timeouts to ProviderError types, enforce a first-token timeout (default 8 s).
- Send full history each turn plus the CALL_CONTEXT message if S-1 requires it; support the
  interruption note.
- Tests: recorded SSE fixtures (normal, error mid-stream, slow first token, tool-call-heavy),
  cancel behaviour, contract suite; a `gpu`-marked live test against the local Hermes.
```

## T-M1-10
```text
Implement T-M1-10: voice worker.
Files: apps/worker/{main.py,session.py,state.py,config.py,livekit_glue.py}, tests/worker/.
- state.py: pure TurnStateMachine (IDLE, LISTENING, THINKING, SPEAKING) with explicit transitions
  and events, exactly as in design 4.2, no LiveKit imports; drive it with mock providers in tests.
- session.py: orchestrates one call: streams mic PCM to STTProvider, applies endpointing
  (config keys from design 4.2 mapped per S-4 findings), sends final transcripts to BrainBackend,
  feeds deltas to SentenceChunker -> tts_norm -> TTSProvider, publishes PCM to the LiveKit track,
  emits every event in design 6.6 via EventWriter with CallClock timestamps, sends data-channel
  messages, enforces call.max_duration and silence timeout, greets first, uploads events on end.
- livekit_glue.py: the thin adapter to LiveKit Agents (verify against the installed version).
- Metrics: RESPONSE_LATENCY (end of caller speech -> first agent audio), stage histograms,
  ACTIVE_CALLS, CALLS_TOTAL. Start the metrics server on CALLSCOPE_METRICS_PORT.
- Tests: every state transition, empty transcript, ASR error, brain timeout, TTS error, greeting,
  call end paths, deterministic latency with fake clock. Then a live manual test on the local
  node: 60 s call; show me the reconstructed timeline query.
Do not: implement barge-in/filler/degradation here beyond hooks; that is T-M2-05.
```

## T-M1-11
```text
Implement T-M1-11: local runner + Compose data plane + make demo.
- Keep docker-compose.local.yml for Postgres, Prometheus, Grafana (MinIO optional). Do NOT put
  ASR/TTS/Hermes/worker/livekit in Compose (no Metal passthrough on Docker Desktop Mac).
- Add a Procfile + honcho (or overmind) OR a make demo script that starts native processes:
  livekit-server --dev, API, biz, worker, ASR, TTS, Hermes. make demo-stop tears down.
- Grafana scrape via host.docker.internal; small Live-ops dashboard (active calls, latency p50/p95).
- Document ports and startup order in DEV_GUIDE. Target: fresh clone → working demo <20 min (NFR-07).
Verify compose config in CI. No deploy.sh, no Caddy, no GPU compose.
```


## T-M1-12
```text
Implement T-M1-12: LLM budget guard.
- callscope/providers/budget.py: estimate cost from Token Factory usage or token counts × $/1M;
  read CALLSCOPE_LLM_BUDGET_USD (default 15) and CALLSCOPE_LLM_SPEND_USD; refuse when projected
  spend would exceed remaining. Persist estimated_usd on eval_runs when that table exists.
- CLI / `make budget` prints spend vs cap. `--estimate` dry-run for eval entrypoints.
- Unit tests for pricing math and refusal. Never call the network in tests.
Verify pricing fields against Token Factory docs/response shapes; do not invent fields.
```

## T-M1-13
```text
Implement T-M1-13: LLM record/replay cassettes.
- Store request/response by content hash under eval/cassettes/ (or tests/cassettes/).
- BrainBackend looks up cassette first; CI must never hit the network (fail if missing).
- `--live` records new cassettes only when budget guard allows. Redact secrets in fixtures.
- Contract tests against cassettes for HermesBackend streaming + cancel.
```
