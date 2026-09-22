# CallScope write-up

Numbers below come from committed run IDs / DECISIONS entries. Do not treat mock WER=0
as production ASR quality.

## Problem

Voice agents fail in ways text chatbots do not: endpointing, barge-in, ASR entity errors,
tool-call discipline, and latency under a hosted LLM hop. CallScope packages a **local Mac
demo** with an evaluation harness, review console, improvement protocol (E1–E3), and
governance gates so those failures are measurable and promotable.

## Design choices (ADRs)

| ADR | Choice |
|-----|--------|
| ADR-001 / S-3 | Hermes API server + Token Factory LLM (`Nemotron-3_5-Lightning`) |
| ADR-002 | LiveKit Agents; native `livekit-server` on Mac |
| ADR-006 | Voice worker is latency source of truth |
| ADR-007 | Stage-replay + caller-sim eval modes |
| ADR-010 / ADR-017 | Local-only demo; no public abuse edge |
| ADR-014..016 | Hybrid models, budget guard, cassettes |
| D-20260922-41 | File-backed model/stack registry + optional MLflow |
| D-20260922-45 | Session concurrency cap = 2; NFR-01 projected gap documented |

Topology: [`docs/img/topology-local-mac.svg`](img/topology-local-mac.svg).

## Benchmarks (with IDs)

### Baseline (synthetic / mock)

- Run: `39692d2c-4b41-4dd3-ba90-205df186a23d` — [`docs/reports/baseline.md`](reports/baseline.md)
- Mode: `stage_replay`, stack `stack-mock-baseline`, n=20 golden items
- WER all = 0.00 on **mocks** (expected; not a live ASR claim)
- Recorded human half: **pending** (D-20260921-38)

### Token Factory / Hermes (spikes)

- S-6 TF chat TTFT p50 ≈ **699 ms** (D-20260920-17)
- S-3 Hermes turn p50 ≈ **2.7 s** on Lightning (D-20260920-18)
- Projected e2e vs NFR-01 (p50 ≤ 1.8 s): **gap** — load report projected p50 ≈ 3200 ms
  (D-20260922-45, run `load-694f5a9867b5`)

### Concurrency (T-M6-01)

| Concurrency | resp p50/p95 (mock oracle) | Session cap |
|---:|---:|---|
| 1 | 500 / 500 ms | — |
| 2 | 500 / 500 ms | third blocked at 2 |

No mock-path knee at 1→2. Public cap remains **2**.

## Root-cause / review

Seed-demo review console plants ≥30 labelled calls with auto-flag + attribution
(T-M4-01..03). Distribution drives E1 vs E3 choice (turn-taking → E3 after E1).

## Improvement experiments

| Exp | Decision | Evidence |
|-----|----------|----------|
| E1 hotwords | **Adopt** | MLflow `23f6d3731fd54dcbb1d576a76eb2835f`; D-20260922-42 |
| E3 endpoint/VAD | **Adopt** | MLflow `cd36bba1573c46a182d703bd3024d6ca`; D-20260922-43 |
| E2 LoRA | **Deferred** | No telephony train set; D-20260922-44 |

## Governance

- Model/stack registry + lifecycle gates on `/v1/models/{id}/transition` (409 + `unmet`)
- Sample card: [`docs/model_cards/asr-mlx-whisper-tiny-9cc29594.md`](model_cards/asr-mlx-whisper-tiny-9cc29594.md)
- Risk template + R-SEC-LOCAL; security suite `tests/security/` (D-20260922-46)

## Limitations

- Synthetic / mock eval dominates; volunteer WAVs still open (D-20260921-38)
- E1/E3 used offline proxies where Metal audio was unavailable — re-validate live
- NFR-01 not claimed met on live Hermes hop
- Demo video binary is operator-recorded (D-20260922-47); SIP dropped (T-M6-04)

## Lessons

1. Cassette-first CI keeps LLM spend inside a hard budget.
2. Oracle + mock transport unlocks caller-sim without a full stack in every PR.
3. Governance as code (cards, gates, scrub, toolset self-test) is cheaper when wired early.
4. Honest gap documentation beats claiming mock latencies as live SLOs.

## Interview one-pager

See [`docs/interview/RESUME_BULLETS.md`](interview/RESUME_BULLETS.md) and
[`docs/interview/WALKTHROUGH_2MIN.md`](interview/WALKTHROUGH_2MIN.md).
