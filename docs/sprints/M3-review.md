# Milestone review - M3 Eval core  (2026-09-21)

## Checklist (all must be Yes, else list the exception and a follow-up task)
| Item | Yes/No | Evidence (link/run ID) |
|---|---|---|
| Feature implementation complete (all M# tasks done or explicitly deferred) | Yes* | T-M3-01..08 `done` in `backlog/tasks.yaml`. *Recorded human WAVs deferred (D-20260921-38); protocol + tooling shipped. |
| Code reviewed and merged (PRs linked; self-review checklist completed) | Yes | #80–#87 (features), #88 (backlog) |
| Unit tests pass; CI green on main | Yes | Local `make ci`: 357 passed, 5 skipped; coverage ~88% (2026-09-21). Filler race hardened in follow-up. |
| Documentation updated (README, design deviations, API/schema docs, runbooks) | Partial | CHANGELOG/DECISIONS/SESSION_NOTES + `docs/recording_protocol.md` + `docs/reports/baseline.md` + `eval/thresholds.yaml`. Public README still deferred to M6. |
| Build artifact created (wheel/sdist/container tag) and attached to release | No | Version bump + tag **held for approval** (see below) |
| Sprint/milestone review completed (this document) | Yes | This file |

## Exit criterion from the design doc (section 12.3)
> **M3 Eval core (protected)** — Scenario spec, dataset builder + augmentation + DQ, stage/text-replay runner, scorers, baseline report. Exit: *Baseline metrics with CIs across C0–C5; synthetic-vs-recorded gap reported.*

Evidence:
- Scenarios: 16 YAMLs + schema (`eval/scenarios/`, T-M3-01, #80).
- Scorers + normaliser: ASR/NLU/tools/task + claims/judge/safety (#81, #87).
- Synth C0–C5 builder + DQ/splits/registry (#82, #83).
- Stage/text-replay runner + cassettes/budget (#84); bootstrap CIs + gate (#85).
- Baseline draft: `docs/reports/baseline.md` citing run `39692d2c-4b41-4dd3-ba90-205df186a23d` (mock golden).
- **Gap:** full C0–C5 CI tables on *real* native ASR and synthetic-vs-recorded gap await volunteer recordings (D-20260921-38) and a Spec-v1 live/cassette eval. Tracked as operator follow-up, not a code blocker for M4.

## Demo / results
- `make eval ARGS='run --stack … --dataset golden-eval@v1 --mode stage_replay'`
- `make eval ARGS='gate --run <id>'` / `compare`
- `make dataset ARGS='ingest-recorded|export-transcripts|import-corrections|freeze-recorded-test'`
- Thresholds locked: `docs/thresholds.lock` ↔ `eval/thresholds.yaml`

## Deviations and decisions
- D-20260921-36 File-backed eval run store (CI without Postgres eval ORM)
- D-20260921-37 Thresholds lockfile + WER margin units (0.01 = +1 pp)
- D-20260921-38 Recorded baseline deferred to volunteer sessions

## Risks, debt, and follow-ups
- Complete 15–20/15–20 recorded set; refresh baseline with recorded `run_id` + gap CIs.
- Re-run Spec v1 (~120) with native ASR for meaningful WER CIs (mock golden WER=0 is not a production claim).
- Wire `FileEvalStore` → Postgres when T-M4-02 / T-M5-01 land.
- Judge calibration labels are synthetic fixture; replace/augment with ≥50 human labels before relying on live judge.

## Go / no-go for next milestone
**Go for M4 (Review + caller-sim).** Eval harness, gates, and scorers are on main. Recorded-set completion can proceed in parallel with review console work.

## Proposed release steps (awaiting approval)
1. Bump `pyproject.toml` version `0.0.1` → `0.3.0` (M3; prior `v0.2.0` for M2 was also held)
2. Move CHANGELOG `[Unreleased]` M3 entries under `[0.3.0]`
3. `make build`
4. `git tag -a v0.3.0 -m "M3 Eval core"` (do not push until approved)
