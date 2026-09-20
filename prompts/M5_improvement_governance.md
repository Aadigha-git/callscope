> Local-Mac scope: native ASR/TTS; Token Factory LLM; cassettes in CI; budget guard before `--live`. Verify APIs against installed source.

# M5 - Improvement loop and governance (protected milestone)
Exit criterion: one measured improvement on the frozen test; promoted model has card + report.
Rules: hypothesis and success criterion are written BEFORE running; train on train, tune on dev,
evaluate ONCE on frozen test; log every experiment (including null results). Wrap with P01.

## T-M5-01
```text
Implement T-M5-01: MLflow + model inventory + stack registry.
Files: callscope/governance/{registry.py,mlflow_utils.py}, apps/api/routes/models.py additions, tests/.
- Add MLflow tracking (compose service on the CPU node, artifacts in MinIO). Helper to log a run
  with git SHA, dataset versions, stack version, config.
- registry.py: register model versions (component, name, base model, revision, licence, artifact
  URI, config hash, intended/out-of-scope use, owner, mlflow_run_id) and stack versions (component
  FKs, Hermes + plugin versions, prompt hash, worker config, git sha); enforce one production stack.
- API: POST/GET /v1/models per openapi.yaml (transition endpoint comes in T-M5-04).
- Backfill: register the models chosen in M0 and the current stack; make eval runs require a
  registered stack. Tests for uniqueness, production constraint, and hash stability.
```

## T-M5-02
```text
Run experiment E1 (T-M5-02): ASR hotword / initial-prompt biasing.
1. Read the baseline report (docs/reports/baseline.md) and the auto/human root-cause distribution;
   write docs/experiments/E1.md with hypothesis, metric, minimum effect of interest, and success
   criterion (e.g. ADDRESS/NAME entity accuracy +N points on C1-C3 without C0 WER regression > 0.5
   abs) BEFORE any run. Commit that file first.
2. Verify from the ASR backend's source/docs how hotwords or initial prompts are supported; add
   a `hotwords` config to the ASR server and worker (vocabulary from streets/services/names lists in
   the business seed; no test-set leakage - build the list only from train scenarios + Business
   seed, never from test transcripts).
3. Evaluate on dev (tune list size/weight), then ONCE on the frozen test; compute paired bootstrap
   CIs; log to MLflow; write results and the decision (adopt / reject) in E1.md and DECISIONS.md.
```

## T-M5-03
```text
Run experiment E2 or E3 (T-M5-03). First choose using the review distribution: if ASR entity errors
dominate -> E2 (LoRA adaptation); if turn-taking errors dominate -> E3 (endpointing/VAD tuning).
Write docs/experiments/E2.md or E3.md with hypothesis + success criteria before running.
E2: build training data ONLY from the train split (+ recorded dev if allowed by protocol), with
C1-C5 augmentation; LoRA fine-tune the ASR model with a documented config (rank, lr, epochs,
seed), serving paused; track loss/dev WER in MLflow; evaluate once on the frozen test incl. clean
(C0) to check regression; register the adapted model as a candidate model version.
E3: grid search endpoint.min_delay/max_delay, vad.threshold, barge_in.min_duration on dev using
caller_sim/stage-replay timing; choose by premature/late endpoint rates with p50 latency +<=100 ms;
evaluate once on frozen test.
Report with CIs (paired bootstrap), slices (voice, condition), compute cost, and a clear
adopt/reject decision; null results are documented, not hidden.
```

## T-M5-04
```text
Implement T-M5-04: governance generator and gates.
Files: callscope/governance/{cards.py,reports.py,risk.py,lifecycle.py}, templates/*.md.j2, tests/.
- cards.py: render a model card per model version (purpose/intended use, components, adaptation
  data, evaluation data, metrics with CIs by slice, limitations incl. synthetic-vs-real gap, safety
  and privacy notes, monitoring plan, change log) from the DB + eval results -> docs/model_cards/.
- reports.py: validation report = thresholds snapshot (from thresholds.yaml + hash), results with
  CIs, pass/fail per gate, slice analysis, comparison with incumbent, open risks, sign-off,
  reproduction command (git SHA, dataset + stack versions) -> docs/validation_reports/ and
  cs.validation_reports. Also render a DOCX version (use python-docx or pandoc).
- risk.py: risk register CRUD + `docs/risk_assessment_template.md`; each promotion requires a
  completed assessment.
- lifecycle.py + POST /v1/models/{id}/transition: candidate->validated requires passing report on
  the frozen test; validated->production requires card complete, monitoring on, rollback stack
  recorded; failing gates return 409 problem+json with the unmet gate list.
- Tests: gate matrix, card completeness, report reproducibility (same inputs -> same output).
```


## T-M5-05
```text
OPTIONAL Experiment E2 (T-M5-05): LoRA ASR on Mac only if T-M0-06 says feasible.
- Estimate memory/time for whisper-small/base via MPS or MLX before any download >2 GB.
- If not feasible: DECISIONS.md deferred entry and stop. If feasible: train on train split only,
  one frozen-test eval, MLflow record. Do not run during a live demo.
```
