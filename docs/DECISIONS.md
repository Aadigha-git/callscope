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
### D-20260919-01 - Schedule re-baselined from the task backlog
- Date / Task: 2026-09-19 / T-M0-01
- Context: The design doc (12.3) guessed 5-6 weeks part-time. Bottom-up estimates in backlog/tasks.yaml total 459 h (P0: 375 h, P1-P3: 84 h): M0 43, M1 106, M2 58, M3 92, M4 60, M5 50, M6 50.
- Decision: Plan from the backlog, not the guess. At 30 h/week that is about 15 weeks for everything, about 12.5 weeks for P0 only. Re-estimate after sprints S1 and S2 using actual hours (velocity ratio). If a shorter path is needed use the thin-slice cut in docs/DEV_GUIDE.md section 5.
- Alternatives considered: shrink estimates to fit 6 weeks (rejected: not credible); drop protected M3-M5 (rejected: it is the portfolio value).
- Consequences: sprint plan in DEV_GUIDE section 5; milestone dates move; design 12.3 effort sentence updated.
- Design doc impact: section 12.3 effort sentence only.
- Status: accepted
