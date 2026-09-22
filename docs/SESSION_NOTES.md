# Session notes (newest first)
Short handoff log so a fresh Cursor chat can resume. Add an entry at the end of every session.

Template:
- Date / task:
- Done:
- Next:
- Open questions / blockers:
- Commands to resume:

## 2026-09-22 / T-M6-02
- Done: `tests/security/` §8.3 suite; scrub expanded; CI marker; D-20260922-46.
- Next: PR merge → T-M6-03 demo runbook / showcase.
- Commands: `make security-test`; `make ci`

## 2026-09-22 / T-M6-01
- Done: load harness + session-cap probe; report `load-694f5a9867b5`; D-20260922-45
  (cap=2; NFR-01 projected gap). Merged #103.
- Next: T-M6-02 security suite.
- Commands: `make load`; `make ci`

## 2026-09-22 / M5 close + T-M5-05
- Done: E2 LoRA deferred (D-20260922-44); `docs/experiments/E2.md`; `docs/sprints/M5-review.md`;
  version `0.5.0` tagged (`v0.5.0`).
- Next: T-M6-01 concurrency/latency.
- Commands: `git switch main && make status T=T-M6-01 S=in_progress`

## 2026-09-22 / T-M5-04
- Done: cards/reports/risk/lifecycle; transition gates; sample model card; tests; #101 merged
  (audio HMAC dotted-URI fix).
- Next: T-M5-05 defer → M5 close.
- Commands: `make ci`; inspect `docs/model_cards/`

## 2026-09-22 / T-M5-03
- Done: Chose E3; hypothesis locked; grid + oracle proxy; adopt WorkerConfig defaults;
  MLflow `cd36bba1573c46a182d703bd3024d6ca`.
- Next: PR merge → T-M5-04 governance generator (then optional T-M5-05 defer).
- Commands: `make experiment ARGS='e3 --out artifacts/experiments/e3'`

## 2026-09-22 / T-M5-02
- Done: E1 hypothesis locked first; domain hotword vocab; offline proxy eval (adopt);
  worker `with_domain_hotwords`; `eval/hotwords.txt`; MLflow run logged.
- Next: PR merge → T-M5-03 (E3 vs E2 from review distribution; likely E3 if turn-taking).
- Commands: `make experiment ARGS='e1 --out artifacts/experiments/e1'`

## 2026-09-22 / T-M5-01
- Done: `ModelStackRegistry` + `mlflow_utils`; M0 backfill; eval CLI stack gate + optional
  MLflow log; API inventory sync; Compose `mlflow`; tests.
- Next: PR merge → T-M5-02 E1 ASR hotword experiment.
- Commands: `make ci`; `make governance ARGS=backfill`; `uv sync --extra governance`

## 2026-09-22 / v0.4.0
- Done: version bump + CHANGELOG `[0.4.0]`; annotated tag after merge.
- Next: T-M5-01 MLflow + model/stack registry.
- Commands: `git switch main && make status T=T-M5-01 S=in_progress`

