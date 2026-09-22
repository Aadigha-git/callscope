# Technical decision log

Append-only. Newest first. One entry per decision, spike result, or deviation from the design doc
(`docs/design/CallScope_Phase3_Design.md`). ADR-001..013 from the design doc are the baseline;
ADR-014..017 added in the local-Mac rescope.

## Template
```
### D-YYYYMMDD-NN - <short title>
- Date / Task: <date> / <T-Mx-yy>
- Context: <what forced a decision; evidence with run IDs or links>
- Decision: <what we do>
- Alternatives considered: <and why not>
- Consequences: <good/bad/follow-ups; tasks created>
- Design doc impact: <ADR-xxx updated? section changes? none>
- Status: proposed | accepted | superseded by D-...
```

## Baseline ADRs (from the design doc)
ADR-001 Hermes via API server | ADR-002 LiveKit Agents, no rebuild of streaming TTS/barge-in |
ADR-003 Self-hosted models (superseded by ADR-014) | ADR-004 Cascaded STT-LLM-TTS |
ADR-005 Postgres + event log + object store | ADR-006 Worker is latency source of truth |
ADR-007 Two eval modes | ADR-008 Synthetic-first data + recorded set |
ADR-009 Two-node GPU (superseded by ADR-015) | ADR-010 Security posture | ADR-011 Governance as code |
ADR-012 SIP stretch (dropped) | ADR-013 Streamlit review console |
ADR-014 Hybrid models + Token Factory | ADR-015 Local-only Mac deployment |
ADR-016 Budget guard + cassettes | ADR-017 Showcase deliverable

## Entries

### D-20260922-40 - Skip LangSmith datasets/experiments for judge eval
- Date / Task: 2026-09-22 / T-M4-06
- Context: T-M4-06 must decide whether LangSmith datasets/experiments earn a place for
  judge eval. Local SoT is already `eval/judge_calibration.jsonl` + FileEvalStore +
  Postgres (ADR-006). LangSmith datasets retain indefinitely and would duplicate
  scrubbed fictional text off-box.
- Decision: **Do not** use LangSmith datasets/experiments for judge eval. Keep optional
  tracing only (brain turns + eval item text spans) behind `CALLSCOPE_LANGSMITH_ENABLED`
  (default off). Judge calibration and gates stay local.
- Alternatives considered: mirror golden labels into LangSmith datasets (rejected —
  retention + dual SoT); always-on OTEL export (rejected — privacy/cost).
- Consequences: Documented; TracingBrain + NullTracer ship; enabling requires API key.
- Design doc impact: closes open item from D-20260920-15
- Status: accepted

### D-20260922-39 - Caller-sim uses livekit.rtc with MockTransport in CI
- Date / Task: 2026-09-22 / T-M4-04
- Context: Verified installed `livekit` (worker extra): `Room.connect`, `AudioSource`,
  `LocalAudioTrack.create_audio_track`, `LocalParticipant.publish_track`,
  `AudioSource.capture_frame`. Full unattended LiveKit room runs need a live
  livekit-server + worker (gpu marker).
- Decision: Ship `LiveKitCallerTransport` against those APIs; CI/default
  `run_caller_sim` uses `MockCallerTransport` + synthetic agent events + oracle
  metrics into `FileEvalStore` so all 16 scenarios run offline. Real rtc path
  remains available for local demo.
- Alternatives considered: skip LiveKit wrappers until gpu CI (rejected — need
  oracle + CLI mode now); require livekit in default deps (rejected — heavy).
- Consequences: `make eval ARGS='run --mode caller_sim --stack mock'` works offline.
- Design doc impact: none (ADR-007 extended with caller_sim mode in practice)
- Status: accepted

### D-20260921-38 - Recorded baseline deferred to volunteer sessions
- Date / Task: 2026-09-21 / T-M3-07
- Context: Acceptance needs 15/15 (or 20/20) consented human recordings with verified
  transcripts. Protocol and ingest tooling can ship without audio; inventing transcripts or
  claiming a recorded run_id would violate eval integrity (T11).
- Decision: Ship `docs/recording_protocol.md`, `callscope.datasets.recorded` + CLI, and
  `docs/reports/baseline.md` with a **real** synthetic/golden run_id for the mock path.
  Recorded half remains TBD until volunteers complete the protocol; update the baseline in a
  follow-up commit with recorded `run_id` + gap table (do not mark recorded acceptance done
  until then).
- Alternatives considered: synthetic tones labelled as "recorded" (rejected — misleading).
- Consequences: T-M3-07 PR documents partial acceptance; operator action required.
- Design doc impact: none.
- Status: accepted

### D-20260921-37 - Pre-declared thresholds + lockfile; WER margin units
- Date / Task: 2026-09-21 / T-M3-06
- Context: Design §10.2 gates and NI margins (WER +1.0 abs, task −2.0 abs, latency p95 +10%).
  Scorers store WER on [0,1]; changing thresholds needs governance discipline (ADR-011).
- Decision: Commit `eval/thresholds.yaml` (fraction units) and `docs/thresholds.lock` (sha256).
  Design "+1.0 abs" WER = +1.0 percentage points = **0.01** on [0,1]. Bootstrap CIs over
  *calls* (1,000 resamples, seed 42); `ci_width_note()` documents that n≈30 recorded sets
  yield wider CIs (~1/sqrt(n)) than n≈120 synthetic. Changing thresholds.yaml without updating
  the lock + a DECISIONS rationale fails CI.
- Alternatives considered: percent-scale YAML (rejected — inconsistent with scorer floats).
- Consequences: `callscope eval gate|compare`; stats/compare/gate modules.
- Design doc impact: none (clarifies units only).
- Status: accepted

### D-20260921-36 - File-backed eval run store for stage/text-replay CI
- Date / Task: 2026-09-21 / T-M3-05
- Context: Design persists `cs.eval_runs` / `eval_item_results` / `eval_metrics` in Postgres.
  ORM models for eval runs are not yet wired (M4 review API / M5 stack registry); CI must run
  a 20-item golden eval with mocks + cassettes without a live DB.
