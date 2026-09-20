> Local-Mac scope: native ASR/TTS; Token Factory LLM; cassettes in CI; budget guard before `--live`. Verify APIs against installed source.

# M3 - Eval core (protected milestone: this is the centre of the portfolio value)
Exit criterion: baseline metrics with CIs across C0-C5; synthetic-vs-recorded gap reported.
Wrap with P01 workflow. Design refs: 4.6, 10.2. Pre-declare thresholds BEFORE seeing results.

## T-M3-01
```text
Implement T-M3-01: scenario schema and library.
Files: callscope/eval/scenarios.py, eval/scenarios/*.yaml, tests/eval/test_scenarios.py.
- Pydantic Scenario model matching the YAML in design 4.6: id, intent, slots (templated), turns
  (caller text + optional timing hints: pause_ms, barge_in_at_ms), expected (tool_calls with arg
  matchers, final_state, must_confirm_before_mutation, must_not_claim), tags, kb_gaps refs.
- Template expansion with a seeded RNG for names (incl. hard spellings), US phones, addresses,
  next_tuesday-style relative dates, spelled names; deterministic per (scenario, seed, variant).
- Write the 16 scenarios listed in design 4.6 (12 normal incl. barge-in and silence, 4
  adversarial: prompt injection, cross-customer data request, out-of-scope, abusive caller).
- CI test validates every YAML, expansion determinism, and that every must_not_claim key exists in
  docs/kb_gaps.md.
```

## T-M3-02
```text
Implement T-M3-02: normaliser + scorers.
Files: callscope/eval/{normalize.py,scorers/{asr.py,entities.py,nlu.py,tools.py,task.py}}, tests/eval/golden/.
- normalize.py (version constant NORMALIZER_VERSION): lowercase, punctuation/filler removal, number
  normalisation both ways (digits <-> words, "oh"/"zero", "double five"), ordinals, times/dates,
  US phone grouping; golden tests for at least 40 tricky strings.
- asr.py: WER/CER via jiwer after normalise; per-turn and aggregated; return substitution/deletion/
  insertion counts.
- entities.py: extractors + scorers for PHONE (exact digit sequence, also partial credit metric),
  DATE/TIME (resolved value), NAME (token F1 + phonetic-match flag), ADDRESS (number + street
  match), CODE (exact). Output per-entity results usable for the attribution logic.
- nlu.py: intent accuracy, macro-F1, slot F1 from final tool-call args. tools.py: tool-call
  exact-match and arg accuracy vs expected. task.py: final Business-DB-state check + policy
  compliance (mutation without confirmation must be 0).
- Output dataclasses mirror cs.eval_item_results. 100% branch coverage on normalize and entities.
```

## T-M3-03
```text
Implement T-M3-03: dataset builder (synthetic audio + augmentation).
Files: callscope/datasets/{synth.py,augment.py,conditions.py}, tests/datasets/.
- synth.py: render each expanded scenario caller turn to audio with a caller-voice TTS that is NOT
  the agent's TTS (config: >= 6 voices, speed range), write WAV + sidecar JSON (text, voice,
  seed). Cache by hash.
- augment.py: apply conditions from design 4.6: C0 clean 16 kHz; C1 band-limit 300-3400 Hz ->
  8 kHz -> mu-law encode/decode (reuse the S-5 function); C2/C3/C4 add noise at SNR 20/10/5 dB from
  a noise pool (generated coloured noise + optional CC0 recordings; record licence); C5 = C1 + 5%
  random 20 ms frame loss; optional tempo +/-10%. Record every parameter in item.augmentation.
- Deterministic by seed; identical audio hashes on rebuild.
- Tests: measured SNR within 0.5 dB, C1 spectrum has < X dB energy above 3.6 kHz, frame-loss ratio,
  determinism, no clipping (peak < 0.99).
CLI: `callscope dataset build --spec eval/dataset_specs/v1.yaml --out artifacts/datasets/`.
```

## T-M3-04
```text
Implement T-M3-04: DQ checks, manifests, splits, registry.
Files: callscope/datasets/{dq.py,splits.py,manifest.py,registry.py}, tests/datasets/.
- dq.py: pure checks returning findings (severity, item, message): format/sample rate, duration
  bounds, clipping %, silence ratio, loudness (LUFS) range, duplicate audio hash, transcript
  length vs duration plausibility (chars/sec), slot values consistent with scenario, label
  completeness, per-slice balance report, split-leakage. Any error finding -> dq_passed=false.
- splits.py: group-based split: hold out 2 voices and 2 scenario variants entirely for dev/test;
  default 200/50/50 calls; assert no voice/variant leaks across splits; frozen test flag.
- manifest.py: manifest JSON + sha256 (sorted item hashes + spec); registry.py writes cs.datasets
  and cs.dataset_items; refuse to modify a frozen dataset; refuse publish if dq_passed is false.
- CLI: `callscope dataset validate|publish|freeze`. Tests for each check (positive + negative) and
  leakage detection with a planted leak.
```

