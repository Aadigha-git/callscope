# Technical decision log

Append-only. Newest first. One entry per decision, spike result, or deviation from the design doc
(`docs/design/CallScope_Phase3_Design.md`). ADR-001..013 from the design doc are the baseline;
ADR-014..017 added in the local-Mac rescope.

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
ADR-003 Self-hosted models (superseded by ADR-014) | ADR-004 Cascaded STT-LLM-TTS |
ADR-005 Postgres + event log + object store | ADR-006 Worker is latency source of truth |
ADR-007 Two eval modes | ADR-008 Synthetic-first data + recorded set |
ADR-009 Two-node GPU (superseded by ADR-015) | ADR-010 Security posture | ADR-011 Governance as code |
ADR-012 SIP stretch (dropped) | ADR-013 Streamlit review console |
ADR-014 Hybrid models + Token Factory | ADR-015 Local-only Mac deployment |
ADR-016 Budget guard + cassettes | ADR-017 Showcase deliverable

## Entries

### D-20260920-18 - S-3: Choose Nemotron-3.5-Lightning on Token Factory via Hermes
- Date / Task: 2026-09-20 / T-M0-04
- Context: Spike S-3 (U3). hermes-agent 0.19.0 API server with custom provider → Token Factory (`https://api.tokenfactory.nebius.com/v1/`). Stub receptionist toolset locked to `callscope-s3` (no terminal/browser). 60 scripted turns × 3 function_calling candidates. Run ID `394d90d9-702a-44db-b081-be6ee0879428`; raw `spikes/T-M0-04/results/tool_reliability.json`. Total est. spend ~$0.080.
  | Model | Valid tool-call rate | p50 turn (Hermes) | Est. USD |
  |---|---:|---:|---:|
  | nvidia/Nemotron-3_5-Lightning | 100% (60/60) | ~2.7 s | ~0.024 |
  | Qwen/Qwen3-30B-A3B-Instruct-2507 | 100% (60/60) | ~4.8 s | ~0.026 |
  | nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | 98.3% (59/60) | ~10.8 s | ~0.031 |
  Licences/prices per D-20260920-12. Nano miss: one booking turn with no tool call. Injection turns: 0 forbidden tools for all three.
- Decision: **Demo agent LLM = `nvidia/Nemotron-3_5-Lightning`** on Token Factory through Hermes. Alternate: `Qwen/Qwen3-30B-A3B-Instruct-2507`. Optional local mlx-lm/llama.cpp fallback sketched only (`spikes/T-M0-04/docs/local_fallback.md`); not a gate. Avoid Ollama primary (D-20260920-13).
- Alternatives considered: Nano as default (rejected: slower + one miss); Qwen as default (acceptable alternate, slightly higher cost/latency); local-only LLM (deferred — memory budget with ASR/TTS).
- Consequences: set `TOKEN_FACTORY_MODEL` default; T-M0-03 overhead spike uses this model; production plugin must return JSON **strings** from tool handlers (Hermes 0.19 contract).
- Design doc impact: U3 / S-3 resolved; `.env.example` model default updated.
- Status: accepted

### D-20260920-17 - S-6: Mac baseline, native livekit-server, Token Factory regional RTT
- Date / Task: 2026-09-20 / T-M0-07
- Context: Spike S-6 under local-Mac scope. Measured on Apple M5 / 16 GB / macOS 26.6.2 arm64. Installed Homebrew `livekit` 1.13.7 (arm64 bottle). Ran `livekit-server --dev --config-body "port: 17880"` → HTTP 200 (port 7880 was held by Docker Desktop publishing an older LiveKit). Probed Token Factory edges with 100 TCP + 20 HTTPS samples/region (no API key; no chat spend). Raw: `spikes/T-M0-07/results/`.
- Decision: (1) Size local models to ≈12 GB usable (reserve ≥4 GB). ASR/TTS memory deferred to T-M0-06. (2) **Keep ADR-002** — native livekit-server works on macOS; no FastAPI WebSocket fallback ADR. For demo, prefer native on 7880 or document Docker conflict. (3) Prefer Token Factory **us-central1** for network RTT from this location (TCP p50 ≈ 50 ms vs ≈ 191 ms eu-north1). If the chosen model only exists in eu-north1, accept the higher floor and measure chat TTFT in T-M0-04. (4) Chat probe (100 non-streaming tiny completions) on `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` via default `api.tokenfactory.nebius.com`: **p50 699 ms / p95 824 ms**, ~$0.00022 spend, 0 errors (`spikes/T-M0-07/results/tf_chat_ttft.json`).
- Alternatives considered: Docker-only LiveKit (works but 7880 conflict / no need); skip regional probe (rejected — catalog regions differ).
- Consequences: design §9.5 updated; start/stop notes in `spikes/T-M0-07/docs/START_STOP.md` (input to T-M6-03). NFR-01 brain budget must include ~0.7 s hosted hop on eu-north1 for this model class.
- Design doc impact: §9.5 filled; U6 resolved by S-6 / D-20260920-17.
- Status: accepted

