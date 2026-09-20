> Local-Mac scope: native ASR/TTS; Token Factory LLM; cassettes in CI; budget guard before `--live`. Verify APIs against installed source.

# M6 - Hardening, telephony (stretch), release
Exit criterion: local demo window run; README + write-up complete; v1.0.0 released. Wrap with P01.

## T-M6-01
```text
Task T-M6-01: load test. Using the caller simulator, run 1..5 concurrent calls on the local Mac,
5 minutes each, 3 repetitions. Produce a chart (p50/p95 response latency and barge-in stop vs
concurrency) with the script and raw data stored under docs/reports/load/. Identify the knee, tune
Token Factory (max-num-seqs, prefix caching), ASR batching and worker settings, re-run, and record the final
public concurrency cap in DECISIONS.md. Acceptance: >= 3 concurrent calls within 20% of the NFR-01
p95 target. Never run load tests against the local demo.
```

## T-M6-02
```text
Task T-M6-02: security suite and abuse controls. Implement automated tests for the six security
requirements in design 8.3 (tests/security/, marker security): consent/consent enforcement;
Hermes effective toolset equals allowlist; adversarial eval suite yields 0 injection successes
(runs on the local Mac); gitleaks + pip-audit clean in CI and no plaintext secrets in compose;
caps under load (concurrency, duration, rate limits); retention purge test. Also verify the Hermes
container egress allowlist (curl to an external host must fail; Token Factory and Business API succeed),
CSP headers on the web app, XSS test in the review console, token scoping. Fix issues found; every
finding becomes a DECISIONS.md entry or a backlog task. Update the risk register.
```

## T-M6-03
```text
Task T-M6-03: GPU lifecycle + offline mode. Implement `make demo-up` / `make demo-down` using the
cloud CLI procedure from S-6 (scripts/gpu_up.sh, gpu_down.sh): start VM, wait for health of every
service, load models, run a smoke call via the caller simulator, then flip the status endpoint to
online; down: drain sessions, stop VM. Add the idle auto-shutdown (30 min with 0 active calls from
the callscope_active_calls metric; hard max uptime per window) with a log line and notification.
Offline mode: status page shows offline state, next window, recorded sample calls (consented or
synthetic), and the latest eval dashboard snapshot. Tests for the idle detector logic with fake
metrics; document runbooks in docs/runbooks/. Never store cloud credentials in the repo.
```

## T-M6-04
```text
Task T-M6-04 (stretch): C1-C5 telephony simulation inbound. First complete spike S-7: one inbound test call from a C1-C5 telephony simulation
trunk provider reaches a stub agent through livekit-sip (verify current docs/config from the
installed livekit-sip release). Then wire the trunk to the real worker with 8 kHz handling
(resample at the edge; the ASR path already supports C1-style audio), per-number call and minute
caps, allowlist, no outbound dialing, and a kill switch. Compare live 8 kHz WER on 10 recorded
calls with the simulated C1 numbers and report the gap. Add toll-fraud controls from design T6.
Acceptance: one inbound call completes a booking; caps verified. Stop and ask me before buying a
number or enabling anything that costs money.
```

## T-M6-05
```text
Task T-M6-05: polish, write-up, v1.0.0. (1) README that lets a stranger reproduce the eval on mock
providers in < 10 minutes and describes the live demo; architecture diagram (export the mermaid
diagrams from the design doc to PNG/SVG under docs/img/). (2) docs/WRITEUP.md: problem, design
choices (link ADRs), benchmark results with CIs, root-cause analysis, the improvement experiment,
governance artifacts, limitations (synthetic vs real, small recorded set), and lessons. Pull every
number from stored run IDs/validation reports. (3) Demo windows: recorded sample calls, video,
status page copy. (4) Release: version 1.0.0, CHANGELOG, `make build`, tag, release with wheel +
validation report attached (run the milestone-close prompt first). (5) Prepare a resume-bullet
draft and a 2-minute interview walkthrough script based on the real results.
```


## T-M6-04
```text
DROPPED. Do not implement SIP. FR-15 / ADR-012 superseded; telephony realism = C1–C5 only.
```