- Decision: Ship `FileEvalStore` under `artifacts/eval_runs/` mirroring the SQL column shapes
  (`git_sha`, `dataset_id`, `stack_version_id`, `estimated_usd`, per-item rows, slice metrics).
  Same `run_eval` / provider path for Mac live providers. Postgres dump of the same JSON is a
  follow-up when eval API endpoints land (T-M4-02 / T-M5-01).
- Alternatives considered: require Postgres in unit CI (rejected — slows PR gate); skip persist
  until M4 (rejected — acceptance needs eval_runs fields).
- Consequences: CLI `callscope.devtools.eval_cli`; golden set in `tests/golden/eval_items.json`.
- Design doc impact: none (storage backend detail); ADR-007 unchanged.
- Status: accepted

### D-20260920-35 - Receptionist skill registration + prompt hash
- Date / Task: 2026-09-20 / T-M2-04
- Context: Design §4.4 skill `callscope:receptionist`. Hermes 0.19 spike verified tools/hooks
  but not `register_skill` kwargs.
- Decision: Ship versioned `skills/receptionist.md`; `prompt_hash()` = sha256(system preamble +
  skill). Call `ctx.register_skill` when present; always expose `skill_text`/`prompt_hash` for
  worker/stack_versions. Ten fictional dry-plan transcripts under `eval/manual_runs/` (live
  re-runs when Hermes+biz are up). Wording tracked in `docs/prompts/CHANGELOG.md`.
- Alternatives considered: hard-require register_skill (rejected until Hermes API confirmed).
- Consequences: CI asserts guardrail phrases + hash stability + 10 scenario files.
- Design doc impact: none.
- Status: accepted

### D-20260920-34 - Local disk recordings + JSONL retention catalog
- Date / Task: 2026-09-20 / T-M2-06
- Context: Design §4.2/NFR-13 — consent-gated audio, 30-day purge, delete-by-call. Walking
  skeleton API is in-memory (no Postgres required for CI).
