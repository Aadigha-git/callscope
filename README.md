# CallScope

Live, self-hosted voice agent (Hermes Agent as the reasoning backend) with a telephony-realistic
evaluation harness, call-review workflow, model-improvement loop and governance artifacts.

- Design of record: `docs/design/CallScope_Phase3_Design.md` (Word version: `docs/design/*.docx`)
- Developer guide (environments, branching, CI/CD, standards): `docs/DEV_GUIDE.md`
- Backlog: `docs/BACKLOG.md` (generated from `backlog/tasks.yaml`)
- Decisions: `docs/DECISIONS.md` | Changelog: `docs/CHANGELOG.md`
- Cursor prompts: `prompts/`

## Quickstart
```bash
make setup      # uv sync, pre-commit hooks, .env from .env.example
make dev-up     # Postgres, MinIO, Prometheus, Grafana (localhost only)
make ci         # lint + typecheck + tests + backlog validation
```
Status: pre-alpha (milestone M0). See `docs/BACKLOG.md`.
