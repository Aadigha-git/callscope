# CallScope developer guide (Phase 4)

Covers step 4.1 (engineering environment) and 4.2 (feature implementation workflow).
Design of record: `docs/design/CallScope_Phase3_Design.md`.

## 1. How the pieces fit

| Required artifact | Where it lives | Updated by | Enforced by |
|---|---|---|---|
| User stories / tasks | `backlog/tasks.yaml` -> GitHub issues | you/Cursor (`make status`) | `backlog validate` in CI + pre-commit |
| Sprint backlog | `sprint:` field + `docs/BACKLOG.md` (generated) + `docs/sprints/Sx-plan.md` | `make sprint` | CI checks BACKLOG.md is current |
| Code repository | GitHub `main` (protected) | PRs only | branch protection |
| Pull requests | one per task, template checklist | you | required checks + template |
| CI/CD pipeline | `.github/workflows/{ci,release,deploy}.yml` | you | required status checks |
| Technical decision log | `docs/DECISIONS.md` (+ ADRs in design doc) | Cursor per rule 20 | PR template + review prompt |
| Updated API / schema docs | `docs/api/openapi.yaml`, `db/schema.sql` | with the code | artifact gate + contract tests |
| Issue tracker | GitHub Issues + Project board + milestones M0-M6 | `make issues` | setup script |
| Sprint reports | `docs/sprints/Sx-report.md` | `make report` + prompt | sprint-close prompt |
| Milestone review | `docs/sprints/Mx-review.md` | milestone-close prompt | checklist template |
| Build artifact | wheel/sdist via `make build`, release on tag | `release.yml` | tag push |
| Session continuity | `docs/SESSION_NOTES.md` | session-end prompt | rule 20 |

## 2. Step 4.1 - engineering environment (do these in order)

### 2.1 Prerequisites
Python 3.11+, `uv`, Git, GitHub CLI (`gh`), Docker (+ compose plugin), Node 20+ (web client from M1),
`pre-commit`, optional `gitleaks`, `pandoc`. Cursor with the repo folder as workspace.
macOS ships GNU Make 3.81; the repo Makefile uses tab-prefixed recipes so `/usr/bin/make` works
(no need for Homebrew `gmake`).

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
scanning + push protection; labels; milestones M0-M6; one issue per task (numbers written back to
`tasks.yaml`); staging/demo Environments; branch protection. Branch protection requires the CI check
names to exist, so if that last step fails, open a trivial PR to trigger CI once, then re-run it.
Create the Project board (`gh project create`), add a Status field (Backlog, Ready, In progress,
In review, Done) and add all issues. Keep the repo private until the demo is ready; the write-up
will make it public later.

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
| dev | laptop, docker-compose.local.yml + mock providers, no GPU | daily development | `make dev-up`, `make test` |
| test | GitHub Actions runners + Postgres service | automated gates on every PR | `ci.yml` |
| staging | private Nebius GPU node ("gpu-dev") with real models | benchmarks, spikes, training, caller-sim, security suite | `deploy.yml` target=staging |
| demo (prod) | CPU node + GPU node, public | live demo windows | `deploy.yml` target=demo (manual approval) |
Staging and demo use separate env files on the node (`/opt/callscope/.env`, mode 600) and separate keys.

### 2.5 CI/CD
- `ci.yml` (PR + main): `lint` (ruff), `typecheck` (mypy strict), `test` (pytest + coverage gate +
  Postgres service, runs contract tests incl. openapi/schema validity and real-Postgres schema apply),
  `security` (gitleaks, pip-audit), `artifacts-gate` (PRs: backlog valid + BACKLOG.md current +
  CHANGELOG/tasks/API/schema updated with code), `build` (wheel/sdist artifact).
- `release.yml`: on `v*` tag: tests, build, release notes from CHANGELOG, GitHub Release with artifacts.
- `deploy.yml`: manual, GitHub Environments with secrets `DEPLOY_HOST/USER/SSH_KEY`; runs
  `scripts/deploy.sh` (rsync compose/config, `docker compose up -d`). Secrets stay on the node.
- GPU-only tests (`-m gpu`) never run in CI; they run on staging via `make test-gpu` (add in M1).
- Later additions are tracked as tasks (docker image builds T-M1-11, `promtool` T-M4-05).

### 2.6 Coding standards
Enforced by ruff (E,F,I,B,UP,SIM,ASYNC,PT,RUF,S,T20), ruff-format, mypy strict, pytest markers
(`unit/contract/integration/gpu`), coverage gate (70% now; raise as code lands), pre-commit, and the
Cursor rules in `.cursor/rules/`. Key rules: typed Pydantic boundaries, async-safe code, monotonic
clocks for latency, no PII in logs, providers behind interfaces, small pure functions for scoring/policy.

### 2.7 Secrets management
- Never in git: `.env*` ignored (except `.env.example`), gitleaks in pre-commit and CI, GitHub push protection.
- Local: `.env` from `.env.example` (dev-only defaults). CI: GitHub Actions secrets/Environments.
- Servers: `/opt/callscope/.env` (600) created by hand or via SOPS+age; compose reads `env_file`, never inline values.
- Rotate demo keys (LiveKit, Hermes API key, DB) at each demo teardown; different values per environment.
- Cloud credentials for GPU lifecycle stay on your machine or in GitHub Environment secrets, never in the repo.

### 2.8 Issue tracking
GitHub Issues (one per task, created from `tasks.yaml`), milestones M0-M6, labels `type:*`/`prio:*`,
Project board with Status. `tasks.yaml` is the source of truth for fields; the issue body is generated.
Flow: `backlog` -> `ready` -> `in_progress` -> `in_review` -> `done` (or `blocked`). Change status with
`make status T=T-M1-03 S=in_progress`, never by hand-editing the generated `docs/BACKLOG.md`.
Sprints are one week: `make sprint N=S2 T=T-M1-02,T-M1-03`, report with `make report SPRINT=S2`.

