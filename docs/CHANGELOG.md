# Changelog
Format: Keep a Changelog. Versions map to milestones (M1 = 0.1.0 ... M6 = 1.0.0).

## [Unreleased]
### Added
- M2 milestone review (`docs/sprints/M2-review.md`)
- Receptionist skill `callscope:receptionist` + prompt hash + 10 manual-run stubs (T-M2-04)
- Policy hook for hermes-callscope (`evaluate` Allow/Deny, budgets, confirmation) (T-M2-03)
- `hermes-callscope` plugin: seven receptionist tools calling Business API (T-M2-02)
- Local call recording (consent-gated WAV), `POST /v1/calls/{id}/recording`, and
  `make purge` / `delete-call` retention CLI (T-M2-06)
- Worker barge-in gate, filler (1.5 s), turn abort (8 s), and §4.11 degradation matrix
  (`apps/worker/interrupt.py`, `degrade.py`) (T-M2-05, D-20260920-33)
- Lakeside Home Services Business API (`apps/biz`, `make biz`) with deterministic seed,
  idempotent booking, KB search, and documented KB gaps (T-M2-01)
- `make demo` / `make demo-stop`: Compose data plane + honcho Procfile, Grafana Live-ops
  dashboard, Prometheus scrapes for API/worker/ASR/TTS (T-M1-11, D-20260920-30)
- Voice worker (`apps/worker`): TurnStateMachine, CallSession, §4.2→LiveKit config
  mapping, mock smoke (`make worker`) (T-M1-10, D-20260920-29)
- Hermes receptionist profile (`infra/hermes`) + `HermesBackend` SSE BrainBackend with CALL_CONTEXT,
  first-token timeout, cancel, cassette wrap (T-M1-09, D-20260920-28)
- Browser web client (`apps/web`, Vite + livekit-client) with consent gate and XSS-safe transcript (T-M1-08, D-20260920-27)
- CallScope API (`apps/api`, `make api`): status, sessions (consent + LiveKit token), events batch (T-M1-07, D-20260920-26)
- Native TTS server (`servers/tts`, `make tts`, `TTSClient`) with fake + optional Piper/Kokoro (T-M1-06, D-20260920-25)
- LLM record/replay cassettes (`CassetteStore`, `CassetteBrain`) under `eval/cassettes/` (T-M1-13, D-20260920-24)
- Native ASR server (`servers/asr`, `make asr`, `ASRClient`) with fake + optional mlx-whisper (T-M1-05, D-20260920-23)
- Sentence chunker + `tts_norm` for streaming TTS (T-M1-04)
- Provider protocols + MockSTT/MockTTS/MockBrain and contract suite (T-M1-03)
- Alembic baseline (`migrations/0001`), async SQLAlchemy models/repos, `make db-upgrade` (T-M1-02, D-20260920-22)
- LLM budget guard (`BudgetGuard`, `make budget`, `--estimate`/`--check`) + `eval_runs.estimated_usd` (T-M1-12, D-20260920-21)
- Event envelope, CallClock, async EventWriter (batch/spill/replay), and `instrument()` (T-M1-01)
- Spike S-2 (T-M0-03): Hermes vs Token Factory TTFT overhead; R-02 thin FAQ fast-path (D-20260920-20)
- Spike S-5 (T-M0-06): Apple Silicon ASR/TTS/VAD shortlist + `eval/probe/` assets (D-20260920-19)
- Spike S-3 (T-M0-04): Hermes→Token Factory tool-call reliability harness under `spikes/T-M0-04/`; choose Nemotron-3.5-Lightning (D-20260920-18)
- Spike S-6 (T-M0-07): Mac baseline, native livekit-server 1.13.7 verification, Token Factory regional RTT harness under `spikes/T-M0-07/` (D-20260920-17)
- Local-Mac rescope: ADR-014..017, budget/cassette tasks (T-M1-12/13), LangSmith task (T-M4-06),
  optional E2 task (T-M5-05); `dropped` backlog status; `make demo`/`budget` stubs; `.gitleaks.toml`
- Engineering environment: CI, backlog tooling, logging/metrics baseline, Cursor rules and prompt library (T-M0-01)
- Backlog of tasks with estimates; schedule re-baselined (D-20260919-01; hours updated D-20260920-10)
- Bootstrap acceptance tests for `.gitignore` secrets/data patterns, GitHub issue linkage, and CI job shape (T-M0-01)
- Spike S-1 (T-M0-02): Hermes 0.19.0 correlation probe under `spikes/T-M0-02/` with scrubbed evidence (D-20260920-04)
- Spike S-4 (T-M0-05): LiveKit Agents 1.8.2 stub worker + browser/headless smoke under `spikes/T-M0-05/` (D-20260920-05)
- Scrubber coverage for TOKEN_FACTORY / LangSmith / Toloka / api_key assignments

### Changed
- Design §3.6: measured TF TTFT + Hermes overhead; FAQ fast-path for NFR-01 headroom (D-20260920-20)
- Design §9.5 filled with S-5 measured ASR/TTS/VAD memory/RTF (D-20260920-19)
- Default `TOKEN_FACTORY_MODEL` → `nvidia/Nemotron-3_5-Lightning` (D-20260920-18)
- Scope: public Nebius GPU VM demo → local Apple Silicon demo + Token Factory LLM (D-20260920-10..16)
- Design doc v1.1: NFRs, infra §9, security §8.6, ADR statuses; Markdown supersedes `.docx`
- Backlog rewrite; T-M6-04 dropped; sprint plan regenerated in DEV_GUIDE §5
- Removed `deploy.yml` / `scripts/deploy.sh`; setup_github no longer creates staging/demo Environments
- Design §4.4 / ADR-006 notes: CALL_CONTEXT must be in user message content; API-server `user`/headers do not reach hooks (D-20260920-04)
- ADR-002 / U4 / S-4: confirmed own LiveKit Agents worker; hermes-livekit not adopted; §4.2 config mapping (D-20260920-05)

### Removed
- Public-demo path assumptions from docs and `.env.example` (captcha, staging deploy)

## [0.0.1]
- Repository bootstrap