## 2026-09-22 / M4 close
- Done: T-M4-01..06 merged (#90–#95); `docs/sprints/M4-review.md`.
- Next: M5 improvement/governance (T-M5-01); optional `v0.4.0` tag approval.
- Open: Volunteer recorded WAVs (D-20260921-38); version tags held.
- Commands: `git switch main && make status T=T-M5-01 S=in_progress`

## 2026-09-22 / T-M4-06
- Done: optional LangSmith tracer + TracingBrain; decision to skip LS datasets for judge.
- Next: PR merge; M4 close ceremony if all tasks done.
- Commands: `CALLSCOPE_LANGSMITH_ENABLED=false make ci`

## 2026-09-22 / T-M4-05
- Done: quality-drift + cost Grafana dashboards, alerts.yml, eval Prometheus exporter.
- Next: PR merge → T-M4-06 LangSmith optional.
- Commands: `make ci`; open Grafana after `make demo`

## 2026-09-22 / T-M4-04
- Done: `callscope/sim/{caller,oracle}`, `runner_sim`, `eval --mode caller_sim`, tests.
- Next: PR merge → T-M4-05 dashboards.
- Commands: `make eval ARGS='run --mode caller_sim --stack mock'`

## 2026-09-21 / T-M4-03
- Done: Streamlit review console, API client, seed-demo (40 planted calls), helpers/tests.
- Next: PR merge → T-M4-04 caller-sim.
- Commands: `make api` + `make review` / `make review-seed`

## 2026-09-21 / T-M4-02
- Done: review/eval/model API routes, `ReviewStore`, signed audio URLs, contract tests.
- Next: PR merge → T-M4-03 Streamlit review console.
- Commands: `git switch feat/T-M4-02-review-api && make ci`

## 2026-09-21 / T-M4-01
- Done: `callscope/review/{timeline,flags,attribution}.py` + pos/neg tests per rule.
- Next: PR merge → T-M4-02 review API endpoints.
- Commands: `git switch feat/T-M4-01-review-flags && make ci`

## 2026-09-21 / M3 close + start M4
- Done: M3 tasks #80–#88 merged; `docs/sprints/M3-review.md`; filler flake hardened.
- Next: T-M4-01 auto-flag / attribution; optional `v0.3.0` tag approval.
- Open: Volunteer recorded WAVs (D-20260921-38); version tag held.
- Commands: `git switch main && make status T=T-M4-01 S=in_progress`

## 2026-09-21 / T-M3-08
- Done: `claims.py` / `judge.py` / `safety.py`, `eval/judge_calibration.jsonl` (55 labels,
  kappa≥0.8), tests for supported/unsupported/injection.
- Next: PR merge; M3 close ceremony if all tasks done (recorded WAVs still volunteer-gated).
- Commands: `git switch feat/T-M3-08-hallucination-safety && make ci`

## 2026-09-21 / T-M3-07
- Done: `docs/recording_protocol.md`, `datasets/recorded.py` + CLI ingest/export/import/freeze,
  `docs/reports/baseline.md` citing run `39692d2c-…` (mock golden); D-20260921-38. **Merged** (#86).
- Next: Volunteer recordings; T-M3-08.
- Open: Recorded 15/15 acceptance blocked on humans (tooling complete).
- Commands: `git switch main`

## 2026-09-21 / T-M3-06
- Done: `stats.py` / `compare.py` / `gate.py`, `eval/thresholds.yaml`, `docs/thresholds.lock`,
  CLI gate/compare, CI-width note (D-20260921-37). **Merged** (#85).
- Next: T-M3-07 recorded set + baseline.
- Commands: `git switch main && make status T=T-M3-07 S=in_progress`

## 2026-09-21 / T-M3-05
- Done: `callscope/eval/{runner,replay,persist}.py`, `devtools/eval_cli.py`, golden 20-item set,
  cassette + budget estimate/refusal tests; file store (D-20260921-36). **Merged** (#84).
- Next: T-M3-06 stats/compare/gate.
- Commands: `git switch main && make status T=T-M3-06 S=in_progress`

## 2026-09-21 / T-M3-04
- Done: `dq.py` / `splits.py` / `manifest.py` / `registry.py`; ORM Dataset models;
  CLI validate|publish|freeze; leakage + frozen + hash tests.
- Next: PR merge; then T-M3-05 eval runner.
- Commands: `git switch feat/T-M3-04-dq-registry && make ci`

## 2026-09-21 / T-M3-03
- Done: `callscope/datasets` synth+augment C0-C5, Spec v1 (~120), CLI build; SNR/spectrum/determinism tests.
  **Merged** (#82).
- Next: T-M3-04 DQ/manifests.
- Commands: `git switch main && make status T=T-M3-04 S=in_progress`

## 2026-09-21 / T-M3-02
- Done: `callscope/eval/normalize.py` + scorers (asr/entities/nlu/tools/task), types aligned
  to `cs.eval_item_results`, golden tests (≥40), 100% branch coverage on normalize+entities.
- Next: PR merge; then T-M3-03 dataset builder.
- Commands to resume: `git switch feat/T-M3-02-scorers && make ci`

## 2026-09-21 / T-M3-01
- Done: `callscope/eval/scenarios.py` Pydantic schema + seeded template expansion; 16 YAMLs
  in `eval/scenarios/` (12 normal incl. barge-in/silence + 4 adversarial); CI tests for
  validation, determinism, and `must_not_claim` ↔ `docs/kb_gaps.md`. **Merged** (#80).
- Next: T-M3-02 normaliser/scorers.
- Commands to resume: `git switch main && make status T=T-M3-02 S=in_progress`

## 2026-09-21 / M2 close
- Done: All M2 tasks merged (#72–#78 except #74 retargeted as #78). Backlog 6/6 done.
  Milestone review: `docs/sprints/M2-review.md`.
- Next: Start **M3** (T-M3-01 scenario schema) after optional `v0.2.0` tag approval.
- Open questions: Approve version bump + tag push?
- Commands to resume: `git switch main && make ci`; then `make status T=T-M3-01 S=in_progress`

## 2026-09-20 / T-M2-04
- Done: receptionist skill + prompt_hash, register_skill when available, 10 manual_runs stubs,
  docs/prompts/CHANGELOG (D-20260920-35).
- Next: Merge stacked PRs #73→#74→#77.
- Commands to resume: `git switch feat/T-M2-04-skill && make ci`

## 2026-09-20 / T-M2-06
- Done: CallRecorder (consent-gated WAV), API recording register, retention catalog +
  `make purge` / delete-call, infra timer example (D-20260920-34). **Merged** (#76).
- Next: Merge #73→#74→#77 (plugin stack).
- Commands to resume: `git switch main && make ci`

## 2026-09-20 / T-M2-05
- Done: `InterruptionGate`, `DegradeController`, CallSession filler/abort/barge-in stop latency,
  §4.11 matrix tests (p95 ≤250 ms decision→cancel). **Merged** (#75).
- Next: T-M2-06 recording/purge; T-M2-04 skill (after #73/#74).
- Commands to resume: `git switch main && make ci`

## 2026-09-20 / T-M2-02
- Done: `plugins/hermes_callscope` — 7 tools, schemas, BizClient, register(ctx), tests with
  fake Business API; toolset `callscope-receptionist`.
- Next: PR merge → T-M2-03 policy + T-M2-04 skill.
- Commands to resume: `git switch feat/T-M2-02-hermes-plugin && make ci`

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
