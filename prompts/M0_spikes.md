# M0 - Setup and spikes (spikes produce decisions, not product code)
Spike rules: time-boxed; throwaway code in `spikes/<TASK-ID>/`; results go into `docs/DECISIONS.md`
using the spike write-up prompt in ceremonies.md. Wrap every prompt with the workflow in
P01_task_wrapper.md (branch, status, CI, artifacts).

## T-M0-02
```text
Spike S-1 (task T-M0-02): can a per-call/turn ID reach Hermes plugin hook kwargs when Hermes is
called through its OpenAI-compatible API server?
- In a scratch venv under spikes/T-M0-02/, install Hermes Agent (record exact version), enable the
  API server (API_SERVER_ENABLED, API_SERVER_KEY, port 8642) with a dedicated profile.
- Write a ~30-line plugin (pip entry point group `hermes_agent.plugins`, `register(ctx)`) whose
  hooks (pre_llm_call, post_llm_call, pre_tool_call, post_tool_call, on_session_start/end) log all
  kwargs they receive (keys and truncated values). Verify hook names/signatures from the installed
  Hermes source or docs, not from memory.
- Call /v1/chat/completions with the `user` field, extra headers X-Call-Id/X-Turn-Id, and a
  `CALL_CONTEXT call_id=<uuid>` system message. Record which of these are visible in hook kwargs,
  and whether a registered tool function can obtain the ID (contextvar, kwargs, session object).
- Also test: does closing the SSE connection cancel generation and tool execution?
Deliver: DECISIONS.md entry with the verdict, the exact mechanism, Hermes version, and whether the
ADR-006 fallback (CALL_CONTEXT + call_id tool arg) stays. Update ADR-006 if needed.
```

## T-M0-07
```text
Spike S-6 (task T-M0-07): size the Nebius GPU node. I will provision it; you write the scripts
and the measurement harness (spikes/T-M0-07/).
- Provide a bash script that installs Docker + NVIDIA container toolkit checks and prints
  `nvidia-smi` info, and a Python script measuring: model download+load time (cold vs warm cache),
  VRAM per service (vLLM, ASR, TTS) via nvidia-smi --query-gpu, and steady-state idle VRAM.
- Provide an RTT probe run from my laptop in Irvine to candidate endpoints (ICMP/TCP connect and a
  WebRTC/TURN probe if feasible) with p50/p95 over 100 samples.
- Provide the procedure to stop/start the VM and keep the model cache on a persistent disk.
Deliver: filled VRAM table replacing design 9.5 estimates, warm-up minutes, chosen region and RTT,
and a written start/stop procedure (input to T-M6-03). Never print or commit credentials.
```

## T-M0-04
```text
Spike S-3 (task T-M0-04): LLM shortlist for reliable tool calling.
- Candidates: 2-3 open-weight instruct models that fit the measured VRAM budget (I will name them;
  if I don't, propose candidates with licences and ask me before downloading).
- For each, write the vLLM launch command with the correct tool-call parser flags (verify in vLLM
  docs/source for that model family; record the flags) and prefix caching enabled.
- Build spikes/T-M0-04/harness.py: 60 scripted receptionist turns (book, reschedule, cancel, FAQ,
  callback, handoff, corrections, injection attempts) sent through Hermes (with a throwaway plugin
  exposing the 7 tools from design 4.4 backed by stubs). Score: valid tool call, schema-correct
  args, correct tool choice, recovery after a policy error, refusal on injection.
- Report a table per model with counts and rates, plus p50 TTFT direct vs via Hermes if time allows.
Deliver: chosen model, flags, licence, and results in DECISIONS.md. Exit: >= 95% valid tool calls.
```

## T-M0-03
```text
Spike S-2 (task T-M0-03): Hermes per-turn overhead.
- Using the chosen LLM on vLLM, script 50 identical short receptionist turns against (a) vLLM
  directly and (b) Hermes API server with a slim `receptionist` profile (memory off, only the
  stub tools, minimal skill). Measure TTFT and total time, p50/p95, and prompt token counts.
- Try: prompt/prefix caching on vs off, shorter system prompt, disabling unused features. Verify
  each Hermes config option in its docs/source before using it.
Deliver: table + verdict vs the 450 ms brain-TTFT budget in design 3.6. If it fails, propose the
smallest mitigation (design R-02) and record it as a DECISIONS.md entry and, if needed, new tasks.
```

## T-M0-05
```text
Spike S-4 (task T-M0-05): LiveKit Agents wiring and hermes-livekit comparison.
- Run livekit-server locally with docker (dev keys from .env). Write a minimal LiveKit Agents
  worker with custom STT/TTS/LLM adapter classes backed by our mock providers (echo STT, sine or
  prerecorded TTS, canned LLM). Verify the exact API of the INSTALLED livekit-agents version
  (AgentSession/plugins, endpointing and interruption parameters) from its source; record the
  mapping table for design 4.2 config keys.
- A minimal browser page (spikes/T-M0-05/web) joins a room and talks to the agent. Test barge-in
  behaviour with the framework defaults and note false-trigger behaviour with speaker echo.
- Read the third-party hermes-livekit plugin source: what it reuses, which events it exposes, licence,
  maintenance signals. Do not adopt it without my approval.
Deliver: browser call works with stubs; config mapping; ADR-002 update recommending own worker vs
hermes-livekit vs Pipecat with evidence.
```

## T-M0-06
```text
Spike S-5 (task T-M0-06): ASR/TTS shortlist probe.
- Create eval/probe/: a 30-utterance script (10 with 10-digit phone numbers, 10 with names spelled
  out, 10 with addresses/dates), and generate audio with a TTS that will NOT be the agent's voice,
  plus optionally my own recordings (I will add them; they must not be committed unless I say so).
- Implement the C1 telephony chain (ffmpeg or sox: 8 kHz, 300-3400 Hz band-limit, mu-law
  encode/decode) as a tested function in callscope/norm or callscope/datasets (reused by T-M3-03).
- For 2 ASR candidates (I will name them; suggest options with licences if not) measure WER, digit
  sequence accuracy (jiwer + a tiny digit scorer), real-time factor, VRAM, and whether real
  streaming is supported. For 2 TTS candidates measure TTFB, real-time factor, licence and a
  round-trip WER through the better ASR.
Deliver: shortlist table in DECISIONS.md with numbers and licences; note the NFR impact.
```
