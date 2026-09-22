# CallScope model card — mlx-whisper-tiny @ mlx-community/whisper-tiny

## Purpose and intended use

Local Mac demo ASR (Metal)

## Out of scope

Production telephony without recorded-set validation

## Component

| Field | Value |
|-------|-------|
| Component | asr |
| Name | mlx-whisper-tiny |
| Revision | mlx-community/whisper-tiny |
| Base model | openai/whisper-tiny |
| Licence | MIT |
| Owner | callscope |
| Status | production |
| Artifact URI | n/a |
| Config SHA-256 | f4a446e5217ac4ebd86cbd20b92af8fbb1f6a3da8411f3ae592bf88618ac0d4e |
| MLflow run | n/a |
| Model version ID | 9cc29594-eaf8-454f-936b-3890ba0ff763 |

## Training / adaptation data

_none recorded_

## Evaluation data

_see linked eval run_

## Metrics (with CIs by slice)

| Metric | Slice | Value | n |
|--------|-------|------:|--:|
| wer | all | 0.0 | 20 |

## Known limitations

- Synthetic-vs-real gap: recorded human set may still be pending (see baseline report).
- Accent / voice / noise coverage limited to demo synthetic + optional volunteer WAVs.

## Safety and privacy

- Caller speech is untrusted input; no shell/SQL/path construction from transcripts.
- Third-party exports (Token Factory / LangSmith / Toloka) receive fictional scrubbed text only — never raw audio.

## Monitoring plan

- Live-ops Grafana: latency, errors, active calls.
- Quality/drift: ASR confidence, flagged-call rate, latest eval metrics.
- Alerts: p95 latency, provider errors, LLM budget burn.

## Change log

_initial registration_

---
_Generated 2026-09-22T05:35:35.344762+00:00 · CallScope governance (T-M5-04)_
