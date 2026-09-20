> Local-Mac scope: native ASR/TTS; Token Factory LLM; cassettes in CI; budget guard before `--live`. Verify APIs against installed source.

# M4 - Call review, caller simulator, dashboards (protected milestone)
Exit criterion: 30+ calls reviewed and labelled; root-cause distribution produced. Wrap with P01.

## T-M4-01
```text
Implement T-M4-01: auto-flag rules and root-cause attribution.
Files: callscope/review/{flags.py,attribution.py,timeline.py}, tests/review/.
- timeline.py: build a per-call timeline model (caller VAD spans, ASR partial/final, endpoint
  decisions, brain first-token, tts first audio, playback start/stop, tool calls, barge-ins) from
  events; pure functions.
- flags.py: one small rule object per flag from design 4.7 (low ASR confidence; tool-arg entity not
  in ASR text; caller repetition/"what/sorry"; dead air > 2 s; agent starts while caller speaking;
  barge-in then restart-from-scratch; policy denial; tool error; unsupported claim; caller hangs
  up within 10 s of an agent turn; eval failure). Thresholds configurable.
- attribution.py: implement the first-pass algorithm in design 4.7 returning RC codes with a
  confidence and the evidence event IDs.
- Tests: for each rule and RC branch build a synthetic timeline (positive + negative + boundary).
After T-M4-03, compute agreement of auto attribution vs your human labels and report it.
```

## T-M4-02
```text
Implement T-M4-02: review/eval/governance-read endpoints.
Files: apps/api/routes/{calls.py,labels.py,eval.py,models.py}, tests/api/.
- Implement exactly the endpoints in docs/api/openapi.yaml: GET /v1/calls (filters + cursor
  pagination), GET /v1/calls/{id}, GET /v1/calls/{id}/audio (signed URL, 5 min), POST
  /v1/calls/{id}/labels, POST /v1/datasets:export-labelled, GET/POST /v1/eval/runs, GET
  /v1/eval/runs/{id}, GET /v1/eval/compare, GET /v1/models (read side).
- Service-token auth on all; audit-log label/export actions; contract tests validate against the
  spec; audio URL expiry and unauthenticated denial tests; pagination stability tests.
- Update openapi.yaml if anything had to change and log a decision.
```

## T-M4-03
```text
Implement T-M4-03: Call Review console (Streamlit, apps/review).
- Talk ONLY to the CallScope API. Pages: Inbox (filters: flag, root cause, model/stack version,
  date, condition, channel), Call detail (audio player, lane timeline chart from timeline.py output,
  transcript with reference diff when a scenario exists, tool calls with scrubbed args), Label form
  (RC code from the taxonomy, severity 1-4, notes, "add to dataset: train/dev"), Dataset export
  (labelled failures -> new dataset version draft), Compare eval runs (metrics table with deltas).
- Escape all transcript text; never use unsafe_allow_html with call content. Behind localhost reverse-proxy (N/A) auth.
- Add a `callscope review seed-demo` command creating 40 synthetic calls with planted failures so I
  can practise labelling before real traffic, and a page showing root-cause distribution + human vs
  auto attribution agreement.
- Tests: pure helpers (timeline chart data, diff), API client with mocked responses.
```

## T-M4-04
```text
Implement T-M4-04: caller simulator + caller_sim eval mode.
Files: callscope/sim/{caller.py,oracle.py}, callscope/eval/runner_sim.py, tests/sim/.
- Caller: LiveKit rtc participant (verify the Python rtc API from the installed package) that
  joins the room via a token from the API (consent flag set for sim channel), plays scenario
  audio (dataset items) with realistic timing (pause_ms), optionally starts speaking mid-agent
  sentence per barge_in_at_ms, and records what it hears.
- Oracle: from the scenario timeline compute expected turn-taking outcomes to score premature
  endpoint, late endpoint (dead air > 2 s), missed/false barge-in, barge-in stop latency, and
  end-to-end response latency from events (worker clock).
- Runner: `callscope eval run --mode caller_sim` runs all scenarios unattended against the
  local Mac, writes results to eval tables; failures produce reviewable calls (channel=sim).
- Tests: oracle logic with synthetic timelines; smoke test with mocks in CI; real run under marker gpu.
```

## T-M4-05
```text
Implement T-M4-05: quality/drift dashboards + alerts.
- Grafana provisioned dashboards: Quality & drift (ASR confidence distribution, tool error rate,
  policy denials, flagged-call rate, latest eval metrics via a small metrics exporter reading
  eval_metrics), Cost (GPU uptime, sessions/hour).
- Prometheus alert rules: p95 response latency > NFR-01 for 10 min, provider error rate > 5%, GPU
  node up with 0 sessions for 30 min, monthly credit budget threshold (documented manual metric).
- CI: `promtool check rules` and dashboard JSON lint; unit test the exporter query logic.
```


## T-M4-06
```text
Implement T-M4-06: optional LangSmith tracing (default off).
- Behind CALLSCOPE_LANGSMITH_ENABLED; use langsmith SDK and/or OTEL exporter.
- scrub() fictional text only; never audio; never real PII. Postgres remains SoT (ADR-006).
- Decide whether LangSmith datasets/experiments earn a place for judge eval; record in DECISIONS.md.
```
