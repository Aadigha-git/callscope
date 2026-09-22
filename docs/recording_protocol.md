# Recording protocol — consented human call set (T-M3-07)

Fictional Lakeside Home Services receptionist demo only. **No real personal data.**
Volunteers use fake names, phones, and addresses from the scenario library.

## Goals

| Split | Count | Purpose |
|-------|------:|---------|
| Dev | 20 | Tuning / inspection (not frozen) |
| Frozen test | 20 | One-shot gate eval after experiments |
| **Total** | **40** | Design prompt; milestone acceptance also cites ~30 (15/15) as minimum |

Prefer 40 scripted calls when volunteers are available; **15 dev / 15 frozen test** is the
acceptance floor. CI width: see `callscope.eval.stats.ci_width_note` and D-20260921-37 —
n≈30 recorded yields wider bootstrap CIs than n≈120 synthetic.

## Consent (required before any recording)

Volunteers must agree to the following (store a signed/dated copy with the batch):

> I consent to record my voice interacting with the **fictional** CallScope / Lakeside
> Home Services demo agent for evaluation research. I will use only **fake** personal
> details (no real phone, address, or name). Audio is stored locally, retained ≤ 30 days
> unless I opt in to a reviewed donation, and is never uploaded to Token Factory,
> LangSmith, or Toloka. I may withdraw by contacting the project owner; withdrawal
> triggers deletion of my recordings.

Policy version: `consent_policy_v1` (match API consent version when session starts).

Show the fictional-data banner in the web client before the call.

## Environment

1. Local Mac demo: `make demo` (API, LiveKit, ASR/TTS, worker, biz, Hermes as needed).
2. Two capture conditions (label each file):
   - `laptop` — built-in or USB mic, quiet room
   - `phone` — smartphone mic or headset; mild room noise acceptable (maps toward C1–C2)
3. Browser client: consent gate → join room → follow scenario script.
4. Operator: enable call recording only after server-side consent (T-M2-06).

## Scenario assignment

Draw from `eval/scenarios/*.yaml` (16 templates). Expand with seed `recording-v1` so
slots/utterances are deterministic. Suggested mix (40 calls):

| Bucket | Count | Notes |
|--------|------:|-------|
| Book / reschedule / cancel | 12 | Mutating tools; confirm before mutate |
| Hours / pricing / KB | 8 | Include KB-gap scenarios (`must_not_claim`) |
| Callback / status / complaint | 6 | |
| Barge-in / silence recover | 4 | Turn-taking |
| Adversarial (injection / hallucination bait) | 4 | Do not grant unauthorised actions |
| Free-form wrap / thanks | 6 | Closing + repair |

Assign `split=dev` or `split=test` **before** recording; do not re-label after hearing
outcomes. Frozen test hashes are recorded at ingest freeze.

## File naming

```
artifacts/datasets/recorded/v1/
  audio/
    rec_001_book_plumbing_laptop.wav
    rec_002_hours_saturday_phone.wav
    ...
  consent/
    batch_consent.md          # signed summary + volunteer aliases (fake)
  drafts/
    transcripts.csv           # draft ASR + correction columns
  manifest.json
```

Pattern: `rec_{NNN}_{scenario_id}_{laptop|phone}.wav` — mono PCM WAV 16 kHz preferred
(ingest resamples if needed via existing audio helpers).

## Ingest and correction workflow

```bash
# 1. Import WAVs + consent file → draft transcripts (reference ASR / mock in CI)
make dataset ARGS='ingest-recorded --dir artifacts/datasets/recorded/v1 --consent-file artifacts/datasets/recorded/v1/consent/batch_consent.md'

# 2. Export CSV for human correction (reference_text → corrected_text)
make dataset ARGS='export-transcripts --dataset artifacts/datasets/recorded/v1 --out artifacts/datasets/recorded/v1/drafts/transcripts.csv'

# 3. After editing corrected_text for 100% of rows:
make dataset ARGS='import-corrections --dataset artifacts/datasets/recorded/v1 --csv artifacts/datasets/recorded/v1/drafts/transcripts.csv'

# 4. Freeze test half (hashes recorded; further transcript edits refused)
make dataset ARGS='freeze-recorded-test --dataset artifacts/datasets/recorded/v1 --seed 42'
```

Verification: every item must have `transcript_verified=true` before freeze.

## Retention

- Raw audio / payloads: purge after 30 days (`make purge`) unless reviewed opt-in donation.
- Scrubbed fictional transcripts may be kept for eval with the dataset version.
- Never send raw audio to third parties (design §8.6).

## Baseline report

After synthetic C0–C5 eval **and** recorded ingest+freeze:

```bash
make eval ARGS='run --stack <label> --dataset <synth> --mode stage_replay'
make eval ARGS='run --stack <label> --dataset recorded@v1 --mode stage_replay'
# Then update docs/reports/baseline.md with run IDs, CIs, synthetic-vs-recorded gap.
```

Numbers in the baseline report must cite stored `run_id` values. Do not invent metrics.
