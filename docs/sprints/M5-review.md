# Milestone review - M5 Improvement + governance  (2026-09-22)

## Checklist (all must be Yes, else list the exception and a follow-up task)
| Item | Yes/No | Evidence (link/run ID) |
|---|---|---|
| Feature implementation complete (all M# tasks done or explicitly deferred) | Yes | T-M5-01..04 `done`; T-M5-05 deferred (D-20260922-44) |
| Code reviewed and merged (PRs linked; self-review checklist completed) | Yes | #98–#101; T-M5-05 deferral PR |
| Unit tests pass; CI green on main | Yes | Local `make ci`: 424 passed; GitHub Actions green on #98–#101 |
| Documentation updated (README, design deviations, API/schema docs, runbooks) | Partial | CHANGELOG/DECISIONS/SESSION_NOTES + OpenAPI lifecycle 409; public README still M6 |
| Build artifact created (wheel/sdist/container tag) and attached to release | Pending approval | `pyproject.toml` → `0.5.0`; tag `v0.5.0` prepared — **do not push until approved** |
| Sprint/milestone review completed (this document) | Yes | This file |

## Exit criterion from the design doc (section 12.3)
> **M5 Improvement + governance (protected)** — E1 (then E2 or E3), MLflow tracking, model inventory, cards, validation report, gate enforcement. Exit: *One measured improvement on the frozen test; promoted model has card + report.*

Evidence:
- E1 hotwords adopted (D-20260922-42); MLflow `23f6d3731fd54dcbb1d576a76eb2835f` (#99).
- E3 endpoint/VAD adopted (D-20260922-43); MLflow `cd36bba1573c46a182d703bd3024d6ca` (#100).
- Optional E2 LoRA deferred (D-20260922-44) — no telephony train set / no >2 GB download.
- Registry + MLflow helpers (D-20260922-41) (#98).
- Cards / validation reports / risk template / lifecycle gates on
  `/v1/models/{id}/transition` (#101); sample card
  `docs/model_cards/asr-mlx-whisper-tiny-9cc29594.md`.

## Demo / results
- `make governance ARGS=backfill`
- `make experiment ARGS='e1 --out artifacts/experiments/e1'`
- `make experiment ARGS='e3 --out artifacts/experiments/e3'`
- Transition API: unmet gates → HTTP 409 + `unmet` list
- Optional Compose MLflow: `docker compose --profile mlflow up`

## Deviations and decisions
- D-20260922-41 File-backed registry + SQLite MLflow default
- D-20260922-42 E1 offline-proxy adopt (real ASR re-confirm later)
- D-20260922-43 E3 oracle-proxy grid adopt
- D-20260922-44 E2 LoRA deferred

## Risks, debt, and follow-ups
- Re-validate E1/E3 on live mlx-whisper + recorded/volunteer audio (D-20260921-38).
- Postgres remains long-term SoT for `cs.model_versions` / stacks (file registry is local/CI).
- Public README + showcase packaging remain M6.

## Go / no-go for next milestone
- **Go for M6** (hardening + demo packaging). Protected M5 exit met via E1+E3 + governance.
- Remaining estimate: T-M6-01.. per backlog; no M5 carry-over except E2 reopen if train data lands.

## Version bump
```bash
# After approval:
git tag -a v0.5.0 -m "M5 Improvement + governance"
git push origin v0.5.0
```
