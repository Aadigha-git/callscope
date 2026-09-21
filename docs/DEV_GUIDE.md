# CallScope developer guide (Phase 4)

Covers engineering environment and feature implementation workflow.
Design of record: `docs/design/CallScope_Phase3_Design.md` (Markdown supersedes any sibling `.docx`).

## 1. How the pieces fit

| Required artifact | Where it lives | Updated by | Enforced by |
|---|---|---|---|
| User stories / tasks | `backlog/tasks.yaml` -> GitHub issues | you/Cursor (`make status`) | `backlog validate` in CI + pre-commit |
| Sprint backlog | `sprint:` field + `docs/BACKLOG.md` (generated) + `docs/sprints/Sx-plan.md` | `make sprint` | CI checks BACKLOG.md is current |
| Code repository | GitHub `main` (protected) | PRs only | branch protection |
| Pull requests | one per task, template checklist | you | required checks + template |
| CI pipeline | `.github/workflows/{ci,release}.yml` | you | required status checks |
| Technical decision log | `docs/DECISIONS.md` (+ ADRs in design doc) | Cursor per rule 20 | PR template + review prompt |
| Updated API / schema docs | `docs/api/openapi.yaml`, `db/schema.sql` | with the code | artifact gate + contract tests |
| Issue tracker | GitHub Issues + Project board + milestones M0-M6 | `make issues` | setup script |
| Sprint reports | `docs/sprints/Sx-report.md` | `make report` + prompt | sprint-close prompt |
| Milestone review | `docs/sprints/Mx-review.md` | milestone-close prompt | checklist template |
| Build artifact | wheel/sdist via `make build`, release on tag | `release.yml` | tag push |
| Session continuity | `docs/SESSION_NOTES.md` | session-end prompt | rule 20 |

## 2. Engineering environment (do these in order)

### 2.1 Prerequisites
Apple Silicon Mac recommended. Python 3.11+, `uv`, Git, GitHub CLI (`gh`), Docker Desktop (+ compose)
for Postgres/Prometheus/Grafana only, Node 20+ (web client from M1), `pre-commit`, optional
`gitleaks`, Homebrew (`brew install livekit` when you reach S-6). Cursor with the repo as workspace.
macOS ships GNU Make 3.81; the repo Makefile uses tab-prefixed recipes so `/usr/bin/make` works.

### 2.2 Create the repository
```bash
unzip callscope-bootstrap.zip && cd callscope
gh auth login && gh auth refresh -s project      # scopes: repo, workflow, project
make setup                                        # deps, hooks, .env
make ci                                           # must be green before anything else
# replace @YOUR_GITHUB_USERNAME in .github/CODEOWNERS, then:
scripts/setup_github.sh callscope private         # repo, settings, labels, milestones, issues, protection
```
The script: creates the repo and pushes `main`; squash-merge only + auto-delete branches; secret
scanning + push protection; labels; milestones M0-M6; one issue per task; branch protection.
**It does not create staging/demo Environments** (local-Mac scope). Create the Project board
(`gh project create`), add a Status field, add all issues. Keep the repo private until the showcase
is ready.

### 2.3 Branching strategy (trunk-based, solo-friendly)
- `main` is always releasable and protected: PR required, required checks, linear history, no force-push.
- Short-lived branches, one per task: `feat|fix|spike|chore|docs|test|exp/<T-ID>-<slug>`.
- Conventional Commits with the task ID in the footer (`Refs: T-M2-05`); squash-merge, PR title = commit.
- Releases: tag per milestone (`v0.1.0` = M1 ... `v1.0.0` = M6); tags trigger `release.yml`.
- Hotfix: `fix/<slug>` off `main`, same gates. Experiments that may be discarded use `exp/` and are
  deleted after their DECISIONS.md entry.

### 2.4 Environments
| Environment | What | Purpose | How |
|---|---|---|---|
| dev | This Mac: native processes + `docker-compose.local.yml` (Postgres/Prom/Grafana); mocks or cassettes | daily development | `make dev-up`, later `make demo` |
| test | GitHub Actions + Postgres service + **LLM cassettes only** | automated gates on every PR | `ci.yml` |
| demo | This Mac with real local ASR/TTS + Token Factory (budgeted) or cassettes | interviews / screen-share | `make demo` |

No staging/demo cloud nodes. No `deploy.yml`.

### 2.5 CI/CD
- `ci.yml` (PR + main): `lint` (ruff), `typecheck` (mypy strict), `test` (pytest + coverage gate +
  Postgres service), `security` (gitleaks, pip-audit), `artifacts-gate`, `build`.
- `release.yml`: on `v*` tag: tests, build, release notes from CHANGELOG, GitHub Release with artifacts.
- Live Token Factory calls never run in CI. Mac-native ML tests are local (`make test` markers as added).

### 2.6 Coding standards
Enforced by ruff, ruff-format, mypy strict, pytest markers (`unit/contract/integration`), coverage
gate, pre-commit, and `.cursor/rules/`. Key rules: typed Pydantic boundaries, async-safe code,
monotonic clocks for latency, no PII in logs, providers behind interfaces, budget guard before live LLM.

### 2.7 Secrets management
- Never in git: `.env*` ignored (except `.env.example`), gitleaks in pre-commit and CI, GitHub push protection.
- Local: `.env` from `.env.example`. Keys: `TOKEN_FACTORY_API_KEY`, optional LangSmith/Toloka, LiveKit, Hermes.
- CI: GitHub Actions secrets only if ever needed (prefer cassettes).
- Rotate demo keys between interview sessions if you shared a machine.