- Decision: `CallRecorder` writes 16 kHz mono WAV (caller/agent/mixed) under
  `CALLSCOPE_RECORDINGS_DIR` only when `consent_recording`; register via
  `POST /v1/calls/{id}/recording`. Retention uses a JSONL catalog + `callscope.devtools.retention_cli`
  (`make purge` dry-run by default; `APPLY=1` to delete). Donated+reviewed rows are exempt.
  Example systemd user timer under `infra/purge.{timer,service}`. MinIO upload remains optional
  (URI can be file:// or s3:// once wired).
- Alternatives considered: require MinIO always (rejected for CI); Postgres-only purge (later).
- Consequences: Pure eligibility tests; no cloud retention job.
- Design doc impact: none.
- Status: accepted

### D-20260920-33 - Barge-in stop latency = decision→cancel (not VAD onset)
- Date / Task: 2026-09-20 / T-M2-05
- Context: Design §4.2 `barge_in.min_duration_ms=250` and NFR “stop within 250 ms p95”. Including
  the min-duration wait in `stop_latency_ms` makes the p95 gate impossible (≥250 ms by definition).
- Decision: `InterruptionGate` enforces min duration + grace; `CallSession.interrupt` measures
  **worker-side** stop latency from barge-in *decision* to TTS/brain cancel. `speech_ms` remains
  on `barge_in.applied` for review. Soft-degrade ASR/brain (2 strikes); TTS → text-only; biz →
  callback stash; events → spill (`DegradeController`).
- Alternatives considered: count VAD onset→stop (rejected: conflicts with min_duration).
- Consequences: Scripted p95 test uses fake clock + injectable cancel delay.
- Design doc impact: clarifies metric semantics for §4.10 histogram.
- Status: accepted

### D-20260920-32 - hermes-callscope plugin package + toolset name
- Date / Task: 2026-09-20 / T-M2-02
- Context: Design §4.4; spike T-M0-04 verified `register_tool(..., toolset=)` and JSON-string
  handlers on hermes-agent 0.19.0.
- Decision: Ship editable `plugins/hermes_callscope` (`hermes-callscope`) with entry point
  `hermes_agent.plugins` → `callscope`. Toolset id **`callscope-receptionist`** (matches
  `infra/hermes`). Seven tools call Business API via httpx; mutating tools refuse without
  `confirmed=true` at handler layer (full policy hook in T-M2-03).
- Alternatives considered: keep tools only in spike (rejected).
- Consequences: `uv sync` installs plugin; CI tests schemas/handlers without live Hermes.
- Design doc impact: none.
- Status: accepted

### D-20260920-31 - Business API: in-memory deterministic store for CI
- Date / Task: 2026-09-20 / T-M2-01
- Context: Design §4.5/§6.4 + `biz` schema. Need identical seed→data in CI without requiring
  Postgres for every unit test; schema uses Postgres-only types (tsvector, int4range).
- Decision: Ship FastAPI `apps/biz` with an in-memory `BizStore` that mirrors the biz tables
  and is reseeded via `POST /admin/reset?seed=` (admin bearer). KB ranking is token-overlap
  approximating tsvector for local demo; Postgres-backed store can replace later without
  changing HTTP contracts (`docs/api/biz.openapi.yaml`). Gaps listed in `docs/kb_gaps.md`.
- Alternatives considered: require Postgres for all biz tests (rejected: slower CI); SQLite
  (rejected: no tsvector/int4range parity).
- Consequences: Plugin (T-M2-02) talks HTTP to `:8100`; demo Procfile includes `biz`.
- Design doc impact: none.
- Status: accepted

### D-20260920-30 - make demo: Compose data plane + honcho Procfile; biz/Hermes optional
- Date / Task: 2026-09-20 / T-M1-11
- Context: Design §9 / ADR-015 — ASR/TTS/worker/livekit native; Postgres/Prom/Grafana in Compose.
  Prompt also listed biz + Hermes in the Procfile; `apps/biz` does not exist yet; Hermes needs a
  separate install + `TOKEN_FACTORY_API_KEY`.
- Decision: `make demo` → `scripts/demo_start.sh` (Compose up + `honcho start -f Procfile`).
  Procfile: livekit, api, asr, tts, worker `--serve`, web. **Omit biz** until that app exists.
  **Omit Hermes** from auto-start (document optional run). Grafana provisioned with Live-ops
  dashboard; Prometheus scrapes host.docker.internal :8000/:9100/:8200/:8300. Pin Prom/Grafana
  image tags. CI validates compose/prom/grafana/Procfile via `tests/infra/test_compose_config.py`.
- Alternatives considered: Docker LiveKit only (works but S-6 prefers brew native); include Hermes
  in Procfile (rejected: fail-closed without keys / install).
- Consequences: Full Agents room path still uses spike or future wiring; demo proves ports + metrics.
- Design doc impact: none (implements §9 local runner).
- Status: accepted

### D-20260920-29 - Voice worker: CallSession owns turns; LiveKit Agents glue is config-thin
- Date / Task: 2026-09-20 / T-M1-10
- Context: Design §4.2 + S-4 (D-20260920-05). Need a testable turn loop without
  pulling `livekit-agents[silero]` into default CI deps.
- Decision: Pure `TurnStateMachine` + `CallSession` (STT→brain→chunker→TTS, events,
  data-channel messages, metrics) with injectable providers/media. `WorkerConfig`
  maps §4.2 keys to Agents `TurnHandlingOptions` / Silero VAD kwargs (verified in
  spike). Optional extra `worker` installs livekit-agents; `--livekit` entrypoint
  documents T-M1-11 for full AgentSession STT/TTS/Hermes adapters.
- Alternatives considered: Full Agents plugins in this PR (rejected: heavy CI deps,
  harder FSM unit tests); hermes-livekit (already rejected D-20260920-05).
- Consequences: `make worker --mock-call` smokes the loop; 60 s LiveKit call is a
  manual check once T-M1-11 wires the Agents session to CallScope providers.
- Design doc impact: none (implements §4.2 / ADR-002 / ADR-006).
- Status: accepted

### D-20260920-28 - HermesBackend: SSE client + receptionist toolset lockdown
- Date / Task: 2026-09-20 / T-M1-09
- Context: Need BrainBackend over Hermes 0.19.0 API server; spikes T-M0-02/03/04 verified
  `/v1/chat/completions` SSE, custom TF provider keys, and `platform_toolsets.api_server`.
- Decision: `HermesBackend` uses httpx async SSE; CALL_CONTEXT + optional interruption note on
  the last **user** message (D-20260920-04); `user`=call_id + X-Call-Id/X-Turn-Id headers
  (informational only); first-token timeout default 8s; `cancel` closes the response stream.
  Profile at `infra/hermes/config.yaml`: TF custom provider, `memory_enabled: false`,
  `platform_toolsets.api_server: [callscope-receptionist]` only; `make hermes-selftest` fails
  closed on drift. Live smoke behind `CALLSCOPE_HERMES_LIVE=1` + `@pytest.mark.gpu`.
- Alternatives considered: sync requests (rejected: worker is async); put CALL_CONTEXT in system
  (rejected: invisible to hooks); leave default Hermes toolsets (rejected: terminal/browser risk).
- Consequences: T-M2 plugin must register toolset name `callscope-receptionist`. CassetteBrain
  wraps Hermes as `inner` (hash is pre-CALL_CONTEXT messages).
- Design doc impact: none (implements §4.2 / ADR-001 / ADR-016).
- Status: accepted

### D-20260920-27 - Web client: Vite + vanilla TS + livekit-client
- Date / Task: 2026-09-20 / T-M1-08
- Context: Design §4.2 client; C1. Need consent-before-mic and XSS-safe transcript.
- Decision: `apps/web` Vite vanilla TypeScript (no framework). `livekit-client` 2.x
  `Room` + `createLocalAudioTrack` (AEC/NS/AGC on) verified from installed package.
  Data topic `callscope`. Strict CSP meta. Vitest for UI state + XSS. `make web-*` + CI `web` job.
- Alternatives considered: React (rejected — prompt says vanilla); hermes-livekit web (out of scope).
- Consequences: Live call still needs T-M1-10 worker for agent audio/transcripts.
- Design doc impact: none.
- Status: accepted

### D-20260920-26 - CallScope API: memory store + concurrent cap (no per-IP limits)
- Date / Task: 2026-09-20 / T-M1-07
- Context: OpenAPI session/status/events; ADR-010 removed public per-IP abuse limits;
  backlog AC: no captcha / public-abuse rate-limit paths. Prompt still mentioned IP caps —
  follow ADR-010 + backlog AC.
- Decision: `apps/api` implements `/v1/status`, `/v1/sessions`, `/v1/sessions/{id}/end`,
  `/v1/events:batch`, `/metrics`. Default `MemoryCallStore` for CI (Postgres repos remain for
  later wiring). Concurrent session cap = 2 (`SessionCapLimiter`); token TTL 300 s via
  `livekit-api` 1.2.1 `AccessToken` (verified). Service bearer on events batch. RFC 7807
  problem+json. No captcha / per-IP rate limit code.
- Alternatives considered: require Postgres in every unit test (rejected for CI speed);
  implement per-IP limits (rejected — ADR-010 / AC).
- Consequences: `make api`; SQL-backed store can replace MemoryCallStore when demo uses Compose.
- Design doc impact: none (aligns ADR-010).
- Status: accepted

### D-20260920-25 - TTS server: fake default; Piper + kokoro-onnx optional
- Date / Task: 2026-09-20 / T-M1-06
- Context: Design §4.3 + S-5 shortlist (D-20260920-19). Port **8300**.
- Decision: FastAPI `servers/tts` with `POST /v1/tts/stream` (chunked `audio/L16`,
  `X-Sample-Rate`), `GET /v1/voices`, `/healthz`, `/metrics` (TTFB, RTF, chars/s).
  Default backend `fake` (cancellable sine). Optional `piper` (chunked synth from spike
  API; GPL-3.0-or-later voice — redistribution caution) and `kokoro_onnx` (full
  `create` then 20 ms chunking; Apache-2.0). Warm-up on lifespan. `TTSClient` implements
  `TTSProvider`. Never log synthesis text.
- Measurements: Piper/Kokoro TTFB/RTF from S-5 (`spikes/T-M0-06/results/`); fake exposes
  the same Prometheus metrics in CI.
- Alternatives considered: always-on Piper (rejected — GPL + weights in CI).
- Consequences: `make tts`; `CALLSCOPE_TTS_*` in `.env.example`.
- Design doc impact: none.
- Status: accepted

### D-20260920-24 - LLM cassettes: content-hash store + CassetteBrain wrapper
- Date / Task: 2026-09-20 / T-M1-13
- Context: ADR-016 / NFR-06 / NFR-11. HermesBackend (T-M1-09) not built yet; need a
  replay surface CI can use now and Hermes can wrap later.
- Decision: `CassetteStore` under `eval/cassettes/{hash[:2]}/{hash}.json`. Hash =
  SHA-256 of messages (+ optional model), **excluding** call_id/turn_id. `CassetteBrain`
  wraps any `BrainBackend`: default/`CI`/`CALLSCOPE_ENV=test` → replay-only (missing
  fails closed); `--live` / `CALLSCOPE_LLM_MODE=live|record` requires `BudgetGuard` then
  records. Fixtures redacted on save. Contract tests use MockBrain as the inner.
- Alternatives considered: HTTP MITM proxy (heavier); hash including call_id (breaks
  cross-call replay).
- Consequences: T-M1-09 plugs Hermes as `inner`; eval runner (T-M3-*) defaults to replay.
- Design doc impact: none (implements ADR-016).
- Status: accepted

### D-20260920-23 - ASR server: fake default, EnergyVAD, mlx-whisper optional
- Date / Task: 2026-09-20 / T-M1-05
- Context: Design §4.3 + S-5 shortlist (D-20260920-19). Whisper-family is not natively
  streaming; CI must not load Metal weights.
- Decision: FastAPI `servers/asr` on port **8200** (`make asr`). Default backend `fake`
  (`CALLSCOPE_ASR_BACKEND=fake`). Optional `mlx_whisper` (`mlx-community/whisper-tiny`) loaded
  only in lifespan / first use — never at import. Energy VAD (no torch) segments for the
  non-streaming path; Silero stays on the LiveKit worker (T-M0-05). Hotwords → Whisper
  `initial_prompt` when using mlx. `ASRClient` implements `STTProvider`.
- Measurements: unified-memory / RTF for mlx-whisper-tiny from S-5 (RTF C0 mean ~0.03; see
  `spikes/T-M0-06/results/`). Fake backend exposes the same Prometheus RTF/latency metrics for
  contract tests (no claim of production RTF from fake).
- Alternatives considered: Silero inside ASR process (rejected — torch in CI); always-on mlx
  (rejected — import/load cost + CI).
- Consequences: `CALLSCOPE_ASR_*` in `.env.example`; gpu-marked mlx test gated by
  `CALLSCOPE_RUN_GPU=1`.
- Design doc impact: none (matches §4.3 / port table).
- Status: accepted

### D-20260920-22 - Alembic baseline = schema.sql; catalog fingerprint for drift
- Date / Task: 2026-09-20 / T-M1-02
- Context: Acceptance asks for pg_dump equivalence; CI/local Mac may lack client tooling consistency.
- Decision: Migration `0001` executes `db/schema.sql` verbatim. Drift test compares a stable
  `information_schema` / `pg_catalog` fingerprint of schemas `cs`+`biz` after Alembic vs after
  applying schema.sql (not raw pg_dump text). Async SQLAlchemy + psycopg3 driver.
- Alternatives considered: hand-written Alembic ops mirroring DDL (drift-prone); require pg_dump in CI.
- Consequences: `make db-upgrade`; repos in `callscope/db/`; compose init still mounts schema.sql for empty volumes.
- Design doc impact: none (schema already Appendix A).
- Status: accepted

### D-20260920-21 - Budget guard: catalog $/1M x usage tokens; eval_runs.estimated_usd
- Date / Task: 2026-09-20 / T-M1-12
- Context: ADR-016 / NFR-11. Token Factory chat completions expose OpenAI-compatible
  `usage.prompt_tokens` / `usage.completion_tokens` (spikes T-M0-03/07). Public catalog
  prices in D-20260920-12. No documented `usage.cost` field — do not invent one.
- Decision: `BudgetGuard` estimates USD as tokens x catalog $/1M for known model IDs;
  `require_live_budget` fails closed; `make budget` / `--estimate` / `--check` CLI;
  add nullable `cs.eval_runs.estimated_usd` (+ OpenAPI) for upcoming eval runs (Alembic in T-M1-02).
- Alternatives considered: persist spend only in `.env` (insufficient for eval audit);
  invent TF cost field (rejected — not in observed responses).
- Consequences: live/eval entrypoints call `require_live_budget` before network; cassettes (T-M1-13) remain free.
- Design doc impact: schema Appendix A column; ADR-016 unchanged in spirit.
- Status: accepted

### D-20260920-20 - S-2: Hermes TTFT overhead fails 450 ms gate; adopt thin FAQ fast-path (R-02)
- Date / Task: 2026-09-20 / T-M0-03
- Context: Spike S-2 (U2). hermes-agent 0.19.0 API server → Token Factory custom provider vs OpenAI-compatible client → TF direct. Model `nvidia/Nemotron-3_5-Lightning`. 50 streamed turns, empty toolset, slim spoken system string. Run `6a3855de-f0f2-45e4-906a-5af9defb2c49`; ~$0.006 spend. Raw: `spikes/T-M0-03/results/ttft_overhead.json`.
  | Path | TTFT p50 | TTFT p95 | Mean prompt tokens |
  |---|---:|---:|---:|
  | TF direct | 884 ms | 989 ms | ~47 |
  | Hermes→TF | 2287 ms | 3779 ms | ~507 |
  | Overhead (H−D) | **1385 ms** | 2907 ms | +~460 |
  Mitigation attempt `memory_enabled: false` (20 turns) did not reduce prompt tokens (~507) or pass the gate (overhead p50 ~1.8 s).
- Decision: **S-2 gate FAIL** vs Hermes-own ≤450 ms p50. Activate **R-02**: voice worker uses a **thin FAQ/chitchat fast-path** (direct TF or local canned) for no-tool turns; **Hermes only for tool/plan turns**. Re-measure after T-M1-09 receptionist profile lockdown. Update §3.6 notes for hosted-TF reality.
- Alternatives considered: accept 1.4 s Hermes tax on every turn (rejected — breaks NFR-01 headroom); fork Hermes to strip system prompt (rejected — black-box constraint); local vLLM (out of Mac scope).
- Consequences: T-M1-08/09 worker routing; design §3.6 + U2/S-2 resolved with mitigation; do not treat 350–450 ms Hermes→token row as achievable on TF without the split.
- Design doc impact: U2, S-2, §3.6 rows annotated; R-02 selected.
- Status: accepted

### D-20260920-19 - S-5: ASR/TTS/VAD shortlist on Apple Silicon
- Date / Task: 2026-09-20 / T-M0-06
- Context: Native Mac probe (no Docker Metal). 30 synthetic utterances under `eval/probe/` (macOS `say` Albert; C0 + C1 telephony). Measured RTF, ΔRSS, WER (orthography-sensitive on spoken digits), TTS first-audio, Silero VAD. Parakeet BF16 ~2.5 GB skipped (size gate). Raw: `spikes/T-M0-06/results/benchmark.json`.
  - **ASR shortlist:** (1) `mlx-whisper` / `mlx-community/whisper-tiny` — RTF C0 mean ~0.03 (Metal); (2) `faster-whisper` base — best WER on this probe (C0 ~0.69 / C1 ~0.74), CPU. Neither is natively streaming → VAD-segmented chunking.
  - **TTS shortlist:** (1) Piper `en_US-lessac-medium` — first-audio p50 ~53 ms / p95 ~125 ms, RTF ~0.03, **GPL-3.0-or-later** (distribution caution); (2) `kokoro-onnx` v1.0 — Apache-2.0, first-audio p50 ~611 ms (non-stream).
  - **VAD:** Silero (`silero-vad` pip; also LiveKit Agents path from T-M0-05) — utterance p50 ~8 ms, MIT.
- Decision: Adopt the shortlist above for T-M1-05/06 native servers. Prefer Piper for latency demos if GPL redistribution is acceptable for the portfolio; otherwise Kokoro. Prefer mlx-whisper-tiny for live path RTF with faster-whisper-base as quality/CPU fallback.
- Alternatives considered: Parakeet-mlx BF16 (skipped size); whisper-base.en-mlx (worse WER than tiny on this synthetic set + heavier load); cloud ASR/TTS (rejected).
- Consequences: design §9.5 ASR/TTS/VAD rows filled; U5/S-5 resolved; E2 LoRA deferred (fits RAM, needs real telephony train set) — T-M5-05 remains optional.
- Design doc impact: U5, S-5, §9.5; supersedes “pending measurements” on D-20260920-14.
- Status: accepted

### D-20260920-18 - S-3: Choose Nemotron-3.5-Lightning on Token Factory via Hermes
- Date / Task: 2026-09-20 / T-M0-04
- Context: Spike S-3 (U3). hermes-agent 0.19.0 API server with custom provider → Token Factory (`https://api.tokenfactory.nebius.com/v1/`). Stub receptionist toolset locked to `callscope-s3` (no terminal/browser). 60 scripted turns × 3 function_calling candidates. Run ID `394d90d9-702a-44db-b081-be6ee0879428`; raw `spikes/T-M0-04/results/tool_reliability.json`. Total est. spend ~$0.080.
  | Model | Valid tool-call rate | p50 turn (Hermes) | Est. USD |
  |---|---:|---:|---:|
  | nvidia/Nemotron-3_5-Lightning | 100% (60/60) | ~2.7 s | ~0.024 |
  | Qwen/Qwen3-30B-A3B-Instruct-2507 | 100% (60/60) | ~4.8 s | ~0.026 |
  | nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | 98.3% (59/60) | ~10.8 s | ~0.031 |
  Licences/prices per D-20260920-12. Nano miss: one booking turn with no tool call. Injection turns: 0 forbidden tools for all three.
- Decision: **Demo agent LLM = `nvidia/Nemotron-3_5-Lightning`** on Token Factory through Hermes. Alternate: `Qwen/Qwen3-30B-A3B-Instruct-2507`. Optional local mlx-lm/llama.cpp fallback sketched only (`spikes/T-M0-04/docs/local_fallback.md`); not a gate. Avoid Ollama primary (D-20260920-13).
- Alternatives considered: Nano as default (rejected: slower + one miss); Qwen as default (acceptable alternate, slightly higher cost/latency); local-only LLM (deferred — memory budget with ASR/TTS).
- Consequences: set `TOKEN_FACTORY_MODEL` default; T-M0-03 overhead spike uses this model; production plugin must return JSON **strings** from tool handlers (Hermes 0.19 contract).
- Design doc impact: U3 / S-3 resolved; `.env.example` model default updated.
- Status: accepted

### D-20260920-17 - S-6: Mac baseline, native livekit-server, Token Factory regional RTT
- Date / Task: 2026-09-20 / T-M0-07
- Context: Spike S-6 under local-Mac scope. Measured on Apple M5 / 16 GB / macOS 26.6.2 arm64. Installed Homebrew `livekit` 1.13.7 (arm64 bottle). Ran `livekit-server --dev --config-body "port: 17880"` → HTTP 200 (port 7880 was held by Docker Desktop publishing an older LiveKit). Probed Token Factory edges with 100 TCP + 20 HTTPS samples/region (no API key; no chat spend). Raw: `spikes/T-M0-07/results/`.
- Decision: (1) Size local models to ≈12 GB usable (reserve ≥4 GB). ASR/TTS memory deferred to T-M0-06. (2) **Keep ADR-002** — native livekit-server works on macOS; no FastAPI WebSocket fallback ADR. For demo, prefer native on 7880 or document Docker conflict. (3) Prefer Token Factory **us-central1** for network RTT from this location (TCP p50 ≈ 50 ms vs ≈ 191 ms eu-north1). If the chosen model only exists in eu-north1, accept the higher floor and measure chat TTFT in T-M0-04. (4) Chat probe (100 non-streaming tiny completions) on `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` via default `api.tokenfactory.nebius.com`: **p50 699 ms / p95 824 ms**, ~$0.00022 spend, 0 errors (`spikes/T-M0-07/results/tf_chat_ttft.json`).
- Alternatives considered: Docker-only LiveKit (works but 7880 conflict / no need); skip regional probe (rejected — catalog regions differ).
- Consequences: design §9.5 updated; start/stop notes in `spikes/T-M0-07/docs/START_STOP.md` (input to T-M6-03). NFR-01 brain budget must include ~0.7 s hosted hop on eu-north1 for this model class.
- Design doc impact: §9.5 filled; U6 resolved by S-6 / D-20260920-17.
- Status: accepted

### D-20260920-16 - Toloka for TEXT human labels (optional stretch); privacy notes
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: $100 Toloka credit available. Docs: platform API can drive TEXT labelling pipelines ([Programmatic access](https://platform.toloka.ai/docs/integration/programmatic-access/)); unverified teams are on trial and **cannot start a run** until identity/business verification. Platform does not delete datasets via UI/API in the product itself — deletion is account-level under the Privacy Notice ([Security and data handling](https://platform.toloka.ai/docs/explanation/security-and-data-handling/), [Privacy Notice](https://toloka.ai/legal/privacy-notice)). DPA: delete/return on termination subject to legal retention.
- Decision: Optional stretch only for ≥50 fictional agent utterances (supported/unsupported) and optional RCA labels on fictional transcripts. **Never upload audio or real personal data.** If verification/minimum spend/terms do not fit, use manual labelling and record that choice.
- Alternatives considered: skip human labels (weakens judge calibration); upload audio (rejected).
- Consequences: T-M3-08 accepts Toloka or manual; document choice in DECISIONS when executed.
- Design doc impact: §8.6 data-flow.
- Status: accepted

### D-20260920-15 - LangSmith optional tracing (off by default); retention notes
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: $100 LangSmith credit. Python SDK supports tracing; OpenTelemetry ingestion to `https://api.smith.langchain.com/otel` (recommend langsmith≥0.4.25) ([OTEL docs](https://docs.langchain.com/langsmith/trace-with-opentelemetry.md)). Trace retention: base **14 days** or extended **400 days**; datasets retain indefinitely ([usage/billing](https://docs.langchain.com/langsmith/usage-and-billing)). Hide/redact inputs via SDK flags or collector.
- Decision: Optional behind `CALLSCOPE_LANGSMITH_ENABLED` (default off). Trace scrubbed **fictional text only** (brain turns + eval items). Postgres remains SoT (ADR-006). Decide later whether LangSmith datasets/experiments earn a place for judge eval (T-M4-06); if not, document why.
- Alternatives considered: always-on tracing (unnecessary cost/privacy surface); skip entirely (forfeit credit/learning).
- Consequences: T-M4-06; scrubber must run first.
- Design doc impact: §8.6; ADR-017 adjacent.
- Status: accepted

### D-20260920-14 - Apple Silicon ASR/TTS/VAD candidates (docs/PyPI/GitHub; not yet run on this Mac)
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: No CUDA; Docker Desktop cannot use Mac GPU/Metal for containers — ASR/TTS must run natively. Candidates checked from public docs (not installed/benchmarked yet; T-M0-06 runs them):
  - **ASR:** `mlx-whisper` / Whisper via [mlx-audio](https://github.com/Blaizzy/mlx-audio) (MIT); [parakeet-mlx](https://github.com/senstella/parakeet-mlx) Apache-2.0 (weights often CC-BY-4.0 with attribution); whisper.cpp Metal/Core ML; faster-whisper CPU-only on Mac.
  - **VAD:** Silero VAD (ONNX/torch CPU) — already used in LiveKit Agents spike.
  - **TTS:** Kokoro via mlx-audio / [kokoro-mlx](https://pypi.org/project/kokoro-mlx/) (MIT code; Kokoro weights Apache-2.0); kokoro-onnx; Piper (CPU ONNX; GPL-3.0-or-later — licence caution for distribution).
- Decision: Shortlist by **running** on this Mac in T-M0-06 (RTF, memory, first-audio, WER clean vs C1). Prefer streaming ASR; else VAD-segmented chunking. E2 LoRA only if whisper-small/base fits in remaining RAM via MPS/MLX; else defer (T-M5-05).
- Alternatives considered: cloud ASR/TTS (rejected: portfolio story); Dockerized GPU ASR (impossible on Mac Desktop).
- Consequences: T-M0-06 / T-M1-05 / T-M1-06 native servers.
- Design doc impact: §4.3, §9.5.
- Status: accepted (measurements completed in D-20260920-19 / T-M0-06)

### D-20260920-13 - livekit-server and Hermes on macOS; prefer Token Factory over Ollama
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context:
  - LiveKit docs: `brew install livekit` then `livekit-server --dev` ([local self-hosting](https://docs.livekit.io/transport/self-hosting/local/)); Homebrew formula ships arm64 bottles, Apache-2.0 ([formulae.brew.sh/formula/livekit](https://formulae.brew.sh/formula/livekit)). **Not yet executed on this machine** — verify in T-M0-07. Fallback if fail: FastAPI WebSocket audio + own VAD (new ADR + tasks).
  - Hermes: installs on macOS; custom OpenAI-compatible provider via `hermes model` / `config.yaml` `provider: custom` + `base_url` ([providers docs](https://hermes-agent.nousresearch.com/docs/integrations/providers); [local LLM on Mac](https://hermes-agent.nousresearch.com/docs/guides/local-llm-on-mac) recommends mlx-lm / llama.cpp). Prior design note V7: Ollama stream+tools hang risk → avoid Ollama as primary.
- Decision: Keep ADR-002; run livekit-server natively. Hermes → Token Factory as custom provider; optional mlx-lm/llama.cpp fallback. Confirm end-to-end in S-6 / S-3.
- Alternatives considered: Docker-only LiveKit (works but extra networking); Ollama primary (rejected).
- Consequences: T-M0-07 acceptance includes brew `--dev` proof.
- Design doc impact: ADR-002 kept; ADR-014/015.
- Status: accepted (pending S-6 runtime proof)

### D-20260920-12 - Nebius Token Factory API facts, candidate LLMs, $25 budget estimate
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: Public docs (no API spend during this rescope):
  - Base URL: `https://api.tokenfactory.nebius.com/v1/` ([list models example](https://docs.tokenfactory.nebius.com/api-reference/examples/list-of-models)).
  - Auth: Bearer API key (`NEBIUS_API_KEY` / we will use `TOKEN_FACTORY_API_KEY` in CallScope `.env`).
  - Catalog: public [`/api/public/models_info`](https://tokenfactory.nebius.com/api/public/models_info) + [model-catalog.md](https://tokenfactory.nebius.com/model-catalog.md) (fetched 2026-09-20).
  - Tools: OpenAI-compatible function calling documented ([function-calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md)); chat completions support `stream` ([API ref](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion)).
  - Rate limits: dynamic; headers `x-ratelimit-*`; HTTP 429 + `Retry-After` ([rate-limits](https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md)). Per-model `per_request_limits` appear in verbose `/v1/models` responses (requires key — **not queried** this session).
  - Speech ASR/TTS: **none** found in the 24-entry public catalog (text2text / image2text / embedding only). Embeddings: e.g. `Qwen/Qwen3-Embedding-8B` @ $0.01/M input.
- Decision: Use Token Factory for the agent LLM (and a different model for the judge). Candidate **function_calling** text2text models from the public catalog (prices USD per 1M tokens):

  | Model ID | In | Out | Licence (catalog) |
  |---|---:|---:|---|
  | nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | 0.06 | 0.24 | nvidia-open-model-license |
  | nvidia/Nemotron-3_5-Lightning | 0.06 | 0.24 | OpenMDW v1.1 |
  | Qwen/Qwen3-30B-A3B-Instruct-2507 | 0.10 | 0.30 | Apache 2.0 |
  | google/gemma-3-27b-it | 0.10 | 0.30 | Gemma License |
  | deepseek-ai/DeepSeek-V4-Flash-0731 | 0.14 | 0.28 | MIT |
  | openai/gpt-oss-120b | 0.15 | 0.60 | Apache 2.0 |
  | Qwen/Qwen3-235B-A22B-Instruct-2507 | 0.20 | 0.60 | Apache 2.0 |

  **$25 budget sketch (assumption, not a measurement):** ~4k input + 300 output tokens/turn ≈ $0.00049/turn on Qwen3-30B → on the order of **~50k turns** raw, or roughly **hundreds to low thousands of multi-turn receptionist calls** once tools, retries, judge calls, and eval are included. Prefer Nemotron Nano / Qwen3-30B class for cost; keep a $10 reserve (cap $15 default). **Verify tool quality in T-M0-04 before locking.**
- Alternatives considered: local-only LLM (tight on 16 GB with ASR+TTS); spend without cassettes (rejected).
- Consequences: ADR-014/016; T-M0-03/04; no speech models from TF.
- Design doc impact: §4.4, §9, ADR-014.
- Status: accepted

### D-20260920-11 - Machine facts (Apple M5, 16 GB)
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: Ran on this machine: `sysctl -n machdep.cpu.brand_string` → **Apple M5**; `hw.memsize` → 17179869184 (**16 GB**); `sw_vers` → macOS 26.6.2 (25G83); `uname -m` → **arm64**.
- Decision: Size all local model choices to ≤ ~12 GB working set (reserve ≥4 GB for OS + browser). Concurrency default 1 (NFR-03).
- Alternatives considered: n/a (hardware fact).
- Consequences: drives S-5/S-6 memory tables; E2 optional/deferred likely.
- Design doc impact: §9.5 baseline filled.
- Status: accepted

### D-20260920-10 - Rescope: local Mac demo + Token Factory LLM (supersedes GPU VM public demo)
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: Nebius access is Token Factory inference only (no VM provisioning); no other cloud GPU credits. Program credits: Token Factory $25, LangSmith $100, Toloka $100; Tavily not used.
- Decision: Apply ADR-014..017; drop public-demo controls; rewrite backlog (T-M6-04 dropped); deliver `make demo` + video + static showcase.
- Alternatives considered: pause project until GPU credits (rejected); public demo without GPU (infeasible for self-hosted LLM).
- Consequences: large backlog/design update; old total ~459 h → new ~462 h (excl. dropped); schedule regenerated in DEV_GUIDE §5.
- Design doc impact: revision changelog; ADRs; §§1–2, 3.6, 4, 8–12.
- Status: accepted

### D-20260920-05 - S-4: Keep own LiveKit Agents worker; do not adopt hermes-livekit
- Date / Task: 2026-09-20 / T-M0-05
- Context: Spike S-4 (U4). Installed `livekit-agents[silero]==1.8.2`, `livekit==1.1.18`, `livekit-api==1.2.1`; ran `livekit/livekit-server:v1.9.1 --dev`. Minimal AgentServer worker with EchoSTT (`StreamAdapter`+Silero), CannedLLM, SineTTS under `spikes/T-M0-05/`. Headless smoke `SMOKE_OK agent_audio_subscribed` on room `callscope-spike-2` after adding `RoomAgentDispatch` to caller tokens. Reviewed `kortexa-ai/hermes-livekit` 0.4.0 @ `640812f` (MIT; requires Hermes ≥0.20.0 not on PyPI; not LiveKit Agents-based). Config mapping in `spikes/T-M0-05/results/config_mapping.md`.
- Decision: **Confirm ADR-002** — assemble the realtime loop with **our** LiveKit Agents worker + provider adapters. **Do not adopt** `hermes-livekit` for the demo path. Map design §4.2 keys onto `TurnHandlingOptions` / Silero `VAD.load` / `aec_warmup_duration` (seconds). Pipecat remains the documented fallback only if Agents wiring regresses.
- Alternatives considered: adopt hermes-livekit (rejected: Hermes 0.20+ unavailable, weak FR-06 stage events, couples media to Hermes); Pipecat now (rejected: unnecessary — Agents stubs work); custom aiortc (rejected: more ownership than needed).
- Consequences: T-M1-10 implements the real worker against this mapping; session tokens must include agent dispatch; interruption fidelity work stays in T-M2-05. Native brew livekit-server re-verified in T-M0-07.
- Design doc impact: ADR-002 status note + U4/S-4 rows marked resolved by S-4 / D-20260920-05; §4.2 mapping footnote.
- Status: accepted

### D-20260920-04 - S-1: API-server metadata does not reach Hermes hooks; keep CALL_CONTEXT fallback
- Date / Task: 2026-09-20 / T-M0-02
- Context: Spike S-1 (U1). Installed `hermes-agent==0.19.0` (latest on PyPI; design cited 0.20.0 — not published). Python 3.12.13 scratch venv under `spikes/T-M0-02/`. Verified APIs from installed source (`hermes_cli.plugins.PluginContext.register_hook`, `agent.turn_context` `pre_llm_call` kwargs, `gateway.platforms.api_server._handle_chat_completions` / `_write_sse_chat_completion`). Ran correlation matrix + SSE close probe with a mock OpenAI stub; scrubbed evidence in `spikes/T-M0-02/results/`.
- Decision: **No** — OpenAI body `user` and headers `X-Call-Id`/`X-Turn-Id` do **not** appear in plugin hook kwargs. System-role `CALL_CONTEXT` also does **not** appear in `pre_llm_call` (`user_message` / `conversation_history`) because system text becomes `ephemeral_system_prompt`. **Keep** the §4.4 fallback, refined: put `CALL_CONTEXT call_id=<uuid>` in the **user** message content (not system), and require `call_id` on every tool schema (visible to `pre_tool_call.args`). ADR-006 (worker = latency SoT) stays. SSE client disconnect is handled in source via `agent.interrupt` + task cancel.
- Alternatives considered: rely on Hermes-internal `session_id`/`turn_id` (rejected: not CallScope UUIDs); put CALL_CONTEXT only in system (rejected: invisible to hooks); invent header plumbing in a Hermes fork (rejected: black-box constraint).
- Consequences: BrainBackend / worker (T-M1-09+) must send CALL_CONTEXT on user turns; plugin policy continues to validate tool `call_id`. Estimates unchanged.
- Design doc impact: §4.4 Correlation paragraph updated; ADR-006 status note (U1 resolved); U1 row marked resolved by S-1.
- Status: accepted

### D-20260920-02 - Align pre-commit ruff with project ruff 0.16.8
- Date / Task: 2026-09-20 / T-M0-01
- Context: Hook pin `astral-sh/ruff-pre-commit@v0.5.7` auto-fixed `@pytest.mark.integration` to `@pytest.mark.integration()`, which fails PT023 under project `ruff==0.16.8` used by CI (`uv run ruff`).
- Decision: Bump pre-commit ruff hook to `v0.16.8` to match `uv.lock`.
- Alternatives considered: ignore PT023 (rejected); keep dual versions (rejected: fight on every commit).
- Consequences: first `pre-commit run` after pull may re-download the hook env.
- Design doc impact: none.
- Status: accepted

### D-20260920-01 - CI pip-audit via uv export, not --strict --skip-editable
- Date / Task: 2026-09-20 / T-M0-01
- Context: `uv sync` installs `callscope` editable. Installed `pip-audit` 2.10.1 (`pip_audit._cli`): `--skip-editable` yields `SkippedDependency`, and `--strict` fatals on any skip (`callscope: distribution marked as editable`). Combining both flags made the security job always fail.
- Decision: In CI, `uv export --frozen --no-emit-project --extra dev` then `pip-audit -r … --strict --disable-pip`. Keep `--strict` for third-party collection failures; omit the local project from the audit set.
- Alternatives considered: drop `--strict` (weakens gate); drop `--skip-editable` and audit editable (fails for other reasons / noise); ignore vuln for callscope (wrong tool).
- Consequences: security job audits locked deps only; local package changes are covered by tests/mypy/ruff, not CVE DB.
- Design doc impact: none (aligns with §4.12 gitleaks + dependency audit in CI).
- Status: accepted

### D-20260919-01 - Schedule re-baselined from the task backlog
- Date / Task: 2026-09-19 / T-M0-01
- Context: The design doc (12.3) guessed 5-6 weeks part-time. Bottom-up estimates in backlog/tasks.yaml total 459 h (P0: 375 h, P1-P3: 84 h): M0 43, M1 106, M2 58, M3 92, M4 60, M5 50, M6 50.
- Decision: Plan from the backlog, not the guess. At 30 h/week that is about 15 weeks for everything, about 12.5 weeks for P0 only. Re-estimate after sprints S1 and S2 using actual hours (velocity ratio). If a shorter path is needed use the thin-slice cut in docs/DEV_GUIDE.md section 5.
- Alternatives considered: shrink estimates to fit 6 weeks (rejected: not credible); drop protected M3-M5 (rejected: it is the portfolio value).
- Consequences: sprint plan in DEV_GUIDE section 5; milestone dates move; design 12.3 effort sentence updated.
- Design doc impact: section 12.3 effort sentence only.
- Status: accepted (hours superseded by D-20260920-10 rescope totals)
