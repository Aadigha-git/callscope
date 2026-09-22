# Milestone review - M4 Review + caller-sim  (2026-09-22)

## Checklist (all must be Yes, else list the exception and a follow-up task)
| Item | Yes/No | Evidence (link/run ID) |
|---|---|---|
| Feature implementation complete (all M# tasks done or explicitly deferred) | Yes | T-M4-01..06 `done` in `backlog/tasks.yaml` |
| Code reviewed and merged (PRs linked; self-review checklist completed) | Yes | #90–#95 |
| Unit tests pass; CI green on main | Yes | Local `make ci` green through T-M4-06 (~406 passed); GitHub Actions green on #91–#95 |
| Documentation updated (README, design deviations, API/schema docs, runbooks) | Partial | CHANGELOG/DECISIONS/SESSION_NOTES + OpenAPI notes. Public README still deferred to M6 |
| Build artifact created (wheel/sdist/container tag) and attached to release | Yes | `pyproject.toml` → `0.4.0`; annotated tag `v0.4.0` (approved 2026-09-22) |
| Sprint/milestone review completed (this document) | Yes | This file |

## Exit criterion from the design doc (section 12.3)
> **M4 Review + caller-sim (protected)** — Review console, auto-flagging, taxonomy, caller simulator, dashboards. Exit: *30+ calls reviewed and labelled; root-cause distribution produced.*

Evidence:
- Auto-flag + attribution: `callscope/review/{flags,attribution,timeline}` (#90).
- Review API: `/v1/calls`, labels, export, eval runs/compare, models (#91).
- Streamlit console + `seed-demo` (40 planted / ≥30 labelled) + distribution page (#92).
- Caller-sim: oracle + MockTransport CI path for all 16 scenarios; LiveKit rtc transport verified (#93, D-20260922-39).
- Grafana quality/cost dashboards + alerts + `/metrics/eval` exporter (#94).
- Optional LangSmith tracing; skip LS datasets for judge (D-20260922-40) (#95).

## Demo / results
- `make api` + `make review` / `make review-seed`
- `make eval ARGS='run --mode caller_sim --stack mock'`
- Grafana after `make demo`: Quality & Drift, Cost & Sessions boards
- LangSmith remains off unless `CALLSCOPE_LANGSMITH_ENABLED=true` + `LANGSMITH_API_KEY`

## Deviations and decisions
- D-20260922-39 Caller-sim mock in CI; LiveKit path for local demo
- D-20260922-40 Skip LangSmith datasets/experiments for judge eval

## Risks, debt, and follow-ups
- Human labelling agreement vs auto-attribution still best measured after real traffic (seed labels are planted).
- Real LiveKit unattended caller-sim needs gpu-marker / demo stack (mock covers CI).
- Wire FileEvalStore / ReviewStore → Postgres in M5 governance.

## Version bump
- **v0.4.0** tagged 2026-09-22 (M4 complete).