### 2.8 Issue tracking
GitHub Issues (one per task), milestones M0-M6, labels `type:*`/`prio:*`, Project board.
Statuses: `backlog` → `ready` → `in_progress` → `in_review` → `done` (or `blocked` / `dropped`).
`make status T=T-M1-03 S=in_progress`. Sprints: `make sprint N=S2 T=T-M1-02,T-M1-03`.

### 2.9 Logging and basic monitoring
JSON logs with `call_id`/`turn_id` and PII scrubbing; Prometheus metrics. Compose runs Prometheus +
Grafana; Live-ops wiring arrives in T-M1-11. `make budget` shows Token Factory spend vs cap (T-M1-12).
`make asr` starts the native ASR server on `:8200` (default `CALLSCOPE_ASR_BACKEND=fake`; set
`mlx_whisper` on Apple Silicon — D-20260920-23). LLM calls default to cassette **replay**
(`eval/cassettes/`); live capture needs `--live` / `CALLSCOPE_LLM_MODE=live` plus the budget
guard (T-M1-13 / D-20260920-24).

### 2.10 Bootstrap done-when checklist
- [x] `make setup && make ci` green on a clean clone; pre-commit installed
- [ ] GitHub repo, branch protection, squash-only, secret scanning + push protection active
- [ ] CI green on a trivial PR
- [x] Labels, milestones, issues, Project board exist; `tasks.yaml` has issue numbers
- [x] `docs/design/` contains the design doc; Cursor rules load
- [x] No staging/demo Environments required (local-Mac scope)
- [ ] `T-M0-01` closed only when the checklist above matches the updated acceptance criteria

## 3. Implementing features

### 3.1 Task template
See `backlog/tasks.yaml` required fields. `make ci` validates IDs, dependencies (no deps on `dropped`),
and requirement IDs.

### 3.2 The per-task loop
1. New chat → paste the task prompt from `prompts/Mx_*.md` (or P01 with the task ID).
2. Cursor: reads task + design section → branch → `make status ... in_progress` → plan.
3. Implement with tests; log decisions; keep `make ci` green. Verify third-party APIs against installed source.
4. Update CHANGELOG, API/schema docs, status `in_review`, regenerate BACKLOG.md, SESSION_NOTES.
5. PR from the template; merge when green; status `done`.

### 3.3 Sprint and milestone ceremonies
See `prompts/ceremonies.md`.

## 4. Working with Cursor
- Agent mode for building, Ask mode for reviews. One task per chat.
- Rules in `.cursor/rules` are always-on. Attach design sections for context.
- Verify Hermes, LiveKit, Token Factory, MLX/model libs against installed source/docs — never invent APIs.
- Never lower gates to get green; fix the cause.
- Do not spend Token Factory credit without `--estimate` / budget check once T-M1-12 exists.

## 5. Schedule and sprint plan (local-Mac rescope)

**Old total (GPU VM scope):** ~459 h (D-20260919-01).
**New total (excl. dropped):** **462 h** — M0 50, M1 116, M2 56, M3 84, M4 60, M5 58, M6 38.
At **30 h/week** ≈ **15.4 weeks** wall clock (optional E2 T-M5-05 is 16 h of that).

Proposed sprints (greedy by dependencies; S1 = remaining M0 spikes):

| Sprint | Tasks (~30 h) |
|---|---|
| S1 | T-M0-07, T-M0-04, T-M0-06, T-M0-03 (done already: T-M0-01/02/05) |
| S2 | T-M1-01, T-M1-12, T-M1-02, T-M1-03 |
| S3 | T-M1-13, T-M1-04, T-M1-05 |
| S4 | T-M1-06, T-M1-07, T-M1-08 |
| S5 | T-M1-09, T-M1-10 |
| S6 | T-M1-11, T-M2-01, T-M2-06 |
| S7 | T-M2-02, T-M2-03, T-M2-04 |
| S8 | T-M2-05, T-M3-01, T-M6-02 |
| S9 | T-M3-02, T-M3-03 |
| S10 | T-M3-04, T-M3-05 |
| S11 | T-M3-06, T-M3-07 |
| S12 | T-M3-08, T-M4-01, T-M4-05 |
| S13 | T-M4-02, T-M4-03 |
| S14 | T-M4-04, T-M4-06, T-M5-01 |
| S15 | T-M5-02, T-M5-03 |
| S16 | T-M5-04, T-M5-05 (optional) |
| S17 | T-M6-01, T-M6-03 |
| S18 | T-M6-05 |

Thin-slice cut (~462 → ~390 h): defer T-M4-04, T-M4-05, T-M4-06, T-M5-05, T-M3-08, T-M6-01; simplify
T-M1-11. Never cut: eval harness core, review console, E1 or E3, governance artifacts, budget+cassettes.

## 6. Troubleshooting
- `artifacts-gate` fails: run `make backlog-render`, update CHANGELOG/tasks.yaml, or add `[skip-artifacts]`
  to the PR title for docs/chore-only PRs.
- Branch protection call fails: required checks do not exist until CI has run once.
- `make ci` mypy errors on new libs: add stubs or a narrow `# type: ignore[code]` with a comment.
- Token Factory 429: honor `Retry-After`; reduce concurrency; check `make budget`.
- MLX / memory pressure: stop Compose browsers, use smaller ASR/TTS, defer local LLM fallback.
- Cursor ignores rules: Settings > Rules; new chat; `@.cursor/rules/20-workflow-artifacts.mdc`.