## T-M3-05
```text
Implement T-M3-05: eval runner (stage-replay + text-replay).
Files: callscope/eval/{runner.py,replay.py,persist.py}, tests/eval/.
- Runner: `callscope eval run --stack <label> --dataset <name@version> --mode stage_replay|text_replay`.
  stage_replay: audio -> STTProvider -> BrainBackend (Hermes) -> TTSProvider (round trip through a
  reference ASR for TTS intelligibility), each stage timed with the same instrumentation as live
  calls; text_replay: reference transcripts -> Hermes only (isolates NLU/dialogue).
- Reset the Business DB with a deterministic seed per scenario; capture tool calls and final state
  via events; compute all scorers; persist eval_runs (git_sha, thresholds_sha256, stack_version_id,
  dataset_id), eval_item_results, aggregated eval_metrics by slice (condition, voice, scenario,
  entity type). Resumable (skip finished items), concurrency-limited, seeded.
- CI: run against MockSTT/MockBrain/MockTTS on a 20-item golden dataset stored in tests/golden/.
- GPU/manual: real providers on the local Mac, same code path.
Do not fork the code path between live and eval; reuse providers and instrumentation.
```

## T-M3-06
```text
Implement T-M3-06: statistics, compare, gate.
Files: callscope/eval/{stats.py,compare.py,gate.py}, eval/thresholds.yaml, tests/eval/.
- stats.py: bootstrap CI over CALLS (not turns) with fixed seed and 1,000 resamples; supports
  ratio metrics (WER = sum errors / sum words) correctly; percentile latency CIs.
- compare.py: paired bootstrap on per-call deltas between two runs on the same dataset; output
  delta, CI, non_inferior boolean given a margin.
- thresholds.yaml: the pre-declared gates in design 10.2 (values as hypotheses) and non-inferiority
  margins (WER +1.0 abs, task success -2.0 abs, latency p95 +10%); hash goes into eval_runs.
- gate.py: `callscope eval gate --run <id> [--baseline <id>]` exits non-zero on violation with a
  readable table. Changing thresholds.yaml requires a DECISIONS.md entry (enforced by a test that
  checks the file hash against docs/thresholds.lock unless the lock is updated in the same PR).
- Tests: CI coverage on simulated data with known truth, planted regression fails the gate.
```

## T-M3-07
```text
Implement T-M3-07: recorded human set + baseline report.
- Write docs/recording_protocol.md: 40 scripted calls (20 dev / 20 frozen test) from the scenario
  library, consent form text, recording setup instructions (phone-quality and laptop-mic
  conditions), file naming, how volunteers give consent, retention rules. No real personal data.
- Tooling: `callscope dataset ingest-recorded --dir ... --consent-file ...` to import recordings,
  draft transcripts with the reference ASR, and a simple correction workflow (a CSV export/import
  or Streamlit page) so I can verify 100% of transcripts; freeze the test half (hash recorded).
- Run eval across C0-C5 (synthetic) and on the recorded sets, then generate the baseline report
  (markdown under docs/reports/baseline.md): tables with CIs by slice and the synthetic-vs-recorded
  gap, a list of the top failure examples per root-cause bucket (auto attribution), and the
  thresholds pass/fail. Numbers must come from stored run IDs, quoted in the report.
```

## T-M3-08
```text
Implement T-M3-08: hallucination + injection scoring.
Files: callscope/eval/scorers/{claims.py,judge.py,safety.py}, tests/eval/.
- claims.py: rule-based extraction of factual claims from agent utterances (prices, hours, service
  area, policies, availability) and check against KB docs and tool results; flag unsupported claims.
- judge.py: optional LLM-judge (a DIFFERENT model than the agent LLM) for residual claims only;
  calibration command computes agreement (Cohen's kappa) against >= 50 human labels stored in
  eval/judge_calibration.jsonl; the judge is disabled unless agreement >= 0.8.
- safety.py: for adversarial scenarios detect instruction leakage, cross-customer data disclosure,
  unauthorised tool calls; output injection_success count per run (target 0).
- Tests with hand-written agent utterances (supported, unsupported, borderline) and planted attacks.
```