### D-20260920-16 - Toloka for TEXT human labels (optional stretch); privacy notes
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: $100 Toloka credit available. Docs: platform API can drive TEXT labelling pipelines ([Programmatic access](https://platform.toloka.ai/docs/integration/programmatic-access/)); unverified teams are on trial and **cannot start a run** until identity/business verification. Platform does not delete datasets via UI/API in the product itself — deletion is account-level under the Privacy Notice ([Security and data handling](https://platform.toloka.ai/docs/explanation/security-and-data-handling/), [Privacy Notice](https://toloka.ai/legal/privacy-notice)). DPA: delete/return on termination subject to legal retention.
- Decision: Optional stretch only for ≥50 fictional agent utterances (supported/unsupported) and optional RCA labels on fictional transcripts. **Never upload audio or real personal data.** If verification/minimum spend/terms do not fit, use manual labelling and record that choice.
- Alternatives considered: skip human labels (weakens judge calibration); upload audio (rejected).
- Consequences: T-M3-08 accepts Toloka or manual; document choice in DECISIONS when executed.
- Design doc impact: §8.6 data-flow.
- Status: accepted

### D-20260920-15 - LangSmith optional tracing (off by default); retention notes
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: $100 LangSmith credit. Python SDK supports tracing; OpenTelemetry ingestion to `https://api.smith.langchain.com/otel` (recommend langsmith≥0.4.25) ([OTEL docs](https://docs.langchain.com/langsmith/trace-with-opentelemetry.md)). Trace retention: base **14 days** or extended **400 days**; datasets retain indefinitely ([usage/billing](https://docs.langchain.com/langsmith/usage-and-billing)). Hide/redact inputs via SDK flags or collector.
- Decision: Optional behind `CALLSCOPE_LANGSMITH_ENABLED` (default off). Trace scrubbed **fictional text only** (brain turns + eval items). Postgres remains SoT (ADR-006). Decide later whether LangSmith datasets/experiments earn a place for judge eval (T-M4-06); if not, document why.
- Alternatives considered: always-on tracing (unnecessary cost/privacy surface); skip entirely (forfeit credit/learning).
- Consequences: T-M4-06; scrubber must run first.
- Design doc impact: §8.6; ADR-017 adjacent.
- Status: accepted

### D-20260920-14 - Apple Silicon ASR/TTS/VAD candidates (docs/PyPI/GitHub; not yet run on this Mac)
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: No CUDA; Docker Desktop cannot use Mac GPU/Metal for containers — ASR/TTS must run natively. Candidates checked from public docs (not installed/benchmarked yet; T-M0-06 runs them):
  - **ASR:** `mlx-whisper` / Whisper via [mlx-audio](https://github.com/Blaizzy/mlx-audio) (MIT); [parakeet-mlx](https://github.com/senstella/parakeet-mlx) Apache-2.0 (weights often CC-BY-4.0 with attribution); whisper.cpp Metal/Core ML; faster-whisper CPU-only on Mac.
  - **VAD:** Silero VAD (ONNX/torch CPU) — already used in LiveKit Agents spike.
  - **TTS:** Kokoro via mlx-audio / [kokoro-mlx](https://pypi.org/project/kokoro-mlx/) (MIT code; Kokoro weights Apache-2.0); kokoro-onnx; Piper (CPU ONNX; GPL-3.0-or-later — licence caution for distribution).
- Decision: Shortlist by **running** on this Mac in T-M0-06 (RTF, memory, first-audio, WER clean vs C1). Prefer streaming ASR; else VAD-segmented chunking. E2 LoRA only if whisper-small/base fits in remaining RAM via MPS/MLX; else defer (T-M5-05).
- Alternatives considered: cloud ASR/TTS (rejected: portfolio story); Dockerized GPU ASR (impossible on Mac Desktop).
- Consequences: T-M0-06 / T-M1-05 / T-M1-06 native servers.
- Design doc impact: §4.3, §9.5.
- Status: accepted (pending measurements)

### D-20260920-13 - livekit-server and Hermes on macOS; prefer Token Factory over Ollama
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context:
  - LiveKit docs: `brew install livekit` then `livekit-server --dev` ([local self-hosting](https://docs.livekit.io/transport/self-hosting/local/)); Homebrew formula ships arm64 bottles, Apache-2.0 ([formulae.brew.sh/formula/livekit](https://formulae.brew.sh/formula/livekit)). **Not yet executed on this machine** — verify in T-M0-07. Fallback if fail: FastAPI WebSocket audio + own VAD (new ADR + tasks).
  - Hermes: installs on macOS; custom OpenAI-compatible provider via `hermes model` / `config.yaml` `provider: custom` + `base_url` ([providers docs](https://hermes-agent.nousresearch.com/docs/integrations/providers); [local LLM on Mac](https://hermes-agent.nousresearch.com/docs/guides/local-llm-on-mac) recommends mlx-lm / llama.cpp). Prior design note V7: Ollama stream+tools hang risk → avoid Ollama as primary.
- Decision: Keep ADR-002; run livekit-server natively. Hermes → Token Factory as custom provider; optional mlx-lm/llama.cpp fallback. Confirm end-to-end in S-6 / S-3.
- Alternatives considered: Docker-only LiveKit (works but extra networking); Ollama primary (rejected).
- Consequences: T-M0-07 acceptance includes brew `--dev` proof.
- Design doc impact: ADR-002 kept; ADR-014/015.
- Status: accepted (pending S-6 runtime proof)

### D-20260920-12 - Nebius Token Factory API facts, candidate LLMs, $25 budget estimate
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: Public docs (no API spend during this rescope):
  - Base URL: `https://api.tokenfactory.nebius.com/v1/` ([list models example](https://docs.tokenfactory.nebius.com/api-reference/examples/list-of-models)).
  - Auth: Bearer API key (`NEBIUS_API_KEY` / we will use `TOKEN_FACTORY_API_KEY` in CallScope `.env`).
  - Catalog: public [`/api/public/models_info`](https://tokenfactory.nebius.com/api/public/models_info) + [model-catalog.md](https://tokenfactory.nebius.com/model-catalog.md) (fetched 2026-09-20).
  - Tools: OpenAI-compatible function calling documented ([function-calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md)); chat completions support `stream` ([API ref](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion)).
  - Rate limits: dynamic; headers `x-ratelimit-*`; HTTP 429 + `Retry-After` ([rate-limits](https://docs.tokenfactory.nebius.com/ai-models-inference/rate-limits.md)). Per-model `per_request_limits` appear in verbose `/v1/models` responses (requires key — **not queried** this session).
  - Speech ASR/TTS: **none** found in the 24-entry public catalog (text2text / image2text / embedding only). Embeddings: e.g. `Qwen/Qwen3-Embedding-8B` @ $0.01/M input.
- Decision: Use Token Factory for the agent LLM (and a different model for the judge). Candidate **function_calling** text2text models from the public catalog (prices USD per 1M tokens):

  | Model ID | In | Out | Licence (catalog) |
  |---|---:|---:|---|
  | nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B | 0.06 | 0.24 | nvidia-open-model-license |
  | nvidia/Nemotron-3_5-Lightning | 0.06 | 0.24 | OpenMDW v1.1 |
  | Qwen/Qwen3-30B-A3B-Instruct-2507 | 0.10 | 0.30 | Apache 2.0 |
  | google/gemma-3-27b-it | 0.10 | 0.30 | Gemma License |
  | deepseek-ai/DeepSeek-V4-Flash-0731 | 0.14 | 0.28 | MIT |
  | openai/gpt-oss-120b | 0.15 | 0.60 | Apache 2.0 |
  | Qwen/Qwen3-235B-A22B-Instruct-2507 | 0.20 | 0.60 | Apache 2.0 |

  **$25 budget sketch (assumption, not a measurement):** ~4k input + 300 output tokens/turn ≈ $0.00049/turn on Qwen3-30B → on the order of **~50k turns** raw, or roughly **hundreds to low thousands of multi-turn receptionist calls** once tools, retries, judge calls, and eval are included. Prefer Nemotron Nano / Qwen3-30B class for cost; keep a $10 reserve (cap $15 default). **Verify tool quality in T-M0-04 before locking.**
- Alternatives considered: local-only LLM (tight on 16 GB with ASR+TTS); spend without cassettes (rejected).
- Consequences: ADR-014/016; T-M0-03/04; no speech models from TF.
- Design doc impact: §4.4, §9, ADR-014.
- Status: accepted

### D-20260920-11 - Machine facts (Apple M5, 16 GB)
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: Ran on this machine: `sysctl -n machdep.cpu.brand_string` → **Apple M5**; `hw.memsize` → 17179869184 (**16 GB**); `sw_vers` → macOS 26.6.2 (25G83); `uname -m` → **arm64**.
- Decision: Size all local model choices to ≤ ~12 GB working set (reserve ≥4 GB for OS + browser). Concurrency default 1 (NFR-03).
- Alternatives considered: n/a (hardware fact).
- Consequences: drives S-5/S-6 memory tables; E2 optional/deferred likely.
- Design doc impact: §9.5 baseline filled.
- Status: accepted

### D-20260920-10 - Rescope: local Mac demo + Token Factory LLM (supersedes GPU VM public demo)
- Date / Task: 2026-09-20 / chore/rescope-local-mac
- Context: Nebius access is Token Factory inference only (no VM provisioning); no other cloud GPU credits. Program credits: Token Factory $25, LangSmith $100, Toloka $100; Tavily not used.
- Decision: Apply ADR-014..017; drop public-demo controls; rewrite backlog (T-M6-04 dropped); deliver `make demo` + video + static showcase.
- Alternatives considered: pause project until GPU credits (rejected); public demo without GPU (infeasible for self-hosted LLM).
- Consequences: large backlog/design update; old total ~459 h → new ~462 h (excl. dropped); schedule regenerated in DEV_GUIDE §5.
- Design doc impact: revision changelog; ADRs; §§1–2, 3.6, 4, 8–12.
- Status: accepted

### D-20260920-05 - S-4: Keep own LiveKit Agents worker; do not adopt hermes-livekit
- Date / Task: 2026-09-20 / T-M0-05
- Context: Spike S-4 (U4). Installed `livekit-agents[silero]==1.8.2`, `livekit==1.1.18`, `livekit-api==1.2.1`; ran `livekit/livekit-server:v1.9.1 --dev`. Minimal AgentServer worker with EchoSTT (`StreamAdapter`+Silero), CannedLLM, SineTTS under `spikes/T-M0-05/`. Headless smoke `SMOKE_OK agent_audio_subscribed` on room `callscope-spike-2` after adding `RoomAgentDispatch` to caller tokens. Reviewed `kortexa-ai/hermes-livekit` 0.4.0 @ `640812f` (MIT; requires Hermes ≥0.20.0 not on PyPI; not LiveKit Agents-based). Config mapping in `spikes/T-M0-05/results/config_mapping.md`.
- Decision: **Confirm ADR-002** — assemble the realtime loop with **our** LiveKit Agents worker + provider adapters. **Do not adopt** `hermes-livekit` for the demo path. Map design §4.2 keys onto `TurnHandlingOptions` / Silero `VAD.load` / `aec_warmup_duration` (seconds). Pipecat remains the documented fallback only if Agents wiring regresses.
- Alternatives considered: adopt hermes-livekit (rejected: Hermes 0.20+ unavailable, weak FR-06 stage events, couples media to Hermes); Pipecat now (rejected: unnecessary — Agents stubs work); custom aiortc (rejected: more ownership than needed).
- Consequences: T-M1-10 implements the real worker against this mapping; session tokens must include agent dispatch; interruption fidelity work stays in T-M2-05. Native brew livekit-server re-verified in T-M0-07.
- Design doc impact: ADR-002 status note + U4/S-4 rows marked resolved by S-4 / D-20260920-05; §4.2 mapping footnote.
- Status: accepted

### D-20260920-04 - S-1: API-server metadata does not reach Hermes hooks; keep CALL_CONTEXT fallback
- Date / Task: 2026-09-20 / T-M0-02
- Context: Spike S-1 (U1). Installed `hermes-agent==0.19.0` (latest on PyPI; design cited 0.20.0 — not published). Python 3.12.13 scratch venv under `spikes/T-M0-02/`. Verified APIs from installed source (`hermes_cli.plugins.PluginContext.register_hook`, `agent.turn_context` `pre_llm_call` kwargs, `gateway.platforms.api_server._handle_chat_completions` / `_write_sse_chat_completion`). Ran correlation matrix + SSE close probe with a mock OpenAI stub; scrubbed evidence in `spikes/T-M0-02/results/`.
- Decision: **No** — OpenAI body `user` and headers `X-Call-Id`/`X-Turn-Id` do **not** appear in plugin hook kwargs. System-role `CALL_CONTEXT` also does **not** appear in `pre_llm_call` (`user_message` / `conversation_history`) because system text becomes `ephemeral_system_prompt`. **Keep** the §4.4 fallback, refined: put `CALL_CONTEXT call_id=<uuid>` in the **user** message content (not system), and require `call_id` on every tool schema (visible to `pre_tool_call.args`). ADR-006 (worker = latency SoT) stays. SSE client disconnect is handled in source via `agent.interrupt` + task cancel.
- Alternatives considered: rely on Hermes-internal `session_id`/`turn_id` (rejected: not CallScope UUIDs); put CALL_CONTEXT only in system (rejected: invisible to hooks); invent header plumbing in a Hermes fork (rejected: black-box constraint).
- Consequences: BrainBackend / worker (T-M1-09+) must send CALL_CONTEXT on user turns; plugin policy continues to validate tool `call_id`. Estimates unchanged.
- Design doc impact: §4.4 Correlation paragraph updated; ADR-006 status note (U1 resolved); U1 row marked resolved by S-1.
- Status: accepted

### D-20260920-02 - Align pre-commit ruff with project ruff 0.16.8
- Date / Task: 2026-09-20 / T-M0-01
- Context: Hook pin `astral-sh/ruff-pre-commit@v0.5.7` auto-fixed `@pytest.mark.integration` to `@pytest.mark.integration()`, which fails PT023 under project `ruff==0.16.8` used by CI (`uv run ruff`).
- Decision: Bump pre-commit ruff hook to `v0.16.8` to match `uv.lock`.
- Alternatives considered: ignore PT023 (rejected); keep dual versions (rejected: fight on every commit).
- Consequences: first `pre-commit run` after pull may re-download the hook env.
- Design doc impact: none.
- Status: accepted

### D-20260920-01 - CI pip-audit via uv export, not --strict --skip-editable
- Date / Task: 2026-09-20 / T-M0-01
- Context: `uv sync` installs `callscope` editable. Installed `pip-audit` 2.10.1 (`pip_audit._cli`): `--skip-editable` yields `SkippedDependency`, and `--strict` fatals on any skip (`callscope: distribution marked as editable`). Combining both flags made the security job always fail.
- Decision: In CI, `uv export --frozen --no-emit-project --extra dev` then `pip-audit -r … --strict --disable-pip`. Keep `--strict` for third-party collection failures; omit the local project from the audit set.
- Alternatives considered: drop `--strict` (weakens gate); drop `--skip-editable` and audit editable (fails for other reasons / noise); ignore vuln for callscope (wrong tool).
- Consequences: security job audits locked deps only; local package changes are covered by tests/mypy/ruff, not CVE DB.
- Design doc impact: none (aligns with §4.12 gitleaks + dependency audit in CI).
- Status: accepted

### D-20260919-01 - Schedule re-baselined from the task backlog
- Date / Task: 2026-09-19 / T-M0-01
- Context: The design doc (12.3) guessed 5-6 weeks part-time. Bottom-up estimates in backlog/tasks.yaml total 459 h (P0: 375 h, P1-P3: 84 h): M0 43, M1 106, M2 58, M3 92, M4 60, M5 50, M6 50.
- Decision: Plan from the backlog, not the guess. At 30 h/week that is about 15 weeks for everything, about 12.5 weeks for P0 only. Re-estimate after sprints S1 and S2 using actual hours (velocity ratio). If a shorter path is needed use the thin-slice cut in docs/DEV_GUIDE.md section 5.
- Alternatives considered: shrink estimates to fit 6 weeks (rejected: not credible); drop protected M3-M5 (rejected: it is the portfolio value).
- Consequences: sprint plan in DEV_GUIDE section 5; milestone dates move; design 12.3 effort sentence updated.
- Design doc impact: section 12.3 effort sentence only.
- Status: accepted (hours superseded by D-20260920-10 rescope totals)
