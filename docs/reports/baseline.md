# Baseline report (M3)

**Status:** Synthetic half published. Recorded human half **pending** volunteer sessions
per [`docs/recording_protocol.md`](../recording_protocol.md) (D-20260921-38).

## Reproduction

| Field | Value |
|-------|-------|
| Synthetic run_id | `39692d2c-4b41-4dd3-ba90-205df186a23d` |
| Dataset | `golden-eval@v1` (20-item CI golden; stand-in until full synth C0–C5 re-run) |
| Stack | `stack-mock-baseline` (MockSTT / CassetteBrain / MockTTS) |
| Mode | `stage_replay` |
| git_sha | `49dd3b77a2303a0d28addafe8990a2b809cf60af` |
| Command | `python -m callscope.devtools.eval_cli run --stack stack-mock-baseline --dataset golden-eval@v1 --mode stage_replay` |

Full synth Spec v1 (~120 calls) should replace this golden stand-in before promotion gates.

## CI-width caveat

Bootstrap CIs over calls (n=120 synthetic typical). Recorded human sets are smaller (n≈30);
expect substantially wider intervals (roughly scaling as 1/sqrt(n)). Do not over-interpret
slice CIs with n<30. (`callscope.eval.stats.ci_width_note`)

## Synthetic slice table (WER)

From run `39692d2c-4b41-4dd3-ba90-205df186a23d` (mock providers → WER 0 is expected, not a
claim about production ASR):

| Slice | WER | n |
|-------|----:|--:|
| all | 0.00 | 20 |
| cond=C0 | 0.00 | 12 |
| cond=C1 | 0.00 | 3 |
| cond=C2 | 0.00 | 2 |
| cond=C3 | 0.00 | 1 |
| cond=C4 | 0.00 | 1 |
| cond=C5 | 0.00 | 1 |

Bootstrap CIs not expanded here (point estimates only on this mock run). Re-run with real
native ASR for meaningful intervals.

## Thresholds (absolute gates)

Gate against `eval/thresholds.yaml` after a **real-provider** synth run:

```bash
make eval ARGS='gate --run <run_id> --out artifacts/eval_runs --require-metric'
```

Mock golden run intentionally under-reports telephony/NLU/tool metrics required by §10.2;
do not treat the mock WER=0 table as a §10.2 pass.

## Recorded set

| Item | Status |
|------|--------|
| Consent + protocol | Ready (`docs/recording_protocol.md`) |
| Ingest / CSV correction / freeze | Ready (`callscope dataset ingest-recorded\|export-transcripts\|import-corrections\|freeze-recorded-test`) |
| 15–20 dev / 15–20 frozen test WAVs | **Not yet recorded** |
| Recorded eval run_id | TBD |
| Synthetic vs recorded WER gap | TBD (report with CI once recorded run exists) |

## Top failures / root cause

Auto root-cause attribution lands in T-M4-01. This baseline has no failure examples on the
mock golden run (WER=0, empty tool predictions).

## Sign-off

| Role | Name | Date | Notes |
|------|------|------|-------|
| Author | BAG / agent | 2026-09-21 | Synthetic mock baseline only |
| Reviewer | | | Pending recorded half |
