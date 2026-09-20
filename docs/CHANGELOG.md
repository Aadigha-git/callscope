# Changelog
Format: Keep a Changelog. Versions map to milestones (M1 = 0.1.0 ... M6 = 1.0.0).

## [Unreleased]
### Added
- Local-Mac rescope: ADR-014..017, budget/cassette tasks (T-M1-12/13), LangSmith task (T-M4-06),
  optional E2 task (T-M5-05); `dropped` backlog status; `make demo`/`budget` stubs; `.gitleaks.toml`
- Engineering environment: CI, backlog tooling, logging/metrics baseline, Cursor rules and prompt library (T-M0-01)
- Backlog of tasks with estimates; schedule re-baselined (D-20260919-01; hours updated D-20260920-10)
- Bootstrap acceptance tests for `.gitignore` secrets/data patterns, GitHub issue linkage, and CI job shape (T-M0-01)
- Spike S-1 (T-M0-02): Hermes 0.19.0 correlation probe under `spikes/T-M0-02/` with scrubbed evidence (D-20260920-04)
- Spike S-4 (T-M0-05): LiveKit Agents 1.8.2 stub worker + browser/headless smoke under `spikes/T-M0-05/` (D-20260920-05)
- Scrubber coverage for TOKEN_FACTORY / LangSmith / Toloka / api_key assignments

### Changed
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