### 2.9 Logging and basic monitoring (already in the kit)
`callscope/observability/logging.py`: JSON logs with `call_id`/`turn_id` context and PII scrubbing;
`metrics.py`: the Prometheus catalogue from design 4.10 (latency histograms with buckets around the
NFR-01 targets). `docker-compose.local.yml` runs Prometheus + Grafana locally; the Live-ops dashboard
and real scrape targets arrive in T-M1-11.

### 2.10 4.1 done-when checklist
- [ ] `make setup && make ci` green on a clean clone; pre-commit installed
- [ ] GitHub repo, branch protection, squash-only, secret scanning + push protection active
- [ ] CI green on a trivial PR (this also unlocks the required-check names)
- [ ] Labels, milestones, 46 issues, Project board exist; `tasks.yaml` has issue numbers
- [ ] `docs/design/` contains the design doc (.md and .docx); Cursor rules load
- [ ] Environments `staging`/`demo` created; secrets placeholders documented
- [ ] `T-M0-01` set to done through the normal PR flow

## 3. Step 4.2 - implementing features

### 3.1 Task template (every task in `backlog/tasks.yaml`)
`id`, `title`, `milestone`, `type`, `requirements` (FR/NFR IDs), `description`, `technical_approach`,
`dependencies` (task IDs), `acceptance_criteria` (checklist), `owner`, `estimate_h`, `priority`,
`status`, `sprint`, `issue`, `prompt` (pointer into `prompts/`). Add new tasks with the grooming prompt;
`make ci` validates required fields, unique IDs, known dependencies and requirement IDs.

### 3.2 The per-task loop (Cursor follows this via rule 20)
1. New chat -> paste the task prompt from `prompts/Mx_*.md` (or P01 with the task ID).
2. Cursor: reads task + design section -> branch -> `make status ... in_progress` -> plan.
3. Implement with tests; log decisions; keep `make ci` green.
4. Update CHANGELOG, API/schema docs, status `in_review`, regenerate BACKLOG.md, SESSION_NOTES.
5. PR from the template; run the PR self-review prompt; merge when green; status `done`.

### 3.3 Sprint and milestone ceremonies
Sprint planning, session start/end, sprint close + report, retro/re-estimate, milestone close (checks:
implementation complete, code reviewed and merged, unit tests pass, documentation updated, build
artifact created, milestone review completed) are all in `prompts/ceremonies.md`.

## 4. Working with Cursor
- Agent mode for building, Ask mode for reviews and design questions. One task per chat.
- Rules in `.cursor/rules` are always-on (context, workflow, security) or file-scoped (Python, tests).
- Attach `@docs/design/CallScope_Phase3_Design.md` sections for context; keep chats short.
- Make Cursor verify third-party APIs (Hermes, LiveKit, vLLM, model libs) in installed source. Do not accept
  "plausible" method names. If it cannot verify, it must log a spike/decision instead.
- Never let it lower gates (coverage, lint rules, thresholds) to get green; fix the cause.

## 5. Schedule reality check and sprint plan
Backlog estimates: M0 43 h, M1 106, M2 58, M3 92, M4 60, M5 50, M6 50 = **459 h** (P0: 375 h). At 30 h/week
that is about 15 weeks (12.5 for P0 only). The "5-6 weeks" in the first design draft was optimistic (D-20260919-01).
Estimates are hands-on hours including review, debugging and GPU waiting; measure actuals in S1-S2 and re-scale.

Proposed sprints (30 h/week, greedy by dependencies; S1 is already set in `tasks.yaml`):
S1 T-M0-01, 02, 05, 07, T-M1-01 | S2 T-M0-04, 06, T-M1-02, 03 | S3 T-M0-03, T-M1-04, 05 | S4 T-M1-06, 07, 08 |
S5 T-M1-09, 10 | S6 T-M1-11, T-M2-01, 06 | S7 T-M2-02, 03, 04 | S8 T-M2-05, T-M3-01, T-M6-02 |
S9 T-M3-02, 03 | S10 T-M3-04, 05 | S11 T-M3-06, 07 | S12 T-M3-08, T-M4-01, 05 | S13 T-M4-02, 03 |
S14 T-M4-04, T-M5-01 | S15 T-M5-02, 03 | S16 T-M5-04, T-M6-01 | S17 T-M6-03, 04 | S18 T-M6-05.
(Move T-M6-02 later if you prefer; it was pulled early only because its dependencies were done.)

Thin-slice cut if you need to shorten (about 375 h -> ~290 h): defer T-M4-04 caller-sim, T-M4-05,
T-M3-08, T-M6-01, T-M6-04, T-M2-06 (keep consent gating, do retention manually), and simplify
T-M1-11 to Compose only. Never cut: eval harness (M3 core), review console, one improvement
experiment, governance artifacts. Record any cut as a DECISIONS.md entry.

## 6. Troubleshooting
- `artifacts-gate` fails: run `make backlog-render`, update CHANGELOG/tasks.yaml, or add `[skip-artifacts]`
  to the PR title for docs/chore-only PRs.
- Branch protection call fails: required checks do not exist until CI has run once.
- `make ci` mypy errors on new libs: add stubs (`types-*`) or a narrow `# type: ignore[code]` with a comment.
- Cursor ignores rules: check Settings > Rules; start a new chat; reference `@.cursor/rules/20-workflow-artifacts.mdc`.
