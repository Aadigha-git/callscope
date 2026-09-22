# Resume bullets (draft — from real run IDs)

- Built **CallScope**, a local Apple Silicon voice-agent stack (LiveKit + Hermes + Token Factory)
  with consent-gated sessions, session cap=2, and scrubbed structured logging.
- Shipped **eval harness** (stage-replay + caller-sim) with cassette CI, bootstrap CIs, and
  golden run `39692d2c-4b41-4dd3-ba90-205df186a23d`.
- Ran improvement protocol: **E1 hotwords** (MLflow `23f6d373…`) and **E3 VAD/endpoint**
  (MLflow `cd36bba1…`) adopted; optional E2 LoRA deferred pending telephony train data.
- Implemented **governance**: model cards, validation reports, risk register, lifecycle API
  gates (HTTP 409 + unmet); security suite for design §8.3.
- Packaged **showcase**: `make demo` runbook, static site, load report `load-694f5a9867b5`
  documenting NFR-01 projected gap vs Hermes turn p50 ~2.7 s.
