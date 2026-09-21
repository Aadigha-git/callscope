# Milestone review - M2 Receptionist behaviour  (2026-09-21)

## Checklist (all must be Yes, else list the exception and a follow-up task)
| Item | Yes/No | Evidence (link/run ID) |
|---|---|---|
| Feature implementation complete (all M# tasks done or explicitly deferred) | Yes | T-M2-01..06 `done` in `backlog/tasks.yaml`; `docs/BACKLOG.md` M2 = 6/6 |
| Code reviewed and merged (PRs linked; self-review checklist completed) | Yes | #72, #73, #75, #76, #78, #77 |
| Unit tests pass; CI green on main | Yes | Local `make ci`: 227 passed, 5 skipped; coverage 85.44% (2026-09-21) |
| Documentation updated (README, design deviations, API/schema docs, runbooks) | Partial | CHANGELOG/DECISIONS/SESSION_NOTES + biz OpenAPI updated. Public README still deferred to M6 (prior decision). |
| Build artifact created (wheel/sdist/container tag) and attached to release | No | Version bump + tag **held for approval** (see below) |
| Sprint/milestone review completed (this document) | Yes | This file |

## Exit criterion from the design doc (section 12.3)
> **M2 Receptionist behaviour** — Plugin tools/policy/skill, Business API + KB, guardrails, filler/degradation paths. Exit: *Scenario library runs manually; policy tests pass.*

Evidence:
- Policy: `tests/plugin/test_policy.py` (table-driven Allow/Deny + toolset selftest).
- Skill + 10 dry-plan scenarios: `eval/manual_runs/` (incl. unknown-fact decline + injection refuse); `tests/plugin/test_skill.py`.
- Business API + KB gaps: `apps/biz`, `docs/kb_gaps.md`, `tests/biz/`.
- Filler/degradation: `apps/worker/{interrupt,degrade}.py`, `tests/worker/test_barge_degrade.py`.
- Full automated scenario library (M3) not required for this exit criterion.

## Demo / results
- `make biz` + plugin unit tests without live Hermes.
- `make purge` dry-run / APPLY for local retention.
- Worker barge-in stop latency scripted p95 ≤250 ms (fake clock).
- Live Mac-stack re-run of the 10 manual scenarios still optional polish before M3 automation.

## Deviations and decisions
- D-20260920-31 Biz in-memory store
- D-20260920-32 hermes-callscope toolset
- D-20260920-33 barge-in stop-latency semantics
- D-20260920-34 local recording + JSONL retention
- D-20260920-35 skill registration + prompt hash

## Risks, debt, and follow-ups
- Live Hermes `register_skill` kwargs not verified on installed 0.19 — skill text still loaded for worker/`prompt_hash`.
- MinIO upload path optional; local `file://` URIs used in demo.
- M3 will automate scenario library beyond dry plans.

## Go / no-go for next milestone
**Go for M3 (Eval core).** Dependencies T-M2-01 and related M2 surfaces are on main. Version tag `v0.2.0` ready to cut after approval.

## Proposed release steps (awaiting approval)
1. Bump `pyproject.toml` version `0.0.1` → `0.2.0`
2. Move CHANGELOG `[Unreleased]` M2 entries under `[0.2.0]`
3. `make build`
4. `git tag -a v0.2.0 -m "M2 Receptionist behaviour"` (do not push until approved)
