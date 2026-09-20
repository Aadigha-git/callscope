# Technical decision log

Append-only. Newest first. One entry per decision, spike result, or deviation from the design doc
(`docs/design/CallScope_Phase3_Design.md`). ADR-001..013 from the design doc are the baseline.

## Template
```
### D-YYYYMMDD-NN - <short title>
- Date / Task: <date> / <T-Mx-yy>
- Context: <what forced a decision; evidence with run IDs or links>
- Decision: <what we do>
- Alternatives considered: <and why not>
- Consequences: <good/bad/follow-ups; tasks created>
- Design doc impact: <ADR-xxx updated? section changes? none>
- Status: proposed | accepted | superseded by D-...
```

## Baseline ADRs (from the design doc)
ADR-001 Hermes via API server | ADR-002 LiveKit Agents, no rebuild of streaming TTS/barge-in |
ADR-003 Self-hosted models, benchmark-driven | ADR-004 Cascaded STT-LLM-TTS |
ADR-005 Postgres + event log + object store | ADR-006 Worker is latency source of truth |
ADR-007 Two eval modes | ADR-008 Synthetic-first data + recorded set |
ADR-009 Two-node, on-demand GPU, Compose | ADR-010 Security posture | ADR-011 Governance as code |
ADR-012 SIP is a stretch | ADR-013 Streamlit review console

## Entries
### D-20260920-02 - Align pre-commit ruff with project ruff 0.16.8
- Date / Task: 2026-09-20 / T-M0-01
- Context: Hook pin `astral-sh/ruff-pre-commit@v0.5.7` auto-fixed `@pytest.mark.integration` to `@pytest.mark.integration()`, which fails PT023 under project `ruff==0.16.8` used by CI (`uv run ruff`).
- Decision: Bump pre-commit ruff hook to `v0.16.8` to match `uv.lock`.
- Alternatives considered: ignore PT023 (rejected); keep dual versions (rejected: fight on every commit).
- Consequences: first `pre-commit run` after pull may re-download the hook env.
- Design doc impact: none.
- Status: accepted

### D-20260920-01 - CI pip-audit via uv export, not --strict --skip-editable
- Date / Task: 2026-09-20 / T-M0-01
- Context: `uv sync` installs `callscope` editable. Installed `pip-audit` 2.10.1 (`pip_audit._cli`): `--skip-editable` yields `SkippedDependency`, and `--strict` fatals on any skip (`callscope: distribution marked as editable`). Combining both flags made the security job always fail.
- Decision: In CI, `uv export --frozen --no-emit-project --extra dev` then `pip-audit -r … --strict --disable-pip`. Keep `--strict` for third-party collection failures; omit the local project from the audit set.
- Alternatives considered: drop `--strict` (weakens gate); drop `--skip-editable` and audit editable (fails for other reasons / noise); ignore vuln for callscope (wrong tool).
- Consequences: security job audits locked deps only; local package changes are covered by tests/mypy/ruff, not CVE DB.
- Design doc impact: none (aligns with §4.12 gitleaks + dependency audit in CI).
- Status: accepted

### D-20260919-01 - Schedule re-baselined from the task backlog
- Date / Task: 2026-09-19 / T-M0-01
- Context: The design doc (12.3) guessed 5-6 weeks part-time. Bottom-up estimates in backlog/tasks.yaml total 459 h (P0: 375 h, P1-P3: 84 h): M0 43, M1 106, M2 58, M3 92, M4 60, M5 50, M6 50.
- Decision: Plan from the backlog, not the guess. At 30 h/week that is about 15 weeks for everything, about 12.5 weeks for P0 only. Re-estimate after sprints S1 and S2 using actual hours (velocity ratio). If a shorter path is needed use the thin-slice cut in docs/DEV_GUIDE.md section 5.
- Alternatives considered: shrink estimates to fit 6 weeks (rejected: not credible); drop protected M3-M5 (rejected: it is the portfolio value).
- Consequences: sprint plan in DEV_GUIDE section 5; milestone dates move; design 12.3 effort sentence updated.
- Design doc impact: section 12.3 effort sentence only.
- Status: accepted
