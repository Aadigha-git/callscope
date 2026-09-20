# CallScope

Live voice agent (Hermes Agent as the reasoning backend) with a telephony-realistic evaluation
harness, call-review workflow, model-improvement loop and governance artifacts.

**Runtime scope (2026-09):** local demo on an **Apple Silicon Mac**. ASR / VAD / TTS run natively;
the agent LLM is a hosted open-weight model on **Nebius Token Factory** (optional local LLM
fallback). Deliverables: `make demo`, a recorded demo video, and a static showcase site — not a
public GPU VM.

- Design of record: `docs/design/CallScope_Phase3_Design.md` (Markdown supersedes any `.docx`)
- Developer guide: `docs/DEV_GUIDE.md`
- Backlog: `docs/BACKLOG.md` (from `backlog/tasks.yaml`)
- Decisions: `docs/DECISIONS.md` | Changelog: `docs/CHANGELOG.md`
- Cursor prompts: `prompts/`

## Third-party data flow (summary)

| Destination | May leave the Mac | Stays local |
|---|---|---|
| Token Factory | Fictional prompts / tool calls / eval text | Audio, recordings, real personal voice data |
| LangSmith (opt-in) | Scrubbed fictional text only | Audio, real PII |
| Toloka (opt-in stretch) | TEXT labelling of fictional utterances | Audio, real personal data |
| Tavily | Not used | — |

Volunteers see a consent notice and a fictional-data banner. See design §8.6.

## Quickstart (Mac)
```bash
make setup      # uv sync, pre-commit hooks, .env from .env.example
# Edit .env: set TOKEN_FACTORY_API_KEY when you are ready for live LLM calls
make dev-up     # Postgres, MinIO (optional), Prometheus, Grafana (localhost only)
make ci         # lint + typecheck + tests + backlog validation
# Later (after M1): make demo / make demo-stop / make budget
```

Status: pre-alpha (milestone M0). Next spike: **T-M0-07** (Mac sizing + Token Factory latency).
See `docs/BACKLOG.md`.
